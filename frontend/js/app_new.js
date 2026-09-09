/**
 * SatQuery AI frontend application
 */

let lastAnalysis = null;
let currentLoc = null;
let currentUploadedImage = null;
let currentImageId = null;
let currentLandcoverCategory = 'Water';
let locationSearchInFlight = false;
let lastCreatedAlertId = null;

// ============================================================================
// INITIALIZATION
// ============================================================================

async function boot() {
  console.log('[boot] Starting application initialization');
  
  MapUI.initMap();
  UI.setStatus('INITIALIZING');
  
  try {
    const st = await API.status();
    UI.setStatus(st.mode === 'REAL_DATA_MODE' ? 'DATA_CONNECTED' : 'PARTIAL_DATA');
    UI.renderSihStatus(st.sih_requirements);
    console.log('[boot] API status:', st.mode);
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    console.error('[boot] API error:', e);
    document.getElementById('answer-text').textContent =
      'Backend not reachable. Start with: python run.py (port 8000)';
  }

  // Attach event listeners
  console.log('[boot] Attaching event listeners');
  
  document.getElementById('btn-locate').addEventListener('click', onLocate);
  document.getElementById('btn-ask').addEventListener('click', onAsk);
  document.getElementById('btn-report').addEventListener('click', onReport);
  document.getElementById('btn-upload-image').addEventListener('click', onUploadImage);
  
  const compareBtn = document.getElementById('btn-compare-images');
  if (compareBtn) { compareBtn.addEventListener('click', onCompareImages); }
  const compareDatesBtn = document.getElementById('btn-compare-dates');
  if (compareDatesBtn) { compareDatesBtn.addEventListener('click', onCompareDates); }
  const loadYearsBtn = document.getElementById('btn-load-years');
  if (loadYearsBtn) { loadYearsBtn.addEventListener('click', loadAvailableYears); }
  document.querySelectorAll('input[name="compare-mode"]').forEach(function(r) {
    r.addEventListener('change', function() {
      const mode = document.querySelector('input[name="compare-mode"]:checked').value;
      const dr = document.getElementById('compare-dates-row');
      const yr = document.getElementById('compare-years-row');
      if (dr) dr.style.display = mode === 'dates' ? 'flex' : 'none';
      if (yr) yr.style.display = mode === 'years' ? 'flex' : 'none';
      if (mode === 'years') loadAvailableYears();
    });
  });
  
  const createAlertBtn = document.getElementById('btn-create-alert');
  if (createAlertBtn) { createAlertBtn.addEventListener('click', onAlertCreate); }
  
  const testAlertBtn = document.getElementById('btn-test-alert');
  if (testAlertBtn) { testAlertBtn.addEventListener('click', onAlertTest); }
  
  document.getElementById('btn-analyze-landcover').addEventListener('click', onAnalyzeLandcover);
  
  // Area selection
  document.getElementById('btn-select-area').addEventListener('click', () => {
    MapUI.startAreaSelection((count) => {
      UI.setAreaStatus(`Drawing manual area: ${count} point${count === 1 ? '' : 's'}.`);
    });
    document.getElementById('btn-select-area').classList.add('hidden');
    document.getElementById('btn-finish-area').classList.remove('hidden');
    document.getElementById('btn-cancel-area').classList.remove('hidden');
    UI.setAreaStatus('Drawing manual area: click at least three points on the map.');
  });
  
  document.getElementById('btn-finish-area').addEventListener('click', () => {
    const aoi = MapUI.finishAreaSelection();
    if (!aoi) {
      const validation = MapUI.validateManualAoi();
      UI.setAreaStatus(validation.error || 'Invalid area. Please redraw.', 'error');
      return;
    }
    setAreaControls(false);
    MapUI.fitManualAoi();
    UI.setAreaStatus(`Area Selected · ${MapUI.areaKm2(aoi).toFixed(2)} km²`, 'success');
    syncManualAreaLocation();
  });
  
  document.getElementById('btn-cancel-area').addEventListener('click', () => {
    MapUI.cancelAreaSelection();
    setAreaControls(false);
    UI.setAreaStatus('Draw an area on the map');
  });
  
  document.getElementById('btn-clear-area').addEventListener('click', () => {
    MapUI.clearAreaSelection();
    setAreaControls(false);
    UI.setAreaStatus('Draw an area on the map');
  });
  
  document.getElementById('btn-clear-landcover').addEventListener('click', () => {
    MapUI.clearLandcoverOverlay();
    UI.renderLandcoverSummary({ success: false });
    UI.setLandcoverStatus('Analysis overlay cleared.', 'success');
  });
  
  document.getElementById('image-file-input').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    UI.setSelectedImageName(file ? file.name : '');
    if (!file) {
      UI.setUploadMessage('', 'success');
    }
  });
  
  document.querySelectorAll('.landcover-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      currentLandcoverCategory = btn.dataset.category;
      document.querySelectorAll('.landcover-btn').forEach(b => b.classList.toggle('active', b === btn));
    });
  });
  
  document.getElementById('ly-landcover')?.addEventListener('change', (e) => {
    if (e.target.checked) {
      if (currentUploadedImage && currentUploadedImage.bounds) {
        MapUI.showLandcoverOverlay({
          success: true,
          ...currentUploadedImage,
          selected_category: currentLandcoverCategory,
          class: currentLandcoverCategory,
          bounds: currentUploadedImage.bounds,
          analysis_method: 'uploaded image bounds'
        });
      }
    } else {
      MapUI.clearLandcoverOverlay();
    }
  });
  
  document.getElementById('overlay-opacity')?.addEventListener('input', (e) => {
    MapUI.setLandcoverOpacity(e.target.value);
  });
  
  document.getElementById('location-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') onLocate();
  });
  
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.getElementById('question-input').value = chip.dataset.q;
      onAsk();
    });
  });
  
  console.log('[boot] Initialization complete');
}

