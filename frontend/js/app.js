/**
 * SatQuery AI frontend application
 */
let lastAnalysis = null;
let currentLoc = null;
let currentUploadedImage = null;
let currentLandcoverCategory = 'Water';
let locationSearchInFlight = false;

async function boot() {
  MapUI.initMap();
  UI.setStatus('INITIALIZING');
  try {
    const st = await API.status();
    UI.setStatus(st.mode === 'REAL_DATA_MODE' ? 'DATA_CONNECTED' : 'PARTIAL_DATA');
    UI.renderSihStatus(st.sih_requirements);
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    console.error(e);
    document.getElementById('answer-text').textContent =
      'Backend not reachable. Start with: python run.py (port 8000)';
  }

  document.getElementById('btn-locate').addEventListener('click', onLocate);
  document.getElementById('btn-ask').addEventListener('click', onAsk);
  document.getElementById('btn-report').addEventListener('click', onReport);
  document.getElementById('btn-upload-image').addEventListener('click', onUploadImage);
  const compareBtn = document.getElementById('btn-compare-images');
  if (compareBtn) { compareBtn.addEventListener('click', onCompareImages); }
  const createAlertBtn = document.getElementById('btn-create-alert');
  if (createAlertBtn) { createAlertBtn.addEventListener('click', onAlertCreate); }
  const testAlertBtn = document.getElementById('btn-test-alert');
  if (testAlertBtn) { testAlertBtn.addEventListener('click', onAlertTest); }
  
  document.getElementById('btn-analyze-landcover').addEventListener('click', onAnalyzeLandcover);
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
        MapUI.showLandcoverOverlay({ success: true, ...currentUploadedImage, selected_category: currentLandcoverCategory, class: currentLandcoverCategory, bounds: currentUploadedImage.bounds, analysis_method: 'uploaded image bounds' });
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
}

async function onLocate() {
  if (locationSearchInFlight) return;
  const q = Query.currentLocationQuery();
  const locateButton = document.getElementById('btn-locate');
  if (!q) {
    UI.setLocationSearchStatus('Please enter a location.', 'error');
    return;
  }

  locationSearchInFlight = true;
  locateButton.disabled = true;
  MapUI.clearAreaSelection();
  setAreaControls(false);
  UI.setAreaStatus('Draw an area on the map');
  UI.setLocationSearchStatus('Searching location...', 'loading');
  UI.showProgress('Searching location...');
  try {
    const loc = await API.searchLocation(q);
    if (!loc || !loc.success || !Number.isFinite(Number(loc.lat)) || !Number.isFinite(Number(loc.lon))) {
      UI.setLocationSearchStatus('Location not found. Please enter a valid location.', 'error');
      return;
    }

    currentLoc = {
      ...loc,
      lat: Number(loc.lat),
      lon: Number(loc.lon),
    };
    const selectedLocation = currentLoc;
    window.__satquery_current_location = currentLoc;
    UI.setLocationInfo(currentLoc);
    MapUI.showLocation(currentLoc);
    UI.setLocationSearchStatus('Location found.', 'success');
    if (currentLoc.bbox) {
      MapUI.clearMapOverlays();
      MapUI.showLocation(currentLoc);
      UI.showProgress('Loading OSM water features…');
      try {
        const water = await API.waterFeatures(currentLoc.bbox);
        if (currentLoc === selectedLocation && water.success) MapUI.showOsmWater(water.features);
      } catch (_) { /* optional */ }
    }
    UI.setStatus('DATA_CONNECTED');
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    UI.setLocationSearchStatus('Location not found. Please enter a valid location.', 'error');
    console.error(e);
  } finally {
    UI.hideProgress();
    locateButton.disabled = false;
    locationSearchInFlight = false;
  }
}

async function syncManualAreaLocation() {
  const center = MapUI.getManualAoiCenter();
  if (!center) return;
  try {
    const location = await API.reverseLocation(center.lat, center.lon);
    if (location.success && location.display_name) {
      currentLoc = location;
      document.getElementById('location-input').value = location.display_name;
      UI.setLocationInfo({ ...location, aoi_area_km2: MapUI.areaKm2(MapUI.getManualAoi()) });
      UI.setAreaStatus(`Area Selected · ${MapUI.areaKm2(MapUI.getManualAoi()).toFixed(2)} km²`, 'success');
    } else {
      document.getElementById('location-input').value = `Selected area near ${center.lat.toFixed(5)}, ${center.lon.toFixed(5)}`;
    }
  } catch (error) {
    document.getElementById('location-input').value = `Selected area near ${center.lat.toFixed(5)}, ${center.lon.toFixed(5)}`;
    console.warn('Selected-area reverse geocoding unavailable:', error);
  }
}

