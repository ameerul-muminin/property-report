/* ═══════════════════════════════════════════════
   Property Environmental Report — Leaflet Map
   ═══════════════════════════════════════════════
   Requires Leaflet JS + CSS loaded before this file.
*/

let map       = null;
let mapLayers = [];   // track markers & circles for cleanup

/**
 * Render (or re-render) the Leaflet map with the property location,
 * a radius circle, and coloured markers for every facility.
 *
 * @param {Object} data — ReportResponse from the API
 */
function renderMap(data) {
  const container = document.getElementById('map');
  if (!container) return;

  // ── Initialise map once ──
  if (!map) {
    map = L.map('map', {
      zoomControl: true,
      scrollWheelZoom: true,
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);
  }

  // ── Clear previous layers ──
  mapLayers.forEach(l => map.removeLayer(l));
  mapLayers = [];

  const center = [data.latitude, data.longitude];

  // ── Radius circle ──
  const radiusMeters = data.radius_miles * 1609.34;
  const circle = L.circle(center, {
    radius: radiusMeters,
    color: '#1a1a18',
    weight: 1.5,
    opacity: 0.5,
    fillColor: '#1a1a18',
    fillOpacity: 0.04,
    dashArray: '6 4',
  }).addTo(map);
  mapLayers.push(circle);

  // ── Property marker (dark) ──
  const propertyIcon = L.divIcon({
    className: '',
    html: `<div style="
      width:18px;height:18px;border-radius:50%;
      background:#1a1a18;border:3px solid #e5e0d8;
      box-shadow:0 2px 6px rgba(0,0,0,.35);
    "></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
  const propMarker = L.marker(center, { icon: propertyIcon, zIndexOffset: 1000 })
    .bindPopup(`<strong>${esc(data.address)}</strong><br><small>Subject property</small>`)
    .addTo(map);
  mapLayers.push(propMarker);

  // ── Facility markers ──
  data.facilities.forEach(f => {
    const color = f.distance_miles < 1 ? '#c0392b'
               : f.distance_miles <= 3 ? '#e67e22'
               : '#27ae60';

    const icon = L.divIcon({
      className: '',
      html: `<div style="
        width:12px;height:12px;border-radius:50%;
        background:${color};border:2px solid #fff;
        box-shadow:0 1px 4px rgba(0,0,0,.3);
      "></div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });

    const sourceLabel = f.source.replace('_', ' ');
    let link = '';
    if (f.source === 'EPA_ECHO' && f.registry_id && f.registry_id !== 'N/A') {
      link = `<br><a href="https://echo.epa.gov/detailed-facility-report?fid=${encodeURIComponent(f.registry_id)}" target="_blank" rel="noopener">View on EPA ↗</a>`;
    } else if (f.source === 'USGS' && f.registry_id && f.registry_id !== 'N/A') {
      link = `<br><a href="https://waterdata.usgs.gov/nwis/inventory/?site_no=${encodeURIComponent(f.registry_id)}" target="_blank" rel="noopener">View on USGS ↗</a>`;
    }

    const marker = L.marker([f.latitude, f.longitude], { icon })
      .bindPopup(`
        <strong>${esc(f.name)}</strong><br>
        <small>${sourceLabel} · ${f.distance_miles} mi ${f.direction}</small>
        ${link}
      `)
      .addTo(map);
    mapLayers.push(marker);
  });

  // ── Fit view ──
  // invalidateSize first so Leaflet recalculates the container dimensions,
  // then fitBounds — avoids 'layerPointToLatLng' errors on hidden-then-shown containers.
  map.invalidateSize();
  try {
    map.fitBounds(circle.getBounds().pad(0.1));
  } catch (_) {
    // Fallback: centre on the property if fitBounds still fails
    map.setView(center, 12);
  }

  // Second invalidateSize after tiles load to fix grey patches
  setTimeout(() => map.invalidateSize(), 300);
}

/**
 * Shared HTML-escape (mirrors the one in app.js).
 * Defined locally so map.js can work standalone.
 */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
