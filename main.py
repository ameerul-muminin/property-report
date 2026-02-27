"""
Property Report API
───────────────────
Two endpoints:
  POST /geocode  — geocode an address (strips unit numbers first)
  POST /report   — geocode + query EPA ECHO + USGS for nearby facilities
"""

import asyncio
import math
import re
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────
app = FastAPI(
    title="Property Environmental Report",
    version="1.0.0",
    description="Geocode addresses and pull EPA/USGS environmental data.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────

class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1, examples=["1600 Pennsylvania Ave NW, Washington, DC 20500"])

    @field_validator("address")
    @classmethod
    def address_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Address must not be blank.")
        return v.strip()


class GeocodeResponse(BaseModel):
    original_address: str
    cleaned_address: str
    latitude: float
    longitude: float
    display_name: str


class ReportRequest(BaseModel):
    address: str = Field(..., min_length=1)
    radius_miles: float = Field(default=3.0, gt=0, le=50)

    @field_validator("address")
    @classmethod
    def address_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Address must not be blank.")
        return v.strip()


class Facility(BaseModel):
    name: str
    registry_id: str
    latitude: float
    longitude: float
    distance_miles: float
    direction: str
    source: str  # "EPA_ECHO" or "USGS"


class ReportResponse(BaseModel):
    address: str
    latitude: float
    longitude: float
    radius_miles: float
    total_findings: int
    facilities: list[Facility]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

# Nominatim requires a descriptive User-Agent
NOMINATIM_HEADERS = {"User-Agent": "PropertyReportApp/1.0 (student project)"}

# Patterns for unit / suite numbers to strip before geocoding
UNIT_PATTERNS = re.compile(
    r"""
    \s*                             # leading whitespace
    (?:
        \#\s*\d+[A-Za-z]?          # #150, #4A
      | (?:Suite|Ste|Unit|Apt|Apartment|Room|Rm|Floor|Fl|Bldg|Building)
        [.\s:]+[A-Za-z0-9-]+       # Suite 200, Unit 4-B
    )
    (?=\s*,|\s*$)                   # must be followed by comma or end
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_unit(address: str) -> str:
    """Remove unit / suite numbers so the geocoder hits the building."""
    return UNIT_PATTERNS.sub("", address).strip().rstrip(",")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return the great-circle distance in **miles** between two points
    on Earth given their latitude/longitude in decimal degrees.

    Uses the Haversine formula — implemented from scratch, no library.
    """
    R = 3_958.8  # Earth's mean radius in miles

    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)

    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(R * c, 2)


def cardinal_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """
    Return the 8-point compass direction FROM (lat1, lon1) TO (lat2, lon2).
    """
    Δlat = lat2 - lat1
    Δlon = lon2 - lon1

    angle = math.degrees(math.atan2(Δlon, Δlat))  # 0° = N, 90° = E
    angle = (angle + 360) % 360  # normalise to [0, 360)

    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(angle / 45) % 8
    return directions[index]


# ──────────────────────────────────────────────
# Core async functions
# ──────────────────────────────────────────────

async def geocode_address(address: str, client: httpx.AsyncClient) -> dict:
    """Call Nominatim to geocode *address*. Returns dict with lat, lon, display_name."""
    cleaned = strip_unit(address)
    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="Address became empty after removing unit/suite number. Please provide a full street address.",
        )
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": cleaned, "format": "json", "limit": 1}

    resp = await client.get(url, params=params, headers=NOMINATIM_HEADERS, timeout=15)
    resp.raise_for_status()
    results = resp.json()

    if not results:
        raise HTTPException(status_code=404, detail=f"Could not geocode address: {cleaned}")

    hit = results[0]
    return {
        "original_address": address,
        "cleaned_address": cleaned,
        "latitude": float(hit["lat"]),
        "longitude": float(hit["lon"]),
        "display_name": hit.get("display_name", ""),
    }


async def fetch_epa_echo(
    lat: float, lon: float, radius_miles: float, client: httpx.AsyncClient
) -> list[dict]:
    """
    Query the EPA ECHO Facility search for facilities within *radius_miles*
    of the given coordinates.
    Docs: https://echo.epa.gov/tools/web-services
    """
    url = "https://echo.epa.gov/api/rest_lookups.get_facility_info"
    params = {
        "output": "JSON",
        "p_lat": lat,
        "p_long": lon,
        "p_radius": radius_miles,  # ECHO accepts miles
    }

    try:
        resp = await client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, Exception):
        return []  # gracefully degrade

    facilities: list[dict] = []
    # ECHO nests results differently depending on the endpoint version
    rows = (
        data.get("Results", {}).get("Facilities", [])
        or data.get("Results", {}).get("FacilityList", [])
        or []
    )
    for row in rows:
        try:
            fac_lat = float(row.get("Lat83", row.get("FacLat", 0)))
            fac_lon = float(row.get("Long83", row.get("FacLong", 0)))
            if fac_lat == 0 and fac_lon == 0:
                continue
            facilities.append({
                "name": row.get("FacName", row.get("Name", "Unknown Facility")),
                "registry_id": row.get("RegistryID", row.get("FacId", "N/A")),
                "latitude": fac_lat,
                "longitude": fac_lon,
                "source": "EPA_ECHO",
            })
        except (ValueError, TypeError):
            continue

    return facilities


