/* ═══════════════════════════════════════════════
   Property Environmental Report — App Logic
   ═══════════════════════════════════════════════ */

// ─── Radius slider ───
const slider  = document.getElementById('radius-slider');
const display = document.getElementById('radius-display');
slider.addEventListener('input', () => {
  display.textContent = parseFloat(slider.value).toFixed(1);
});

// ─── Utilities ───
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function showError(elId, msg) {
  const el = document.getElementById(elId);
  el.textContent = msg;
  el.classList.add('visible');
}

function hideError(elId) {
  document.getElementById(elId).classList.remove('visible');
}

// ─── GEOCODE ───
async function doGeocode() {
  const address = document.getElementById('geocode-address').value.trim();
  if (!address) { showError('geocode-error', 'Please enter a property address.'); return; }

  hideError('geocode-error');
  const resEl = document.getElementById('geocode-result');
  resEl.classList.remove('visible');

  const btn = document.getElementById('btn-geocode');
  btn.textContent = 'GEOCODING…';
  btn.disabled = true;

  try {
    const resp = await fetch('/geocode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `Server error (${resp.status})` }));
      throw new Error(err.detail || 'Geocoding failed');
    }
    const data = await resp.json();
    document.getElementById('geo-lat').textContent     = data.latitude.toFixed(6);
    document.getElementById('geo-lon').textContent     = data.longitude.toFixed(6);
    document.getElementById('geo-cleaned').textContent = data.cleaned_address;
    document.getElementById('geo-display').textContent = data.display_name;
    resEl.classList.add('visible');

    // Auto-fill report address
    document.getElementById('report-address').value = address;
  } catch (e) {
    showError('geocode-error', e.message);
  } finally {
    btn.textContent = 'GEOCODE ONLY';
    btn.disabled = false;
  }
}

// ─── REPORT ───
async function doReport() {
  const address = document.getElementById('report-address').value.trim();
  if (!address) { showError('report-error', 'Please enter a property address.'); return; }

  const radius  = parseFloat(slider.value);
  const loader  = document.getElementById('loader');
  const results = document.getElementById('results');

  hideError('report-error');
  results.classList.remove('visible');
  loader.classList.add('visible');

  const btn = document.getElementById('btn-report');
  btn.textContent = 'SEARCHING…';
  btn.disabled = true;

  try {
    const resp = await fetch('/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, radius_miles: radius }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `Server error (${resp.status})` }));
      throw new Error(err.detail || 'Report generation failed');
    }
    const data = await resp.json();
    window._lastReport = data;          // store for export / print
    renderResults(data);
  } catch (e) {
    showError('report-error', e.message);
  } finally {
    loader.classList.remove('visible');
    btn.textContent = 'GENERATE REPORT';
    btn.disabled = false;
  }
}

// ─── RENDER RESULTS ───
function renderResults(data) {
  document.getElementById('result-title').textContent =
    `Findings near ${data.address}`;
  document.getElementById('result-count').textContent =
    `${data.total_findings} facilit${data.total_findings === 1 ? 'y' : 'ies'} within ${data.radius_miles} mi`;
  document.getElementById('result-coords').textContent =
    `${data.latitude.toFixed(6)}, ${data.longitude.toFixed(6)}`;

  const list = document.getElementById('facility-list');
  list.innerHTML = '';

  if (data.facilities.length === 0) {
    list.innerHTML = `
      <div class="no-results">
        <div style="font-size:32px;margin-bottom:12px;">✓</div>
        No EPA or USGS facilities found within ${data.radius_miles} miles.<br>
        <span style="font-size:11px;opacity:.7;">
          This may indicate a clean area, or the radius may be too small.
          Try increasing the search radius for broader coverage.
        </span>
      </div>`;
  } else {
    data.facilities.forEach((f, i) => {
      const badgeClass = f.source === 'EPA_ECHO' ? 'badge-epa' : 'badge-usgs';

      // Proximity class
      let proxClass = 'proximity-far';
      if (f.distance_miles < 1)       proxClass = 'proximity-close';
      else if (f.distance_miles <= 3) proxClass = 'proximity-medium';

      // Source link
      let sourceLink = '';
      if (f.source === 'EPA_ECHO' && f.registry_id && f.registry_id !== 'N/A') {
        sourceLink = `<a href="https://echo.epa.gov/detailed-facility-report?fid=${encodeURIComponent(f.registry_id)}" target="_blank" rel="noopener" title="View on EPA ECHO">↗</a>`;
      } else if (f.source === 'USGS' && f.registry_id && f.registry_id !== 'N/A') {
        sourceLink = `<a href="https://waterdata.usgs.gov/nwis/inventory/?site_no=${encodeURIComponent(f.registry_id)}" target="_blank" rel="noopener" title="View on USGS">↗</a>`;
      }

      const el = document.createElement('div');
      el.className = `facility ${proxClass}`;
      el.style.setProperty('--i', i);
      el.innerHTML = `
        <div>
          <div class="facility-name">${esc(f.name)}${sourceLink}</div>
          <div class="facility-id">
            <span class="facility-badge ${badgeClass}">${f.source.replace('_', ' ')}</span>
            &nbsp; ${esc(f.registry_id)}
          </div>
        </div>
        <div class="facility-dist">
          <div class="miles">${f.distance_miles}</div>
          <div class="unit">miles ${f.direction}</div>
          <div class="facility-dir">${f.direction}</div>
        </div>
      `;
      list.appendChild(el);
    });
  }

  // Make results visible BEFORE initialising the map
  // (Leaflet needs a visible container to calculate size)
  document.getElementById('results').classList.add('visible');

  // Small delay so the browser can lay out the now-visible container
  if (typeof renderMap === 'function') {
    setTimeout(() => renderMap(data), 50);
  }

  document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ─── EXPORT (download .txt) ───
function exportReport() {
  const data = window._lastReport;
  if (!data) return;

  let text = `PROPERTY ENVIRONMENTAL REPORT\n`;
  text += `${'='.repeat(50)}\n\n`;
  text += `Address:    ${data.address}\n`;
  text += `Coords:     ${data.latitude.toFixed(6)}, ${data.longitude.toFixed(6)}\n`;
  text += `Radius:     ${data.radius_miles} miles\n`;
  text += `Findings:   ${data.total_findings}\n`;
  text += `Generated:  ${new Date().toLocaleString()}\n\n`;
  text += `${'─'.repeat(50)}\n\n`;

  if (data.facilities.length === 0) {
    text += `No EPA or USGS facilities found within the specified radius.\n`;
  } else {
    data.facilities.forEach((f, i) => {
      text += `${i + 1}. ${f.name}\n`;
      text += `   Source:    ${f.source.replace('_', ' ')}\n`;
      text += `   ID:        ${f.registry_id}\n`;
      text += `   Distance:  ${f.distance_miles} miles ${f.direction}\n`;
      text += `   Location:  ${f.latitude}, ${f.longitude}\n\n`;
    });
  }

  text += `${'─'.repeat(50)}\n`;
  text += `DISCLAIMER: This report uses publicly available EPA ECHO and USGS data.\n`;
  text += `It is NOT a certified environmental site assessment.\n`;

  const blob = new Blob([text], { type: 'text/plain' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `env-report-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── PRINT ───
function printReport() {
  window.print();
}

// ─── KEYBOARD SHORTCUTS ───
document.getElementById('geocode-address').addEventListener('keydown', e => {
  if (e.key === 'Enter') doGeocode();
});
document.getElementById('report-address').addEventListener('keydown', e => {
  if (e.key === 'Enter') doReport();
});