let chatSessionId = null;
let currentImageId = null;

function appendChatBubble(role, content, meta) {
  const box = document.getElementById('chat-messages');
  if (!box) return;
  const div = document.createElement('div');
  div.className = 'chat-bubble ' + role;
  div.textContent = content;
  if (meta && (meta.confidence != null || meta.task)) {
    const m = document.createElement('div');
    m.className = 'chat-meta';
    m.textContent = [meta.task, meta.confidence != null ? ('conf ' + meta.confidence) : null].filter(Boolean).join(' · ');
    div.appendChild(m);
  }
  if (meta && meta.evidence && typeof meta.evidence === 'object') {
    const chips = document.createElement('div');
    Object.entries(meta.evidence).slice(0, 8).forEach(([k, v]) => {
      if (v == null) return;
      const c = document.createElement('span');
      c.className = 'evidence-chip';
      c.textContent = k + ': ' + v;
      chips.appendChild(c);
    });
    div.appendChild(chips);
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

async function onAsk() {
  const location = Query.currentLocationQuery();
  const question = Query.currentQuestion();
  if (!question) {
    document.getElementById('answer-text').textContent = 'Enter a question.';
    return;
  }
  if (!location && !currentImageId) {
    document.getElementById('answer-text').textContent = 'Enter a location or upload an image.';
    return;
  }
  const aoi = getValidatedActiveAoi();
  if (aoi === false) return;

  appendChatBubble('user', question, null);
  document.getElementById('question-input').value = '';
  UI.showProgress('Chat: routing & fetching real data…');
  try {
    const payload = {
      session_id: chatSessionId,
      message: question,
      location: location || undefined,
      image_id: currentImageId || undefined,
      aoi: aoi || undefined,
    };
    const result = await API.chatMessage(payload);
    chatSessionId = result.session_id || chatSessionId;

    appendChatBubble('assistant', result.content || result.answer_text || 'No answer', {
      task: result.task,
      confidence: result.confidence,
      evidence: result.evidence,
    });

    // Also drive the existing answer panel / map when analysis present
    const analysis = result.analysis || result;
    if (analysis && analysis.location) {
      lastAnalysis = analysis;
      currentLoc = analysis.location || currentLoc;
      UI.setLocationInfo(analysis.location);
      MapUI.showLocation(analysis.location);
    }
    if (MapUI.getManualAoi()) MapUI.fitManualAoi();
    MapUI.clearIndexLayer();

    const layers = result.map_layers || analysis.map_layers || {};
    if (layers.osm_water_features) MapUI.showOsmWater(layers.osm_water_features);
    if (layers.ndwi_water_points) MapUI.showIndexPoints(layers.ndwi_water_points, '#38bdf8', 'NDWI water sample');
    if (layers.ndwi_water_geojson) MapUI.showMaskGeoJSON(layers.ndwi_water_geojson, '#38bdf8', 'NDWI water region', 'water');
    if (layers.ndbi_points) MapUI.showIndexPoints(layers.ndbi_points, '#f97316', 'NDBI sample');
    if (layers.ndbi_geojson) MapUI.showMaskGeoJSON(layers.ndbi_geojson, '#f97316', 'NDBI built-up region', 'builtup');
    if (layers.vegetation_geojson) MapUI.showMaskGeoJSON(layers.vegetation_geojson, '#84cc16', 'NDVI vegetation region', 'vegetation');

    // Grounding polygons
    if (result.grounding && result.grounding.geojson) {
      MapUI.showMaskGeoJSON(result.grounding.geojson, '#22d3ee', 'Grounded region', result.grounding.target || 'ground');
    }

    // Image preview if available
    if (currentImageId) {
      const prev = document.getElementById('upload-preview');
      if (prev) {
        prev.src = API.imagePreviewUrl(currentImageId, 'rgb');
        prev.classList.remove('hidden');
      }
    }

    if (typeof UI.renderAnswer === 'function' && analysis.answer_text) {
      UI.renderAnswer(analysis);
    } else {
      const at = document.getElementById('answer-text');
      if (at) at.textContent = result.content || '';
    }
  } catch (e) {
    UI.setStatus('NO_CURRENT_DATA');
    appendChatBubble('assistant', 'Error: ' + e.message, null);
    const at = document.getElementById('answer-text');
    if (at) at.textContent = 'Analysis error: ' + e.message;
  } finally {
    UI.hideProgress();
  }
}

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

async function onUploadImage() {
  const input = document.getElementById('image-file-input');
  const file = input?.files && input.files[0];

  if (!file) {
    UI.setUploadMessage('Please choose a TIFF file first.', 'error');
    return;
  }

  const ext = file.name.split('.').pop()?.toLowerCase();
  if (!['tif', 'tiff', 'png', 'jpg', 'jpeg'].includes(ext)) {
    UI.setUploadMessage('Unsupported image type. Please upload a GeoTIFF (.tif/.tiff), PNG, or JPG.', 'error');
    return;
  }

  UI.showProgress('Uploading GeoTIFF…');
  UI.setUploadMessage('Uploading…', 'loading');

  try {
    const result = await API.uploadImage(file);
    currentUploadedImage = result;
    const statusMessage = `Image loaded successfully. CRS: ${result.crs || 'MISSING CRS'} · Bands: ${result.bands || 0} · Resolution: ${result.resolution ? `${Number(result.resolution.x).toFixed(6)} x ${Number(result.resolution.y).toFixed(6)}` : 'n/a'}`;
    UI.setUploadMessage(statusMessage, 'success');
    UI.renderImageMetadata(result);
    MapUI.showUploadedRaster(result);
    if (result.has_geospatial === false) {
      UI.setUploadMessage(result.warning || 'Image loaded, but geographic metadata is missing. Spatial features will be limited.', 'error');
    } else if (result.crs && result.crs.toUpperCase() === 'MISSING CRS') {
      UI.setUploadMessage('GeoTIFF loaded, but CRS is missing.', 'error');
    }
    if (result.image_id) {
      UI.setLandcoverStatus('Image ready for analysis.', 'success');
    }
  } catch (e) {
    UI.setUploadMessage(e.message || 'Upload failed.', 'error');
    UI.renderImageMetadata({ success: false });
    MapUI.clearUploadedRaster();
    console.error(e);
  } finally {
    UI.hideProgress();
  }
}

async function onAnalyzeLandcover() {
  const category = currentLandcoverCategory;
  if (!category || !['Water', 'Agriculture', 'Forest / Vegetation', 'Built-up'].includes(category)) {
    UI.setLandcoverStatus('Please select Water, Agriculture, Forest/Vegetation, or Built-up.', 'error');
    return;
  }

  if (!currentLoc && !currentUploadedImage && !MapUI.getManualAoi()) {
    UI.setLandcoverStatus('Search for a location before analyzing satellite data.', 'error');
    return;
  }

  const aoi = getValidatedActiveAoi();
  if (aoi === false) return;
  const analyzeButton = document.getElementById('btn-analyze-landcover');
  analyzeButton.disabled = true;
  UI.showProgress('Finding satellite imagery...');
  UI.setLandcoverStatus('Finding satellite imagery...', 'loading');

  const locationContext = currentLoc || (
    MapUI.getManualAoi()
      ? {
          bbox: [
            Math.min(...MapUI.getManualAoi().coordinates[0].map(([lon]) => lon)),
            Math.min(...MapUI.getManualAoi().coordinates[0].map(([, lat]) => lat)),
            Math.max(...MapUI.getManualAoi().coordinates[0].map(([lon]) => lon)),
            Math.max(...MapUI.getManualAoi().coordinates[0].map(([, lat]) => lat)),
          ],
        }
      : null
  );

  try {
    const result = await API.analyzeLandcover(
      currentUploadedImage?.image_id || null,
      category,
      aoi,
      locationContext
    );
    UI.renderLandcoverSummary(result);
    MapUI.showLandcoverOverlay(result);
    UI.setLandcoverStatus(`Analysis complete: ${category}.`, 'success');
  } catch (e) {
    UI.setLandcoverStatus(e.message || 'Land-cover analysis failed.', 'error');
    UI.renderLandcoverSummary({ success: false });
    MapUI.clearLandcoverOverlay();
  } finally {
    analyzeButton.disabled = false;
    UI.hideProgress();
  }
}

async function onCompareImages() {
  const beforeInput = document.getElementById('compare-before-input');
  const afterInput = document.getElementById('compare-after-input');
  const fileBefore = beforeInput?.files && beforeInput.files[0];
  const fileAfter = afterInput?.files && afterInput.files[0];

  if (!fileBefore || !fileAfter) {
    document.getElementById('compare-status').textContent = 'Please select both Before and After images.';
    document.getElementById('compare-status').className = 'upload-status error';
    return;
  }

  document.getElementById('compare-status').textContent = 'Uploading images...';
  document.getElementById('compare-status').className = 'upload-status loading';
  UI.showProgress('Uploading images for comparison...');

  try {
    const resBefore = await API.uploadImage(fileBefore);
    const resAfter = await API.uploadImage(fileAfter);
    
    document.getElementById('compare-status').textContent = 'Comparing images...';
    
    const compareRes = await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_before_id: resBefore.image_id,
        image_after_id: resAfter.image_id
      })
    }).then(r => r.json());
    
    if (compareRes.success) {
      document.getElementById('compare-status').textContent = 'Comparison complete.';
      document.getElementById('compare-status').className = 'upload-status success';
      
      const resDiv = document.getElementById('compare-result');
      resDiv.classList.remove('hidden');
      resDiv.innerHTML = `
        <div style="font-size: 0.85rem; line-height: 1.4;">
          <strong>Method:</strong> ${compareRes.method}<br>
          <strong>Changed Area:</strong> ${compareRes.stats.percentage_changed}% (${compareRes.stats.changed_pixels} px)<br>
          <em>${compareRes.report_summary}</em><br>
          <span style="color:var(--muted)">${compareRes.warning || compareRes.stats.vegetation_note || ''}</span>
        </div>
      `;
    } else {
      throw new Error(compareRes.error || compareRes.detail || 'Comparison failed');
    }
  } catch (e) {
    document.getElementById('compare-status').textContent = e.message || 'Comparison failed.';
    document.getElementById('compare-status').className = 'upload-status error';
    document.getElementById('compare-result').classList.add('hidden');
    console.error(e);
  } finally {
    UI.hideProgress();
  }
}