// ============================================================================
// LOCATION SEARCH
// ============================================================================

async function onLocate() {
  if (locationSearchInFlight) return;
  
  const q = Query.currentLocationQuery();
  if (!q) {
    UI.setLocationSearchStatus('Please enter a location.', 'error');
    return;
  }
  
  locationSearchInFlight = true;
  const locateButton = document.getElementById('btn-locate');
  locateButton.disabled = true;
  UI.setLocationSearchStatus('Searching…', 'loading');
  
  try {
    const result = await API.searchLocation(q);
    if (!result || !result.success || !Number.isFinite(Number(result.lat)) || !Number.isFinite(Number(result.lon))) {
      throw new Error(result?.error || 'No valid location was returned by the geocoding service.');
    }
    currentLoc = { ...result, lat: Number(result.lat), lon: Number(result.lon) };
    UI.setLocationInfo(result);
    UI.setLocationSearchStatus('Location found.', 'success');
    
    if (result.bbox) {
      MapUI.clearMapOverlays();
      MapUI.showLocation(result);
      UI.showProgress('Loading OSM water features…');
      
      try {
        const water = await API.waterFeatures(result.bbox);
        if (water.success) {
          MapUI.showOsmWater(water.features);
        }
      } catch (_) {
        // Water features are optional
      }
    }
    
    UI.setStatus('DATA_CONNECTED');
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    UI.setLocationSearchStatus('Location not found. Please enter a valid location.', 'error');
    console.error('[onLocate] Error:', e);
  } finally {
    UI.hideProgress();
    locateButton.disabled = false;
    locationSearchInFlight = false;
  }
}

// ============================================================================
// AREA SYNC
// ============================================================================

async function syncManualAreaLocation() {
  try {
    const aoi = MapUI.getManualAoi();
    if (!aoi) {
      if (currentLoc) {
        const center = { lat: currentLoc.lat, lon: currentLoc.lon };
        UI.setLocationInfo({ ...currentLoc, aoi_area_km2: MapUI.areaKm2(MapUI.getManualAoi()) });
        UI.setAreaStatus(`Area Selected · ${MapUI.areaKm2(MapUI.getManualAoi()).toFixed(2)} km²`, 'success');
      } else {
        const center = MapUI.getManualAoiCenter?.();
        if (center) {
          document.getElementById('location-input').value = `Selected area near ${center.lat.toFixed(5)}, ${center.lon.toFixed(5)}`;
        } else {
          document.getElementById('location-input').value = 'Selected area';
        }
      }
    } else {
      document.getElementById('location-input').value = `Selected area near ${aoi[0].lat.toFixed(5)}, ${aoi[0].lon.toFixed(5)}`;
    }
  } catch (error) {
    document.getElementById('location-input').value = `Selected area (coordinates unavailable)`;
  }
}