async def fetch_usgs(
    lat: float, lon: float, radius_miles: float, client: httpx.AsyncClient
) -> list[dict]:
    """
    Query the USGS Water Services for monitoring sites within the radius.
    Docs: https://waterservices.usgs.gov
    """
    # USGS site service expects radius in miles — max 150
    url = "https://waterservices.usgs.gov/nwis/site/"
    params = {
        "format": "rdb",
        "bBox": _bounding_box(lat, lon, radius_miles),
        "siteStatus": "active",
        "hasDataTypeCd": "iv",  # sites with real-time (instantaneous) data
    }

    try:
        resp = await client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        text = resp.text
    except (httpx.HTTPError, Exception):
        return []

    sites: list[dict] = []
    header_seen = False
    for line in text.splitlines():
        # Skip comment lines
        if line.startswith("#"):
            continue
        # The first non-comment line is the column header row
        if not header_seen:
            header_seen = True
            continue
        # The second non-comment line is the data-type row (e.g., "5s\t15s\t…")
        # Detect it: every tab-separated token matches the pattern \d+[sdna]
        parts = line.split("\t")
        if all(re.match(r"^\d+[sdna]$", p.strip()) for p in parts if p.strip()):
            continue
        if len(parts) < 5:
            continue
        try:
            site_name = parts[2] if len(parts) > 2 else "USGS Site"
            site_lat = float(parts[4]) if len(parts) > 4 else 0
            site_lon = float(parts[5]) if len(parts) > 5 else 0
            if site_lat == 0 and site_lon == 0:
                continue
            sites.append({
                "name": site_name.strip(),
                "registry_id": parts[1].strip() if len(parts) > 1 else "N/A",
                "latitude": site_lat,
                "longitude": site_lon,
                "source": "USGS",
            })
        except (ValueError, IndexError):
            continue

    return sites


def _bounding_box(lat: float, lon: float, radius_miles: float) -> str:
    """Return 'west,south,east,north' bounding box string for USGS."""
    # Approximate degrees per mile at this latitude
    lat_delta = radius_miles / 69.0
    cos_lat = math.cos(math.radians(lat))
    # Guard against division by zero at the poles
    lon_delta = radius_miles / (69.0 * cos_lat) if cos_lat > 1e-6 else 180.0
    west = round(max(lon - lon_delta, -180.0), 6)
    south = round(max(lat - lat_delta, -90.0), 6)
    east = round(min(lon + lon_delta, 180.0), 6)
    north = round(min(lat + lat_delta, 90.0), 6)
    return f"{west},{south},{east},{north}"


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@app.post("/geocode", response_model=GeocodeResponse)
async def geocode(req: GeocodeRequest):
    """
    Accept a property address, strip unit numbers, geocode via Nominatim,
    and return the coordinates.
    """
    try:
        async with httpx.AsyncClient() as client:
            result = await geocode_address(req.address, client)
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Geocoding service timed out. Please try again.")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding service error: {exc}")
    return GeocodeResponse(**result)


@app.post("/report", response_model=ReportResponse)
async def report(req: ReportRequest):
    """
    Geocode the address, then query EPA ECHO **and** USGS concurrently
    for facilities within the given radius. Return each as a finding
    with haversine distance and cardinal direction.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Step 1 — geocode
            geo = await geocode_address(req.address, client)
            lat, lon = geo["latitude"], geo["longitude"]
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Geocoding service timed out. Please try again.")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding service error: {exc}")

    async with httpx.AsyncClient() as client:

        # Step 2 — fan out EPA + USGS simultaneously (bonus)
        epa_task = fetch_epa_echo(lat, lon, req.radius_miles, client)
        usgs_task = fetch_usgs(lat, lon, req.radius_miles, client)
        epa_results, usgs_results = await asyncio.gather(epa_task, usgs_task)

    # Step 3 — merge, compute distance & direction, sort
    all_raw = epa_results + usgs_results
    facilities: list[Facility] = []
    seen_ids: set[str] = set()

    for raw in all_raw:
        rid = raw["registry_id"]
        # Use a composite key to avoid collapsing unrelated sites that share "N/A"
        dedup_key = (
            f"{rid}|{raw['source']}"
            if rid and rid != "N/A"
            else f"{raw['name']}|{raw['latitude']}|{raw['longitude']}|{raw['source']}"
        )
        if dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)

        dist = haversine(lat, lon, raw["latitude"], raw["longitude"])
        if dist > req.radius_miles:
            continue  # respect the radius

        direction = cardinal_direction(lat, lon, raw["latitude"], raw["longitude"])
        facilities.append(
            Facility(
                name=raw["name"],
                registry_id=rid,
                latitude=raw["latitude"],
                longitude=raw["longitude"],
                distance_miles=dist,
                direction=direction,
                source=raw["source"],
            )
        )

    facilities.sort(key=lambda f: f.distance_miles)

    return ReportResponse(
        address=geo["cleaned_address"],
        latitude=lat,
        longitude=lon,
        radius_miles=req.radius_miles,
        total_findings=len(facilities),
        facilities=facilities,
    )


# ──────────────────────────────────────────────
# Serve static frontend
# ──────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")