function getValidatedActiveAoi() {
  const validation = MapUI.validateManualAoi();
  if (validation.valid && !MapUI.isAreaDrawing()) return validation.aoi;
  if (MapUI.isAreaDrawing()) {
    UI.setAreaStatus('Finish or cancel the current area before analyzing.', 'error');
    return false;
  }
  if (MapUI.hasAreaPoints()) {
    UI.setAreaStatus(validation.error || 'Invalid area. Please redraw.', 'error');
    return false;
  }
  return null;
}

function setAreaControls(drawing) {
  document.getElementById('btn-select-area').classList.toggle('hidden', drawing);
  document.getElementById('btn-finish-area').classList.toggle('hidden', !drawing);
  document.getElementById('btn-cancel-area').classList.toggle('hidden', !drawing);
}

let lastCreatedAlertId = null;

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
  
  UI.showProgress('Creating alert...');
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
  
  UI.showProgress('Sending test alert...');
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

function startApp() {
  if (typeof MapUI?.initMap === 'function') {
    MapUI.initMap();
  }
  if (typeof boot === 'function') {
    boot();
  }
}

// Ensure startApp is globally accessible
window.startApp = startApp;
// boot will be called from initializeApp when ready

// Initialize immediately with error handling
function initializeApp() {
  try {
    console.log('[SatQuery] Initializing app...');
    if (typeof MapUI?.initMap === 'function') {
      console.log('[SatQuery] Calling MapUI.initMap()');
      MapUI.initMap();
    } else {
      console.warn('[SatQuery] MapUI.initMap not available');
    }
    
    if (typeof boot === 'function') {
      console.log('[SatQuery] Calling boot()');
      boot();
    } else {
      console.warn('[SatQuery] boot() not available');
    }
  } catch (error) {
    console.error('[SatQuery] Initialization error:', error);
  }
}

// Wait for DOM to be ready, with a delay to ensure all scripts are loaded
function scheduleInit() {
  // Use setTimeout to delay initialization slightly
  const timer = setTimeout(() => {
    console.log('[SatQuery] Running delayed initialization');
    initializeApp();
  }, 100);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', scheduleInit);
  console.log('[SatQuery] DOMContentLoaded listener registered');
} else {
  console.log('[SatQuery] DOM already loaded, scheduling init');
  scheduleInit();
}
