# Property Environmental Report

A FastAPI web application that geocodes U.S. property addresses and generates environmental reports by querying **EPA ECHO** and **USGS Water Services** for nearby facilities.

## Features

- **Geocoding** — Resolves addresses via OpenStreetMap Nominatim (auto-strips unit/suite numbers)
- **EPA ECHO + USGS** — Concurrent queries for environmental facilities within a configurable radius
- **Interactive Map** — Leaflet map with color-coded facility markers and radius circle
- **Distance & Direction** — Haversine distance + 8-point compass bearing for every facility
- **Export & Print** — Download results as `.txt` or print with clean layout
- **Edge-case hardened** — Whitespace validation, dedup fixes, bounding-box clamping, timeout handling

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, httpx, Pydantic |
| Frontend | Vanilla HTML/CSS/JS, Leaflet.js |
| APIs | Nominatim, EPA ECHO, USGS Water Services |

## Project Structure

```
property-report/
├── main.py                  # FastAPI backend (geocode + report endpoints)
├── requirements.txt         # Python dependencies
└── static/
    ├── index.html           # HTML shell
    ├── css/
    │   └── styles.css       # Neumorphic UI + print styles
    └── js/
        ├── app.js           # Core app logic (geocode, report, export)
        └── map.js           # Leaflet map rendering
```

## Quick Start

```bash
# Clone
git clone https://github.com/ameerul-muminin/property-report.git
cd property-report

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/geocode` | Geocode an address → lat/lon |
| `POST` | `/report` | Geocode + EPA ECHO + USGS environmental report |
| `GET` | `/` | Serve the frontend |

## License

MIT