// ============================================================================
// CHAT & ANALYSIS
// ============================================================================

function appendChatBubble(role, content, meta) {
  const container = document.getElementById('chat-messages') || document.getElementById('answer-text');
  if (!container) return;
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble ' + role;
  const body = document.createElement('div');
  body.style.whiteSpace = 'pre-wrap';
  body.textContent = content;
  bubble.appendChild(body);
  if (meta && meta.chips && meta.chips.length) {
    const chips = document.createElement('div');
    chips.style.marginTop = '6px';
    meta.chips.forEach(function(t) {
      const c = document.createElement('span');
      c.className = 'evidence-chip';
      c.textContent = t;
      chips.appendChild(c);
    });
    bubble.appendChild(chips);
  }
  if (meta && (meta.task || meta.confidence != null)) {
    const metaEl = document.createElement('div');
    metaEl.className = 'chat-meta';
    metaEl.textContent = (meta.task ? ('task: ' + meta.task) : '') +
      (meta.confidence != null ? (' · confidence: ' + meta.confidence) : '');
    bubble.appendChild(metaEl);
  }
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

async function onAsk() {
  const q = Query.currentQuestion();
  if (!q) {
    UI.setStatus('QUERY_MISSING');
    return;
  }
  
  const locQ = Query.currentLocationQuery();
  if (!locQ && !currentLoc && !MapUI.hasAreaPoints() && !currentImageId) {
    UI.setStatus('LOCATION_MISSING');
    document.getElementById('answer-text').textContent = 'Search for a location, draw an AOI, or upload an image first.';
    return;
  }
  
  UI.showProgress('AI: routing & fetching real data…');
  document.getElementById('answer-text').textContent = '';
  
  try {
    const aoi = getValidatedActiveAoi();
    if (aoi === false) return;
    const locationForChat = locQ || currentLoc?.display_name || 'Selected AOI';
    const result = await API.chatMessage({
      session_id: window.__satquery_chat_session_id || null,
      message: q,
      location: locationForChat,
      image_id: currentImageId || undefined,
      aoi: aoi || undefined,
    });
    window.__satquery_chat_session_id = result.session_id || window.__satquery_chat_session_id || null;
    lastAnalysis = result.analysis || result;
    
    const text = result.content || result.answer_text || result.analysis?.answer_text || 'No answer generated.';
    appendChatBubble('user', q, null);
    appendChatBubble('assistant', text, {
      task: result.task || result.detected_task,
      confidence: result.confidence,
      chips: result.chips || (result.evidence && result.evidence.chips) || [],
    });
    const at = document.getElementById('answer-text');
    if (at) at.textContent = text;
    if (result.analysis?.location) {
      currentLoc = result.analysis.location;
      UI.setLocationInfo(currentLoc);
      MapUI.showLocation(currentLoc);
    }
    UI.setStatus(result.success === false ? 'PARTIAL_DATA' : 'DATA_CONNECTED');
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    appendChatBubble('assistant', 'Error: ' + e.message, null);
    const at = document.getElementById('answer-text');
    if (at) at.textContent = 'Analysis error: ' + e.message;
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// REPORTING
// ============================================================================

async function onReport() {
  if (!lastAnalysis) {
    document.getElementById('answer-text').textContent = 'Run an analysis first.';
    return;
  }
  
  UI.showProgress('Generating report…');
  
  try {
    const rep = await API.report(
      Query.currentLocationQuery(),
      Query.currentQuestion(),
      lastAnalysis
    );
    
    const blob = new Blob([rep.report_text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = rep.file || 'satquery_report.txt';
    a.click();
  } catch (e) {
    document.getElementById('answer-text').textContent = 'Report error: ' + e.message;
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// IMAGE UPLOAD
// ============================================================================

async function onUploadImage() {
  const input = document.getElementById('image-file-input');
  const file = input.files && input.files[0];
  
  if (!file) {
    UI.setUploadMessage('Please select a file.', 'error');
    return;
  }
  
  const fd = new FormData();
  fd.append('file', file);
  
  const aoi = getValidatedActiveAoi();
  if (aoi) {
    fd.append('bounds', JSON.stringify(aoi));
  }
  
  UI.showProgress('Uploading image…');
  
  try {
    const res = await fetch('/api/images/upload', {
      method: 'POST',
      body: fd
    }).then(r => r.json());
    
    if (res.success) {
      currentUploadedImage = res;
      currentImageId = res.image_id || null;
      UI.setUploadMessage('Image uploaded: ' + (res.filename || 'unknown'), 'success');
      UI.renderImageMetadata(res);
      
      const statusMessage = `Image loaded successfully. CRS: ${res.crs || 'MISSING CRS'} · Bands: ${res.bands || 0} · Resolution: ${res.resolution ? `${Number(res.resolution.x).toFixed(6)} x ${Number(res.resolution.y).toFixed(6)}` : 'n/a'}`;
      document.getElementById('image-status').textContent = statusMessage;
      
      if (res.bounds) {
        MapUI.showUploadedRaster(res);
      }
    } else if (res.crs && res.crs.toUpperCase() === 'MISSING CRS') {
      UI.setUploadMessage('Warning: Image CRS is missing. Some features may not work.', 'warning');
    }
  } catch (e) {
    UI.renderImageMetadata({ success: false });
    UI.setUploadMessage('Upload failed: ' + e.message, 'error');
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// LAND COVER ANALYSIS
// ============================================================================

async function onAnalyzeLandcover() {
  const category = currentLandcoverCategory;
  
  const aoi = getValidatedActiveAoi();
  if (!aoi) {
    UI.setLandcoverStatus('No valid area. Search for location or draw an area.', 'error');
    UI.renderLandcoverSummary({ success: false });
    return;
  }
  
  UI.showProgress(`Analyzing ${category}…`);
  UI.setLandcoverStatus('Analyzing…', 'loading');
  
  try {
    const analysis = await API.analyzeLandcover(
      null,
      category,
      aoi,
      currentLoc
    );
    
    if (analysis.success || analysis.map_layers) {
      UI.renderLandcoverSummary(analysis);
      UI.setLandcoverStatus(`Analysis complete: ${category}.`, 'success');
      
      const layers = analysis.map_layers || {};
      if (analysis.geojson || analysis.map_geojson || analysis.overlay_geojson || layers.overlay) {
        MapUI.showLandcoverOverlay(analysis);
      }
    } else {
      UI.renderLandcoverSummary({ success: false });
      UI.setLandcoverStatus('Analysis returned no data.', 'warning');
    }
  } catch (e) {
    console.error('[onAnalyzeLandcover] Error:', e);
    UI.renderLandcoverSummary({ success: false });
    UI.setLandcoverStatus('Analysis failed: ' + e.message, 'error');
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// IMAGE COMPARISON
// ============================================================================

async function onCompareImages() {
  const b = document.getElementById('image-before')?.files?.[0];
  const a = document.getElementById('image-after')?.files?.[0];
  
  if (!b || !a) {
    UI.renderComparisonResult({ success: false, error: 'Please upload both Before and After images.' });
    return;
  }
  
  const fd = new FormData();
  fd.append('before', b);
  fd.append('after', a);
  
  const aoi = getValidatedActiveAoi();
  if (aoi) {
    fd.append('bounds', JSON.stringify(aoi));
  }
  
  UI.showProgress('Comparing images…');
  
  try {
    const compareRes = await fetch('/api/image/compare', {
      method: 'POST',
      body: fd
    }).then(r => r.json());
    
    if (compareRes.success) {
      UI.renderComparisonResult(compareRes);
      
      const html = `
        <strong>Method:</strong> ${compareRes.method}<br>
        <strong>Changed Area:</strong> ${compareRes.stats.percentage_changed}% (${compareRes.stats.changed_pixels} px)<br>
        <em>${compareRes.report_summary}</em><br>
      `;
      
      document.getElementById('answer-text').innerHTML = html;
      
      if (compareRes.map_layers) {
        if (compareRes.map_layers.overlay) {
          MapUI.showMaskGeoJSON('change', compareRes.map_layers.overlay, {
            color: compareRes.map_layers.color || '#FF0000',
            opacity: 0.7
          });
        }
      }
    } else {
      UI.renderComparisonResult({ success: false, error: compareRes.error });
    }
  } catch (e) {
    UI.renderComparisonResult({ success: false, error: e.message });
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// HELPERS
// ============================================================================

function getValidatedActiveAoi() {
  const aoi = MapUI.getManualAoi();
  
  // If manual AOI exists, convert to GeoJSON polygon
  if (aoi && MapUI.hasAreaPoints()) {
    // aoi is array of {lat, lon} objects - convert to GeoJSON
    const coords = aoi.map(p => [p.lon, p.lat]);
    // Close the polygon by adding first point at end
    if (coords.length > 0 && (coords[coords.length-1][0] !== coords[0][0] || coords[coords.length-1][1] !== coords[0][1])) {
      coords.push([coords[0][0], coords[0][1]]);
    }
    return {
      type: 'Polygon',
      coordinates: [coords]
    };
  }
  
  // If location exists, use its bbox as AOI
  if (currentLoc) {
    if (currentLoc.bbox && currentLoc.bbox.length === 4) {
      const [minLon, minLat, maxLon, maxLat] = currentLoc.bbox;
      return {
        type: 'Polygon',
        coordinates: [[
          [minLon, minLat],
          [maxLon, minLat],
          [maxLon, maxLat],
          [minLon, maxLat],
          [minLon, minLat]
        ]]
      };
    }
  }
  
  return null;
}

function setAreaControls(drawing) {
  document.getElementById('btn-select-area').classList.toggle('hidden', drawing);
  document.getElementById('btn-finish-area').classList.toggle('hidden', !drawing);
  document.getElementById('btn-cancel-area').classList.toggle('hidden', !drawing);
}

// ============================================================================
// ALERTS
// ============================================================================

async function onAlertCreate() {
  const loc = document.getElementById('alert-location').value;
  const cond = document.getElementById('alert-condition').value;
  const thresh = document.getElementById('alert-threshold').value;
  const email = document.getElementById('alert-email').value;
  const phone = document.getElementById('alert-phone').value;
  
  if (!loc || !thresh || (!email && !phone)) {
    document.getElementById('alert-status').textContent = 'Please provide location, threshold, and at least one contact method (email/phone).';
    document.getElementById('alert-status').className = 'upload-status error';
    return;
  }
  
  UI.showProgress('Creating alert…');
  document.getElementById('alert-status').textContent = 'Creating alert...';
  document.getElementById('alert-status').className = 'upload-status loading';
  
  try {
    const res = await fetch('/api/alerts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location_name: loc,
        condition_type: cond,
        threshold: parseFloat(thresh),
        email: email || null,
        phone: phone || null
      })
    }).then(r => r.json());
    
    lastCreatedAlertId = res.id;
    document.getElementById('alert-status').textContent = 'Alert created successfully! ID: ' + res.id;
    document.getElementById('alert-status').className = 'upload-status success';
  } catch (e) {
    document.getElementById('alert-status').textContent = e.message || 'Failed to create alert.';
    document.getElementById('alert-status').className = 'upload-status error';
  } finally {
    UI.hideProgress();
  }
}

async function onAlertTest() {
  if (!lastCreatedAlertId) {
    document.getElementById('alert-status').textContent = 'Create an alert first to test it.';
    document.getElementById('alert-status').className = 'upload-status error';
    return;
  }
  
  UI.showProgress('Sending test alert…');
  document.getElementById('alert-status').textContent = 'Sending test alert...';
  document.getElementById('alert-status').className = 'upload-status loading';
  
  try {
    const res = await fetch('/api/alerts/' + lastCreatedAlertId + '/test', {
      method: 'POST'
    }).then(r => r.json());
    
    if (res.success) {
      document.getElementById('alert-status').textContent = 'Test alert sent successfully! (' + (res.details || []).join(', ') + ')';
      document.getElementById('alert-status').className = 'upload-status success';
    } else {
      document.getElementById('alert-status').textContent = 'Test alert failed: ' + (res.errors || []).join(', ');
      document.getElementById('alert-status').className = 'upload-status error';
    }
  } catch (e) {
    document.getElementById('alert-status').textContent = e.message || 'Failed to test alert.';
    document.getElementById('alert-status').className = 'upload-status error';
  } finally {
    UI.hideProgress();
  }
}

// ============================================================================
// APP STARTUP
// ============================================================================

function startApp() {
  console.log('[startApp] Calling boot()');
  if (typeof boot === 'function') {
    boot().catch(e => console.error('[startApp] boot error:', e));
  } else {
    console.error('[startApp] boot is not a function');
  }
}

function initializeApp() {
  console.log('[initializeApp] Starting');
  try {
    if (typeof boot === 'function') {
      console.log('[initializeApp] Calling boot()');
      boot().catch(e => console.error('[initializeApp] boot error:', e));
    } else {
      console.error('[initializeApp] boot is not defined');
    }
  } catch (error) {
    console.error('[initializeApp] Error:', error);
  }
}

function scheduleInit() {
  console.log('[scheduleInit] Scheduling initialization with 100ms delay');
  setTimeout(() => {
    console.log('[scheduleInit] Running delayed initialization');
    initializeApp();
  }, 100);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  console.log('[app.js] DOM is loading, waiting for DOMContentLoaded');
  document.addEventListener('DOMContentLoaded', scheduleInit);
} else {
  console.log('[app.js] DOM already loaded, scheduling init immediately');
  scheduleInit();
}

console.log('[app.js] Script loaded');





async function loadAvailableYears() {
  const statusEl = document.getElementById('compare-status');
  const locQ = (typeof Query !== 'undefined' && Query.currentLocationQuery) ? Query.currentLocationQuery() : (document.getElementById('location-input') || {}).value;
  if (!locQ && !(window.currentLoc)) {
    if (statusEl) { statusEl.textContent = 'Set a location first to load available years.'; statusEl.className = 'upload-status error'; }
    return;
  }
  if (statusEl) { statusEl.textContent = 'Loading available years from STAC…'; statusEl.className = 'upload-status loading'; }
  try {
    const params = { location: locQ || (window.currentLoc && window.currentLoc.display_name) };
    if (window.currentLoc && window.currentLoc.bbox) {
      params.min_lon = window.currentLoc.bbox[0];
      params.min_lat = window.currentLoc.bbox[1];
      params.max_lon = window.currentLoc.bbox[2];
      params.max_lat = window.currentLoc.bbox[3];
    }
    const res = await API.availableYears(params);
    const years = res.years || [];
    ['compare-year-a', 'compare-year-b'].forEach(function(id) {
      const sel = document.getElementById(id);
      if (!sel) return;
      sel.innerHTML = '';
      if (!years.length) {
        sel.innerHTML = '<option value="">No years found</option>';
        return;
      }
      years.forEach(function(y) {
        const o = document.createElement('option');
        o.value = y; o.textContent = y;
        sel.appendChild(o);
      });
      if (id === 'compare-year-a' && years.length) sel.value = years[0];
      if (id === 'compare-year-b' && years.length) sel.value = years[years.length - 1];
    });
    if (statusEl) {
      statusEl.textContent = years.length ? ('Available years: ' + years[0] + '–' + years[years.length-1]) : 'No years with scenes for this AOI.';
      statusEl.className = years.length ? 'upload-status success' : 'upload-status error';
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = 'Load years error: ' + e.message; statusEl.className = 'upload-status error'; }
  }
}

async function onCompareDates() {
  const modeEl = document.querySelector('input[name="compare-mode"]:checked');
  const mode = modeEl ? modeEl.value : 'dates';
  const index = (document.getElementById('compare-index') || {}).value || null;
  const statusEl = document.getElementById('compare-status');
  const resDiv = document.getElementById('compare-result');
  const locQ = (typeof Query !== 'undefined' && Query.currentLocationQuery) ? Query.currentLocationQuery() : (document.getElementById('location-input') || {}).value;
  let aoi = null;
  try { aoi = (typeof getValidatedActiveAoi === 'function') ? getValidatedActiveAoi() : null; } catch (_) {}
  if (!locQ && !aoi && !(window.currentLoc)) {
    if (statusEl) { statusEl.textContent = 'Set a location or draw an AOI first.'; statusEl.className = 'upload-status error'; }
    return;
  }
  if (statusEl) { statusEl.textContent = 'Searching STAC…'; statusEl.className = 'upload-status loading'; }
  if (resDiv) { resDiv.classList.add('hidden'); resDiv.innerHTML = ''; }
  try {
    let result;
    if (mode === 'years') {
      const ya = (document.getElementById('compare-year-a') || {}).value;
      const yb = (document.getElementById('compare-year-b') || {}).value;
      if (!ya || !yb) {
        if (statusEl) { statusEl.textContent = 'Select Year A and Year B (use Refresh years if empty).'; statusEl.className = 'upload-status error'; }
        return;
      }
      const body = {
        year_a: parseInt(ya, 10),
        year_b: parseInt(yb, 10),
        location: locQ || (window.currentLoc && window.currentLoc.display_name) || undefined,
        aoi: aoi || undefined,
        index: index || undefined,
      };
      if (window.currentLoc && window.currentLoc.bbox) body.bbox = window.currentLoc.bbox;
      result = await API.compareYears(body);
    } else {
      const dateA = (document.getElementById('compare-date-a') || {}).value;
      const dateB = (document.getElementById('compare-date-b') || {}).value;
      if (!dateA || !dateB) {
        if (statusEl) { statusEl.textContent = 'Pick both Date A and Date B.'; statusEl.className = 'upload-status error'; }
        return;
      }
      const body = {
        date_a: dateA,
        date_b: dateB,
        location: locQ || (window.currentLoc && window.currentLoc.display_name) || undefined,
        aoi: aoi || undefined,
        index: index || undefined,
        window_days: 14,
        max_cloud: 40,
      };
      if (window.currentLoc && window.currentLoc.bbox) body.bbox = window.currentLoc.bbox;
      result = await API.compareDates(body);
    }
    if (statusEl) {
      statusEl.textContent = result.success ? 'Comparison complete.' : (result.message || 'Partial / no scenes');
      statusEl.className = result.success ? 'upload-status success' : 'upload-status error';
    }
    if (resDiv) {
      resDiv.classList.remove('hidden');
      const fmt = function(s, meta, label) {
        if (!s) {
          return '<div style="flex:1;min-width:180px"><strong>' + label + '</strong><br><em style="color:#f87171">' +
            ((meta && (meta.error || meta.reason)) || 'No scene') + '</em></div>';
        }
        return '<div style="flex:1;min-width:180px"><strong>' + label + '</strong><br>' +
          'Acquired: ' + (s.acquisition_date || s.datetime || s.acquired || '—') + '<br>' +
          'Cloud: ' + (s.cloud_cover_pct != null ? s.cloud_cover_pct + '%' : '—') + '<br>' +
          'Collection: ' + (s.collection || '—') + '<br>' +
          'ID: ' + (s.id || '—') + '</div>';
      };
      const labelA = mode === 'years' ? ('Year A (' + result.year_a + ')') : ('Date A (' + result.date_a + ')');
      const labelB = mode === 'years' ? ('Year B (' + result.year_b + ')') : ('Date B (' + result.date_b + ')');
      resDiv.innerHTML =
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">' +
        fmt(result.scene_a, result.meta_a, labelA) +
        fmt(result.scene_b, result.meta_b, labelB) +
        '</div>' +
        '<div style="font-size:0.85rem;margin-top:6px">' + (result.message || '') + '</div>' +
        (result.difference ? '<div style="font-size:0.8rem;opacity:0.85;margin-top:4px">Index: ' +
          (result.difference.index || '') + ' — ' + (result.difference.note || result.difference.status) + '</div>' : '');
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = 'Compare error: ' + e.message; statusEl.className = 'upload-status error'; }
  }
}

