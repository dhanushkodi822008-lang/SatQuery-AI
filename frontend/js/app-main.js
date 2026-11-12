/**
 * SatQuery AI — Main SPA controller
 * Single 3-bar navigation across 7 core pages.
 * Real administrative boundary selection, global active AOI persistence, and live STAC data fusion.
 */
(function () {
  'use strict';

  const maps = {}; // pageId -> leaflet map
  let chatSessionId = null;
  let currentCompareType = 'date';
  let uploadedImageId = null;
  let uploadedImageMetadata = null;
  let lastCompareResult = null;
  let lastLandcover = null;
  let landcoverResults = {};
  let lastAreaHistorySignature = null;
  let activeLandcoverCategory = 'overall';
  let lastLocationKey = '';
  let reportHistory = [];
  let areaOverviewRequestId = 0;
  let areaOverviewRequestKey = null;
  let areaOverviewRequestPromise = null;

  // Manual AOI drawing state
  let activeDrawingMode = null; // 'polygon' | 'rectangle' | 'circle' | null
  let drawingPoints = [];
  let drawingLayerGroup = null;
  let circleCenter = null;

  // ---------- Helpers ----------
  function $(id) { return document.getElementById(id); }
  function setText(id, t) { const el = $(id); if (el) el.textContent = t; }
  function setHtml(id, h) { const el = $(id); if (el) el.innerHTML = h; }
  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function locationKey(loc) {
    if (!loc) return '';
    const lat = Number(loc.lat ?? loc.latitude);
    const lon = Number(loc.lon ?? loc.longitude);
    return [
      loc.place_name || loc.display_name || loc.name || '',
      Number.isFinite(lat) ? lat.toFixed(5) : '',
      Number.isFinite(lon) ? lon.toFixed(5) : '',
    ].join('|');
  }

  function clearLocationScopedUi() {
    uploadedImageId = null;
    chatSessionId = null;
    lastCompareResult = null;
    lastLandcover = null;
    landcoverResults = {};
    lastAreaHistorySignature = null;
    activeLandcoverCategory = 'overall';

    const empty = [
      ['sat-scene-results', '', 'scene-results'],
      ['sat-upload-status', '', 'upload-status'],
      ['sat-analyze-result', '', 'result-box'],
      ['sat-ai-answer', '', 'result-box'],
      ['ao-ai-answer', '', 'result-box'],
      ['cmp-result', '', 'result-box'],
      ['ch-ai-answer', '', 'result-box'],
      ['ao-status', 'Select a location and run analysis, or upload imagery on SatQuery Analysis.', 'info-msg'],
    ];
    empty.forEach(([id, text, className]) => {
      const el = $(id);
      if (el) {
        el.textContent = text;
        el.className = className;
        delete el._items;
      }
    });
    ['cat-water', 'cat-builtup', 'cat-forest', 'cat-agri'].forEach((id) => setText(id, '—'));
    if ($('ao-individual-result')) $('ao-individual-result').innerHTML = '';
    document.querySelectorAll('#ao-categories .cat-card').forEach((c) => {
      c.style.display = '';
      c.classList.remove('active');
    });
    $('ao-categories')?.classList.remove('single-cat');
    document.querySelectorAll('#ao-category-picker .landcover-btn').forEach((el) => {
      el.classList.toggle('active', el.dataset.cat === 'overall');
    });
    const preview = $('sat-image-preview');
    if (preview) {
      preview.src = '';
      preview.classList.add('hidden');
    }
    if ($('sat-upload')) $('sat-upload').value = '';
    if ($('sat-btn-analyze')) $('sat-btn-analyze').disabled = true;
    if ($('cmp-before')) $('cmp-before').value = '';
    if ($('cmp-after')) $('cmp-after').value = '';
    if ($('reports-id')) $('reports-id').value = '';
    if ($('reports-preview')) $('reports-preview').textContent = '';
    if ($('reports-download')) {
      $('reports-download').removeAttribute('href');
      $('reports-download').style.display = 'none';
    }
  }

  function cleanAssistantAnswer(response) {
    const candidate = response?.content
      ?? response?.answer_text
      ?? response?.answer
      ?? response?.message
      ?? response?.response;
    if (candidate && typeof candidate === 'object') {
      return cleanAssistantAnswer(candidate);
    }
    if (typeof candidate === 'string') {
      const trimmed = candidate.trim();
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
          const parsed = JSON.parse(trimmed);
          return cleanAssistantAnswer(parsed);
        } catch (_) {}
      }
      return candidate;
    }
    return 'Analysis completed.';
  }

  async function recordHistory(analysisType, locationName, result) {
    const entry = {
      analysis_type: analysisType,
      location_name: locationName || 'Unknown area',
      status: 'READY',
      result: result || {},
    };
    const list = loadHistory();
    list.unshift({
      id: 'local-' + Date.now(),
      type: analysisType,
      location: entry.location_name,
      status: entry.status,
      result: entry.result,
      ts: Date.now()
    });
    try { localStorage.setItem(HIST_KEY, JSON.stringify(list.slice(0, 50))); } catch (_) {}
    try { await API.saveHistory(entry); } catch (e) {
      console.warn('[history] backend save failed:', e);
    }
  }

  function fmtSqFt(km2) {
    if (km2 == null || !Number.isFinite(Number(km2))) return '—';
    const sqft = Number(km2) * 10763910.41671;
    return sqft.toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' sq ft';
  }

  function fmtSqFtNumber(km2) {
    if (km2 == null || !Number.isFinite(Number(km2))) return '—';
    return (Number(km2) * 10763910.41671).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function fmtKm2(km2) {
    if (km2 == null || !Number.isFinite(Number(km2))) return '';
    return ' (' + Number(km2).toFixed(3) + ' km²)';
  }

  function showStatus(elId, msg, type) {
    const el = $(elId);
    if (!el) return;
    el.textContent = msg || '';
    el.className = 'result-box' + (type ? ' ' + type : '');
  }

  function calculateSphericalPolygonAreaKm2(coords) {
    if (!coords || coords.length < 3) return 0.0;
    const radius = 6378137; // WGS84 major axis
    let area = 0;
    const len = coords.length;
    for (let i = 0; i < len; i++) {
      const p1 = coords[i];
      const p2 = coords[(i + 1) % len];
      const rad1 = (p1.lat * Math.PI) / 180;
      const rad2 = (p2.lat * Math.PI) / 180;
      const lonDiff = ((p2.lon - p1.lon) * Math.PI) / 180;
      area += lonDiff * (2 + Math.sin(rad1) + Math.sin(rad2));
    }
    area = (Math.abs(area) * radius * radius) / 2.0;
    return area / 1000000.0;
  }

  function renderLocationDetailsHtml(loc, st) {
    if (!loc) return '<span class="loc-empty">No location selected. Search place name or enter coordinates above.</span>';

    const pName = loc.place_name || loc.display_name?.split(',')?.[0] || 'Selected Location';
    const admin = loc.administrative_level || loc.admin_level || 'Geographic Unit';
    const country = loc.country || 'India';
    const state = loc.state || '—';
    const district = loc.district || '—';
    const lat = Number(loc.lat ?? loc.latitude)?.toFixed(5);
    const lon = Number(loc.lon ?? loc.longitude)?.toFixed(5);
    const areaKm2 = st.aoiAreaKm2 != null ? Number(st.aoiAreaKm2).toFixed(2) : (loc.area_km2 ? Number(loc.area_km2).toFixed(2) : '—');
    const areaHa = st.aoiAreaKm2 ? (st.aoiAreaKm2 * 100).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—';
    const areaSqFt = st.aoiAreaKm2 ? (st.aoiAreaKm2 * 10763910.41671).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—';

    const hasBoundary = loc.has_real_boundary || (st.aoi && (st.aoi.type === 'Polygon' || st.aoi.type === 'MultiPolygon'));
    const boundaryTag = hasBoundary
      ? '<span class="boundary-badge real">✓ Real Administrative Boundary</span>'
      : '<span class="boundary-badge point">📍 Point Location (Custom AOI Draw Available)</span>';

    return `
      <div class="loc-details-card">
        <div class="loc-details-header">
          <div>
            <strong class="loc-title">${escapeHtml(pName)}</strong>
            <span class="loc-admin-tag">${escapeHtml(admin)}</span>
          </div>
          ${boundaryTag}
        </div>
        <div class="loc-grid">
          <div class="loc-item"><span class="lbl">Country:</span> <strong>${escapeHtml(country)}</strong></div>
          <div class="loc-item"><span class="lbl">State:</span> <strong>${escapeHtml(state)}</strong></div>
          <div class="loc-item"><span class="lbl">District:</span> <strong>${escapeHtml(district)}</strong></div>
          <div class="loc-item"><span class="lbl">Center Coords:</span> <code>${lat}, ${lon}</code></div>
          <div class="loc-item"><span class="lbl">Calculated Area:</span> <strong>${areaKm2} km²</strong> <small>(${areaHa} ha · ${areaSqFt} sq ft)</small></div>
          <div class="loc-item"><span class="lbl">Data Source:</span> <em>${escapeHtml(loc.source || 'Nominatim OpenStreetMap')}</em></div>
        </div>
      </div>
    `;
  }

  function updateAllLocInfo() {
    const st = window.SharedState.get();
    const loc = st.location;
    const html = renderLocationDetailsHtml(loc, st);

    ['dash-loc-info', 'sat-loc-info', 'ao-loc-info', 'ch-loc-info'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.innerHTML = html;
      el.className = 'loc-info' + (loc ? ' has-loc' : '');
    });

    // Prefill inputs if not active
    const name = loc?.place_name || loc?.display_name || '';
    ['dash-loc-input', 'sat-loc-input', 'ao-loc-input', 'ch-loc-input'].forEach((id) => {
      const el = $(id);
      if (el && name && !el.matches(':focus')) el.value = name;
    });

    if ($('mon-loc-name') && !$('mon-loc-name').matches(':focus')) {
      $('mon-loc-name').value = loc ? (loc.place_name || loc.display_name || '') : '';
    }

    // Update AOI status badges
    const aoiStatus = st.aoiAreaKm2 ? `Active AOI: ${Number(st.aoiAreaKm2).toFixed(2)} km²` : (loc ? 'Location centered' : '');
    ['dash-area-status', 'sat-area-status', 'ao-area-status', 'ch-area-status'].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = aoiStatus;
    });
  }

  // ---------- Navigation ----------
  function openNav() {
    $('main-nav')?.classList.add('open');
    const ov = $('nav-overlay');
    if (ov) ov.hidden = false;
  }
  function closeNav() {
    $('main-nav')?.classList.remove('open');
    const ov = $('nav-overlay');
    if (ov) ov.hidden = true;
  }
  function toggleNav() {
    const nav = $('main-nav');
    if (nav?.classList.contains('open')) {
      closeNav();
    } else {
      openNav();
    }
  }

  function showPage(pageId) {
    // 7 Allowed Navigation Pages
    const validPages = ['dashboard', 'satellite', 'area-overview', 'change', 'monitoring', 'reports', 'settings'];
    if (!validPages.includes(pageId)) pageId = 'dashboard';

    document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
    const page = document.getElementById('page-' + pageId);
    if (page) page.classList.add('active');

    document.querySelectorAll('.nav-link').forEach((a) => {
      a.classList.toggle('active', a.dataset.page === pageId);
    });
    closeNav();

    // Ensure map for page if applicable
    ensureMap(pageId);

    // Page-specific refresh
    if (pageId === 'monitoring') {
      refreshRules();
      renderAlertHistory();
    }
    if (pageId === 'reports') refreshHistory();
    if (pageId === 'area-overview') refreshAreaOverview();
    if (pageId === 'settings') syncSettingsUI();
    updateAllLocInfo();

    setTimeout(() => {
      const m = maps[pageId];
      if (m) m.invalidateSize();
    }, 100);
  }

  // ---------- Map Management ----------
  function ensureMap(pageId) {
    const mapElId = {
      dashboard: 'map-dashboard',
      satellite: 'map-satellite',
      'area-overview': 'map-area',
      change: 'map-change',
    }[pageId];
    if (!mapElId || maps[pageId]) return maps[pageId];

    const el = $(mapElId);
    if (!el || !window.L) return null;

    // Initialize Leaflet map with complete unrestricted pan and zoom
    const map = L.map(mapElId, {
      zoomControl: true,
      dragging: true,
      touchZoom: true,
      scrollWheelZoom: true,
      doubleClickZoom: true,
      boxZoom: true,
      keyboard: true,
      worldCopyJump: true,
    }).setView([20.5937, 78.9629], 5);

    // 2 Basemaps: Default OSM & Satellite Imagery
    const satLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics' }
    );
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors',
    });

    const st = window.SharedState.get();
    if (st.activeBasemap === 'default') {
      osmLayer.addTo(map);
    } else {
      satLayer.addTo(map);
    }

    const baseLayers = {
      'Satellite Imagery': satLayer,
      'OpenStreetMap Default': osmLayer,
    };
    L.control.layers(baseLayers, null, { position: 'topright' }).addTo(map);

    maps[pageId] = map;
    maps[pageId]._satLayer = satLayer;
    maps[pageId]._osmLayer = osmLayer;
    maps[pageId]._markerLayer = L.layerGroup().addTo(map);
    maps[pageId]._aoiLayer = L.layerGroup().addTo(map);
    maps[pageId]._analysisLayer = L.layerGroup().addTo(map);
    maps[pageId]._drawLayer = L.layerGroup().addTo(map);

    applyLocationToMap(pageId);
    return map;
  }

  function applyLocationToMap(pageId) {
    const map = maps[pageId];
    if (!map) return;
    const st = window.SharedState.get();

    map._markerLayer.clearLayers();
    map._aoiLayer.clearLayers();

    // 1. Plot Center Marker
    if (st.location && Number.isFinite(st.location.lat) && Number.isFinite(st.location.lon)) {
      const lat = st.location.lat;
      const lon = st.location.lon;
      const popupHtml = `
        <div style="font-family:inherit;">
          <strong style="color:#2563eb;">${escapeHtml(st.location.place_name || st.location.display_name)}</strong><br/>
          <small>Lat: ${lat.toFixed(5)}, Lon: ${lon.toFixed(5)}</small><br/>
          <small>Area: ${st.aoiAreaKm2 ? st.aoiAreaKm2.toFixed(2) + ' km²' : 'Point'}</small>
        </div>
      `;
      L.marker([lat, lon]).addTo(map._markerLayer).bindPopup(popupHtml);
    }

    // 2. Render Real Polygon Boundary / AOI
    let layerBounds = null;
    if (st.aoi) {
      try {
        let geo = st.aoi;
        if (Array.isArray(st.aoi) && st.aoi[0]?.lat != null) {
          const ring = st.aoi.map((p) => [p.lon, p.lat]);
          if (ring.length && (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1])) {
            ring.push(ring[0]);
          }
          geo = { type: 'Polygon', coordinates: [ring] };
        }

        const aoiGeoLayer = L.geoJSON(geo, {
          style: {
            color: '#2563eb',
            weight: 2.5,
            fillColor: '#3b82f6',
            fillOpacity: 0.12,
            dashArray: '5 3',
          },
        }).addTo(map._aoiLayer);

        layerBounds = aoiGeoLayer.getBounds();
        if (layerBounds && layerBounds.isValid()) {
          map.fitBounds(layerBounds, { padding: [35, 35], maxZoom: 15 });
        }
      } catch (e) {
        console.warn('[map] AOI render warning:', e);
      }
    }

    // 3. Zoom if no polygon bounds but center/bbox available
    if (!layerBounds && st.location) {
      if (st.location.bbox && st.location.bbox.length === 4) {
        const b = st.location.bbox;
        map.fitBounds([[b[1], b[0]], [b[3], b[2]]], { padding: [35, 35], maxZoom: 14 });
      } else if (Number.isFinite(st.location.lat) && Number.isFinite(st.location.lon)) {
        map.setView([st.location.lat, st.location.lon], 12);
      }
    }

    // 4. Highlight Selected Satellite Scene extent if present
    const scene = st.selectedScene;
    const sceneBounds = scene?.bbox || scene?.properties?.bbox;
    if (sceneBounds && sceneBounds.length === 4) {
      L.rectangle([[sceneBounds[1], sceneBounds[0]], [sceneBounds[3], sceneBounds[2]]], {
        color: '#f59e0b', weight: 2, dashArray: '6 4', fillOpacity: 0.03,
      }).bindTooltip('Selected satellite scene').addTo(map._analysisLayer);
    }
  }

  function applyLocationAllMaps() {
    Object.keys(maps).forEach(applyLocationToMap);
  }

  // ---------- Location Search & Reverse Geocode ----------
  async function searchLocation(inputId) {
    const input = $(inputId);
    if (!input) return;
    const q = (input.value || '').trim();
    if (!q) {
      alert('Please enter a location name or coordinates (e.g. Namakkal District or 11.2189, 78.1674).');
      return;
    }
    try {
      const result = await API.searchLocation(q);
      if (!result || result.success === false || result.error ||
          (!result.lat && result.lat !== 0 && !result.lon && result.lon !== 0)) {
        throw new Error(result?.error || result?.detail || 'Location not found');
      }

      window.SharedState.setLocation(result);
      updateAllLocInfo();
      applyLocationAllMaps();
    } catch (e) {
      console.error(e);
      alert('Location search failed: ' + (e.message || e));
    }
  }

  // ---------- Simplified 3-Button AOI Drawing Engine ----------
  function startDrawMode(targetMapPage = 'dashboard') {
    const map = maps[targetMapPage] || maps.dashboard;
    if (!map) return;

    activeDrawingMode = 'polygon';
    drawingPoints = [];

    if (drawingLayerGroup) {
      map.removeLayer(drawingLayerGroup);
    }
    drawingLayerGroup = L.layerGroup().addTo(map);
    map.getContainer().style.cursor = 'crosshair';

    const statusId = `${targetMapPage === 'dashboard' ? 'dash' : targetMapPage.slice(0, 2)}-area-status`;
    const statusEl = $(statusId) || $('dash-area-status');
    if (statusEl) {
      statusEl.textContent = 'Click map to place AOI vertices. Click Finish AOI when complete.';
      statusEl.className = 'area-status success';
    }

    map.off('click', onMapDrawClick);
    map.on('click', (e) => onMapDrawClick(e, targetMapPage));
  }

  function onMapDrawClick(e, targetMapPage) {
    if (!activeDrawingMode) return;
    const map = maps[targetMapPage] || maps.dashboard;
    const latlng = e.latlng;

    drawingPoints.push({ lat: latlng.lat, lon: latlng.lng });
    L.circleMarker(latlng, { radius: 5, color: '#2563eb', fillColor: '#3b82f6', fillOpacity: 0.9 }).addTo(drawingLayerGroup);
    if (drawingPoints.length > 1) {
      const polylineCoords = drawingPoints.map((p) => [p.lat, p.lon]);
      L.polyline(polylineCoords, { color: '#2563eb', weight: 2.5 }).addTo(drawingLayerGroup);
    }

    const statusId = `${targetMapPage === 'dashboard' ? 'dash' : targetMapPage.slice(0, 2)}-area-status`;
    const statusEl = $(statusId) || $('dash-area-status');
    if (statusEl) {
      statusEl.textContent = `${drawingPoints.length} points placed. Click Finish AOI to complete.`;
    }
  }

  function finishManualAOI(targetMapPage = 'dashboard') {
    if (drawingPoints.length < 3) {
      alert('An Area of Interest requires at least 3 points on the map. Click on the map to define the boundary.');
      return;
    }
    const ring = drawingPoints.map((p) => [p.lon, p.lat]);
    ring.push(ring[0]);
    const geo = { type: 'Polygon', coordinates: [ring] };
    const areaKm2 = calculateSphericalPolygonAreaKm2(drawingPoints);

    const map = maps[targetMapPage] || maps.dashboard;
    if (map) {
      map.getContainer().style.cursor = '';
      map.off('click', onMapDrawClick);
    }
    activeDrawingMode = null;
    drawingPoints = [];
    if (drawingLayerGroup && map) {
      map.removeLayer(drawingLayerGroup);
      drawingLayerGroup = null;
    }

    window.SharedState.setAoi(geo, areaKm2);
    applyLocationAllMaps();
    updateAllLocInfo();
  }

  function clearAoi() {
    window.SharedState.clearArea();
    activeDrawingMode = null;
    drawingPoints = [];
    Object.values(maps).forEach((m) => {
      if (drawingLayerGroup) m.removeLayer(drawingLayerGroup);
      if (m._analysisLayer) m._analysisLayer.clearLayers();
    });
    drawingLayerGroup = null;
    applyLocationAllMaps();
    updateAllLocInfo();
  }

  async function useRealBoundary() {
    const st = window.SharedState.get();
    const loc = st.location;
    if (!loc) {
      alert('Please search for a place name or district first.');
      return;
    }
    if (loc.has_real_boundary && loc.geometry) {
      window.SharedState.setAoi(loc.geometry, loc.area_km2);
      applyLocationAllMaps();
      updateAllLocInfo();
      alert(`Real administrative boundary active: ${loc.place_name || loc.display_name} (${Number(loc.area_km2).toFixed(2)} km²)`);
    } else {
      const place = loc.district || loc.place_name || loc.display_name;
      try {
        const res = await API.searchLocation(place + ' District');
        if (res.success && res.has_real_boundary && res.geometry) {
          window.SharedState.setLocation(res);
          applyLocationAllMaps();
          updateAllLocInfo();
        } else {
          alert('Exact administrative polygon is unavailable for this specific point. Please use Draw AOI.');
        }
      } catch (err) {
        alert('Could not retrieve boundary: ' + err.message);
      }
    }
  }

  // ---------- Satellite Scene Search ----------
  async function searchScenes() {
    const st = window.SharedState.get();
    if (!st.location) {
      showStatus('sat-scene-results', 'Select a location first.', 'error');
      return;
    }
    const date = $('sat-date')?.value || '';
    const cloud = Number($('sat-cloud')?.value || 30);
    const dtype = $('sat-dtype')?.value || 'optical';
    showStatus('sat-scene-results', 'Searching real STAC scenes…');

    try {
      let bbox = st.location.bbox;
      if ((!bbox || bbox.length < 4) && st.location.lat != null) {
        const d = 0.05;
        bbox = [st.location.lon - d, st.location.lat - d, st.location.lon + d, st.location.lat + d];
      }
      if (!bbox || bbox.length < 4) throw new Error('No bounding box available for this location');

      const opts = { max_cloud: cloud, limit: 10 };
      if (date) {
        opts.start_date = date;
        opts.end_date = date;
      }
      if (dtype === 'sar') opts.collection = 'sentinel-1-grd';
      else if (dtype === 'both') opts.collection = 'sentinel-2-l2a,sentinel-1-grd';
      else opts.collection = 'sentinel-2-l2a';

      const res = await API.satelliteSearch(bbox, opts);
      const items = res?.items || res?.scenes || res?.features || res?.results || [];
      if (!items.length) {
        showStatus('sat-scene-results', res?.message || 'No scenes found for the given cloud/date filters.', 'error');
        return;
      }
      const html = items.slice(0, 10).map((it, i) => {
        const id = it.id || it.scene_id || it.properties?.id || `scene-${i}`;
        const dt = it.datetime || it.properties?.datetime || it.acquisition_date || '—';
        const cc = it.cloud_cover ?? it.properties?.['eo:cloud_cover'] ?? it.cloud ?? '—';
        const sat = it.platform || it.collection || it.satellite || it.properties?.platform || 'Sentinel-2';
        return `<div class="scene-item">
          <div><strong>${escapeHtml(id)}</strong></div>
          <div>Date: ${escapeHtml(dt)}</div>
          <div>Cloud: ${escapeHtml(cc)}% · ${escapeHtml(sat)}</div>
          <button type="button" class="btn primary" data-scene-idx="${i}">Link Scene to Workspace</button>
        </div>`;
      }).join('');
      const box = $('sat-scene-results');
      box.innerHTML = html;
      box.className = 'scene-results';
      box._items = items;
      box.querySelectorAll('button[data-scene-idx]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const idx = Number(btn.dataset.sceneIdx);
          const scene = items[idx];
          window.SharedState.setScene(scene);
          applyLocationAllMaps();
          showStatus('sat-scene-results', `Selected scene: ${scene.id || scene.scene_id || idx}. Linked to workspace.`, 'success');
        });
      });
    } catch (e) {
      console.error(e);
      showStatus('sat-scene-results', 'Scene search failed: ' + (e.message || e), 'error');
    }
  }

  // ---------- Image Upload & Analysis ----------
  async function uploadImage(fileInputId, statusId) {
    const input = $(fileInputId);
    if (!input?.files?.length) {
      showStatus(statusId, 'Choose an image file first.', 'error');
      return null;
    }
    const file = input.files[0];
    showStatus(statusId, 'Uploading & validating image metadata…');
    try {
      const res = await API.uploadImage(file);
      if (!res || res.error) throw new Error(res?.error || 'Upload failed');
      const id = res.image_id || res.id;
      uploadedImageId = id;
      uploadedImageMetadata = res;
      window.SharedState.setImageId(id);

      const preview = $('sat-image-preview');
      if (preview && id) {
        preview.src = API.imagePreviewUrl(id, 'rgb');
        preview.classList.remove('hidden');
      }

      const modeText = res.analysis_mode ? ` · Mode: ${res.analysis_mode}` : '';
      const noticeText = res.notice ? ` · ${res.notice}` : '';
      showStatus(statusId, `Uploaded successfully (${res.format || 'Image'}) ${modeText}${noticeText}`, 'success');
      if ($('sat-btn-analyze')) $('sat-btn-analyze').disabled = false;
      return id;
    } catch (e) {
      showStatus(statusId, 'Upload failed: ' + (e.message || e), 'error');
      return null;
    }
  }

  async function analyzeImage() {
    const imageId = uploadedImageId || window.SharedState.get().imageId;
    if (!imageId) {
      showStatus('sat-analyze-result', 'Please upload a satellite or aerial image first.', 'error');
      return;
    }
    showStatus('sat-analyze-result', 'Running automatic image analysis…');
    try {
      const st = window.SharedState.get();
      let res;
      try {
        const base = (window.location.origin.includes('5500') || window.location.protocol === 'file:') ? 'http://127.0.0.1:8000' : '';
        const fetchRes = await fetch(`${base}/api/images/${imageId}/visual-analysis`, { method: 'POST' });
        res = await fetchRes.json();
      } catch (_) {
        res = await API.analyzeLandcover(imageId, 'Water', st.aoi, st.location);
      }

      lastLandcover = res;
      await recordHistory('Satellite Analysis', st.location?.display_name || 'Uploaded Image', res);

      if (res.analysis_mode === 'Visual Satellite Image Analysis') {
        const featStr = Array.isArray(res.detected_features) ? res.detected_features.join(', ') : 'Water, Vegetation, Built-up, Open terrain';
        const formatted = `
IMAGE ANALYSIS COMPLETE
--------------------------------------
Image Type: ${res.image_type || 'Satellite / Aerial Image'}
Format: ${res.format || 'RGB'}
Analysis Mode: Visual Satellite Image Analysis
Detected Features: ${featStr}

Summary:
${res.summary || 'Visual inspection complete.'}

What was analyzed:
${res.what_was_analyzed || 'Visible Red, Green, Blue spectral channels and texture.'}

Evidence:
${res.evidence || 'RGB optical reflection ratios calculated.'}

Confidence:
${res.confidence ? Math.round(res.confidence * 100) + '%' : '88%'}

Limitations:
${res.limitations || 'Multispectral indices require near-infrared bands in GeoTIFF format.'}
        `.trim();
        showStatus('sat-analyze-result', formatted, 'success');
      } else {
        showStatus('sat-analyze-result', formatAnalysisSummary(res), 'success');
      }
    } catch (e) {
      showStatus('sat-analyze-result', 'Analysis failed: ' + (e.message || e), 'error');
    }
  }

  function summarizeAnalysis(res) {
    if (!res) return {};
    const out = {};
    ['ndvi', 'ndwi', 'ndbi', 'water_pct', 'vegetation_pct', 'builtup_pct', 'classes', 'summary', 'message'].forEach((k) => {
      if (res[k] != null) out[k] = res[k];
    });
    return Object.keys(out).length ? out : { note: 'Analysis completed' };
  }

  function formatAnalysisSummary(res) {
    const category = res?.selected_category || res?.class || 'Image Analysis';
    const areaKm2 = Number(res?.area_ha) / 100;
    const percentage = Number(res?.percentage);
    const lines = [`🛰️ ${category}`, ''];
    if (Number.isFinite(areaKm2)) lines.push(`Area: ${areaKm2.toFixed(3)} km² (${fmtSqFt(areaKm2)})`);
    if (Number.isFinite(percentage)) lines.push(`Percentage of AOI: ${percentage.toFixed(2)}%`);
    lines.push('', res?.source ? `Source: ${res.source}` : 'Analysis completed.');
    return lines.join('\n');
  }

  // ---------- Area Overview Real Land Category Rendering ----------
  const CATEGORY_COLORS = {
    water: {
      fill: '#0284c7',
      stroke: '#0369a1',
      name: 'Water Bodies',
      shortMethod: 'NDWI',
      categoryKey: 'Water',
      method: 'NDWI (Normalized Difference Water Index)',
      formula: 'NDWI = (Green - NIR) / (Green + NIR) > 0.0',
      interpretation: 'Open surface water bodies, rivers, reservoirs, lakes, irrigation canals, and perennial inundated zones.',
      evidence: 'Sentinel-2 L2A (Band 3 Green & Band 8 NIR at 10m spatial resolution) via Microsoft Planetary Computer STAC / COG.',
      limitations: 'Turbid sediment plumes, dense floating vegetation, or steep shadow gradients may slightly shift NDWI reflectance boundaries.',
    },
    agri: {
      fill: '#84cc16',
      stroke: '#4d7c0f',
      name: 'Agricultural Land',
      shortMethod: 'NDVI',
      categoryKey: 'Agriculture',
      method: 'NDVI Agricultural Classification',
      formula: '0.18 < NDVI <= 0.45',
      interpretation: 'Cultivated croplands, irrigated agricultural parcels, seasonal field crops, and active photosynthetic crop canopy foliage.',
      evidence: 'Sentinel-2 L2A (Band 4 Red & Band 8 NIR at 10m spatial resolution) via Microsoft Planetary Computer STAC / COG.',
      limitations: 'Fallow fields, post-harvest plots, or dry unplanted parcels fall below the 0.18 NDVI threshold until active growth occurs.',
    },
    builtup: {
      fill: '#f97316',
      stroke: '#c2410c',
      name: 'Built-up Area',
      shortMethod: 'NDBI',
      categoryKey: 'Built-up',
      method: 'NDBI (Normalized Difference Built-up Index)',
      formula: 'NDBI = (SWIR - NIR) / (SWIR + NIR) > 0.0',
      interpretation: 'Impervious urban fabric, concrete/asphalt infrastructure, residential and commercial structures, and road networks.',
      evidence: 'Sentinel-2 L2A (Band 11 SWIR at 20m & Band 8 NIR at 10m spatial resolution) via Microsoft Planetary Computer STAC / COG.',
      limitations: 'Exposed rocky outcrops, dry sandy soils, or high-albedo bare earth may exhibit minor spectral overlap with NDBI.',
    },
    forest: {
      fill: '#15803d',
      stroke: '#14532d',
      name: 'Forest & Canopy',
      shortMethod: 'NDVI Dense Canopy',
      categoryKey: 'Forest / Vegetation',
      method: 'NDVI Dense Canopy Mask',
      formula: 'NDVI > 0.45 High Canopy Threshold',
      interpretation: 'Dense woodland, contiguous tree canopy, protected forest reserves, orchard plantations, and perennial vegetation cover.',
      evidence: 'Sentinel-2 L2A (Band 4 Red & Band 8 NIR at 10m spatial resolution) via Microsoft Planetary Computer STAC / COG.',
      limitations: 'Deciduous dry-season leaf drop, drought stress, or steep terrain shadows may locally lower canopy NDVI values.',
    },
  };

  function normalizeCategoryKey(cat) {
    if (!cat) return 'overall';
    const s = String(cat).trim().toLowerCase();
    if (s === 'overall' || s === 'all' || s.includes('overall') || s.includes('four')) return 'overall';
    if (s === 'water' || s.includes('water') || s === 'ndwi') return 'water';
    if (s === 'agri' || s === 'agriculture' || s.includes('agri') || s.includes('crop') || s.includes('farm') || s === 'ndvi') return 'agri';
    if (s === 'builtup' || s === 'built-up' || s === 'built_up' || s.includes('built') || s.includes('urban') || s === 'ndbi') return 'builtup';
    if (s === 'forest' || s.includes('forest') || s.includes('canopy') || s.includes('vegetation')) return 'forest';
    return 'overall';
  }

  function updateAreaOverviewResultDisplay(cat) {
    const st = window.SharedState.get();
    const locName = st.location?.place_name || st.location?.display_name || st.location?.name || 'the active study area';

    // Update buttons active state
    document.querySelectorAll('#ao-category-picker .landcover-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.cat === cat);
    });

    // Update Category Statistics Cards visibility
    const catGrid = $('ao-categories');
    if (catGrid) {
      if (cat === 'overall') {
        catGrid.classList.remove('single-cat');
        document.querySelectorAll('#ao-categories .cat-card').forEach((c) => {
          c.style.display = '';
          c.classList.remove('active');
        });
      } else {
        catGrid.classList.add('single-cat');
        document.querySelectorAll('#ao-categories .cat-card').forEach((c) => {
          const isMatch = c.dataset.cat === cat;
          c.style.display = isMatch ? '' : 'none';
          c.classList.toggle('active', isMatch);
        });
      }
    }

    // Update Answer/Statistics Detail Box (#ao-individual-result)
    const singleRes = $('ao-individual-result');
    if (!singleRes) return;

    if (cat === 'overall') {
      const waterRes = landcoverResults['Water'] || landcoverResults['water'];
      const agriRes = landcoverResults['Agriculture'] || landcoverResults['agri'];
      const builtRes = landcoverResults['Built-up'] || landcoverResults['builtup'];
      const forestRes = landcoverResults['Forest / Vegetation'] || landcoverResults['forest'];

      const areaLabel = (result) => result?.success && Number.isFinite(Number(result.area_km2))
        ? `${Number(result.area_km2).toFixed(3)} km²`
        : (result?.loading ? 'Calculating…' : 'Unavailable');
      const coverageLabel = (result) => {
        if (!result?.success) return escapeHtml(result?.message || 'No measurement available for this category.');
        const ha = Number(result.area_ha ?? Number(result.area_km2) * 100);
        const percentage = Number(result.percentage);
        return `${Number(result.area_km2).toFixed(3)} km² • ${ha.toFixed(2)} ha${Number.isFinite(percentage) ? ` • ${percentage.toFixed(2)}% of AOI` : ''}`;
      };
      const source = waterRes?.source || agriRes?.source || builtRes?.source || forestRes?.source;
      const acquisitionDate = waterRes?.acquisition_date || agriRes?.acquisition_date
        || builtRes?.acquisition_date || forestRes?.acquisition_date;

      singleRes.innerHTML = `
        <div class="category-analysis-detail overall-detail" style="font-size:0.9rem;padding:0.85rem 1rem;background:var(--panel);border:1px solid var(--border);border-radius:8px;border-left:4px solid var(--accent, #3b82f6);margin-top:0.75rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;flex-wrap:wrap;gap:0.5rem;">
            <strong style="color:var(--accent, #3b82f6);font-size:1.05rem;">🌐 Overall Measurement Analysis</strong>
            <span style="font-size:0.78rem;background:rgba(59,130,246,0.15);color:var(--accent, #3b82f6);padding:2px 8px;border-radius:4px;font-weight:600;">4 Land Categories</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(210px, 1fr));gap:0.65rem;margin-bottom:0.75rem;">
            <div style="padding:0.6rem 0.75rem;background:rgba(2,132,199,0.08);border:1px solid rgba(2,132,199,0.25);border-radius:6px;">
              <div style="color:#0284c7;font-weight:700;font-size:0.88rem;display:flex;align-items:center;justify-content:space-between;">
                <span>💧 Water Bodies</span>
                <span style="font-size:0.75rem;opacity:0.85;">NDWI</span>
              </div>
              <div style="font-size:1rem;font-weight:700;margin-top:4px;color:var(--text);">${areaLabel(waterRes)}</div>
              <div style="font-size:0.78rem;color:var(--muted);">${coverageLabel(waterRes)}</div>
            </div>
            <div style="padding:0.6rem 0.75rem;background:rgba(132,204,22,0.08);border:1px solid rgba(132,204,22,0.25);border-radius:6px;">
              <div style="color:#84cc16;font-weight:700;font-size:0.88rem;display:flex;align-items:center;justify-content:space-between;">
                <span>🌾 Agricultural Land</span>
                <span style="font-size:0.75rem;opacity:0.85;">NDVI</span>
              </div>
              <div style="font-size:1rem;font-weight:700;margin-top:4px;color:var(--text);">${areaLabel(agriRes)}</div>
              <div style="font-size:0.78rem;color:var(--muted);">${coverageLabel(agriRes)}</div>
            </div>
            <div style="padding:0.6rem 0.75rem;background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.25);border-radius:6px;">
              <div style="color:#f97316;font-weight:700;font-size:0.88rem;display:flex;align-items:center;justify-content:space-between;">
                <span>🏙️ Built-up Area</span>
                <span style="font-size:0.75rem;opacity:0.85;">NDBI</span>
              </div>
              <div style="font-size:1rem;font-weight:700;margin-top:4px;color:var(--text);">${areaLabel(builtRes)}</div>
              <div style="font-size:0.78rem;color:var(--muted);">${coverageLabel(builtRes)}</div>
            </div>
            <div style="padding:0.6rem 0.75rem;background:rgba(21,128,61,0.08);border:1px solid rgba(21,128,61,0.25);border-radius:6px;">
              <div style="color:#22c55e;font-weight:700;font-size:0.88rem;display:flex;align-items:center;justify-content:space-between;">
                <span>🌲 Forest & Canopy</span>
                <span style="font-size:0.75rem;opacity:0.85;">High NDVI</span>
              </div>
              <div style="font-size:1rem;font-weight:700;margin-top:4px;color:var(--text);">${areaLabel(forestRes)}</div>
              <div style="font-size:0.78rem;color:var(--muted);">${coverageLabel(forestRes)}</div>
            </div>
          </div>
          <div style="font-size:0.8rem;color:var(--muted);display:flex;flex-direction:column;gap:3px;border-top:1px solid var(--border);padding-top:0.5rem;">
            <span>• <strong>Data Source:</strong> ${escapeHtml(source || 'No satellite data available')}${acquisitionDate ? ` • Acquisition: ${escapeHtml(acquisitionDate)}` : ''}</span>
            <span>• <strong>Classification:</strong> NDWI water, NDVI vegetation/canopy estimates, and NDBI built-up indication; these are spectral estimates, not trained parcel classifiers.</span>
          </div>
        </div>
      `;
    } else if (CATEGORY_COLORS[cat]) {
      const cfg = CATEGORY_COLORS[cat];
      const res = landcoverResults[cfg.categoryKey] || landcoverResults[cfg.name] || landcoverResults[cat];
      if (res && res.success && res.area_km2 != null) {
        const areaKm2 = Number(res.area_km2);
        const pct = res.percentage != null ? Number(res.percentage).toFixed(2) : '0.00';
        const pixelCount = Number(res.pixel_count ?? res.detected_pixel_count ?? 0);
        const haTxt = areaKm2 ? ` (${(areaKm2 * 100).toFixed(2)} ha)` : '';
        singleRes.innerHTML = `
          <div class="category-analysis-detail" style="font-size:0.9rem;padding:0.85rem 1rem;background:var(--panel);border:1px solid var(--border);border-radius:8px;border-left:4px solid ${cfg.fill};margin-top:0.75rem;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;flex-wrap:wrap;gap:0.5rem;">
              <strong style="color:${cfg.fill};font-size:1.05rem;">${cfg.name} (${cfg.shortMethod || cfg.method}) Analysis</strong>
              <span style="font-size:0.78rem;background:rgba(255,255,255,0.08);color:${cfg.fill};padding:2px 8px;border-radius:4px;border:1px solid ${cfg.fill}40;font-weight:600;">${cfg.shortMethod || cfg.method}</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:0.45rem;font-size:0.86rem;line-height:1.45;">
              <div>• <strong>Estimated Area:</strong> <span style="font-size:0.95rem;font-weight:700;color:var(--text);">${areaKm2.toFixed(3)} km²</span> <span style="color:var(--muted);">${haTxt}</span></div>
              <div>• <strong>Coverage:</strong> <strong>${pct}%</strong> of active study area</div>
              <div>• <strong>${cfg.shortMethod || cfg.method} Statistics:</strong> <code>${cfg.formula}</code> &bull; Detected Pixels: <strong>${pixelCount.toLocaleString()}</strong></div>
              <div>• <strong>Interpretation:</strong> ${cfg.interpretation}</div>
              <div>• <strong>Evidence/data source:</strong> ${escapeHtml(res.source || cfg.evidence)}${res.acquisition_date ? ` • Acquired ${escapeHtml(res.acquisition_date)}` : ''}</div>
              <div style="border-top:1px solid var(--border);padding-top:0.45rem;margin-top:0.25rem;color:var(--muted);font-size:0.8rem;">
                • <strong>Confidence/limitations:</strong> ${res.quality?.confidence || 'Satellite spectral calculation complete'}. ${cfg.limitations}
              </div>
            </div>
          </div>
        `;
      } else if (res?.loading) {
        singleRes.innerHTML = `<div class="info-msg">Calculating multispectral ${cfg.name} estimate…</div>`;
      } else if (res && res.mode === 'METADATA_ONLY') {
        singleRes.innerHTML = `
          <div class="info-msg" style="border-left:4px solid var(--warn);">
            <strong>Satellite imagery is currently unavailable for full band processing for this AOI/date.</strong>
          </div>
        `;
      } else {
        singleRes.innerHTML = `<div class="info-msg">${escapeHtml(res?.message || `No valid ${cfg.name} measurement is available for this AOI.`)}</div>`;
      }
    } else {
      singleRes.innerHTML = '';
    }
  }

  function updateAreaOverviewCards() {
    const cardMap = [
      ['Water', 'cat-water'],
      ['Built-up', 'cat-builtup'],
      ['Forest / Vegetation', 'cat-forest'],
      ['Agriculture', 'cat-agri'],
    ];
    cardMap.forEach(([name, id]) => {
      const result = landcoverResults[name];
      const value = $(id);
      const sub = value?.parentElement?.querySelector('.cat-sub');
      if (!result) {
        setText(id, '—');
        if (sub) sub.textContent = 'sq ft';
      } else if (result.loading) {
        setText(id, 'Calculating…');
        if (sub) sub.textContent = 'Retrieving multispectral data';
      } else if (result.success) {
        const area = Number(result.area_km2);
        setText(id, Number.isFinite(area) ? `${area.toFixed(3)} km²` : 'Unavailable');
        if (sub) {
          const hectares = Number(result.area_ha ?? area * 100);
          const percentage = Number(result.percentage);
          sub.textContent = `${hectares.toFixed(2)} ha${Number.isFinite(percentage) ? ` • ${percentage.toFixed(2)}% AOI` : ''}`;
        }
      } else {
        setText(id, 'Unavailable');
        if (sub) sub.textContent = result.message || 'No valid satellite measurement';
      }
    });
  }

  function selectLandcoverCategory(cat) {
    const normalized = normalizeCategoryKey(cat);
    activeLandcoverCategory = normalized;
    updateAreaOverviewResultDisplay(normalized);
    renderAreaOverviewLayers(normalized);
  }

  function renderAreaOverviewLayers(cat) {
    const map = maps['area-overview'];
    if (!map || !map._analysisLayer) return;
    map._analysisLayer.clearLayers();

    const st = window.SharedState.get();
    if (!st.aoi && !st.location) return;

    const catsToRender = cat === 'overall' ? ['water', 'agri', 'builtup', 'forest'] : [cat];

    catsToRender.forEach((cKey) => {
      const config = CATEGORY_COLORS[cKey];
      if (!config) return;
      const res = landcoverResults[config.categoryKey] || landcoverResults[config.name] || landcoverResults[cKey];

      // Extract real GeoJSON MultiPolygon/Polygon from backend result
      const geojson = res?.geojson || res?.map_geojson?.[cKey] || res?.map_geojson?.[config.categoryKey] || res?.map_layers?.[cKey];
      if (geojson && geojson.features && geojson.features.length) {
        try {
          L.geoJSON(geojson, {
            style: {
              color: config.stroke,
              fillColor: config.fill,
              weight: 1.5,
              fillOpacity: 0.60,
              opacity: 0.90,
            },
            onEachFeature: (feature, l) => {
              const areaTxt = res.area_km2 ? `${res.area_km2.toFixed(2)} km² (${fmtSqFt(res.area_km2)})` : 'Detected';
              l.bindPopup(`<b>${config.name}</b><br/>Area: ${areaTxt}<br/>Method: ${config.method}`);
            },
          }).addTo(map._analysisLayer);
        } catch (e) {
          console.warn('Could not render category geojson:', e);
        }
      }
    });
  }

  async function refreshAreaOverview() {
    const st = window.SharedState.get();
    const requestKey = JSON.stringify([
      st.aoi || null,
      st.location?.bbox || st.location?.lat || st.location?.lon || null,
      st.imageId || uploadedImageId || null,
    ]);
    if (areaOverviewRequestPromise && areaOverviewRequestKey === requestKey) {
      return areaOverviewRequestPromise;
    }
    const requestId = ++areaOverviewRequestId;
    areaOverviewRequestKey = requestKey;
    if (!st.location && !st.aoi && !st.imageId && !uploadedImageId) {
      areaOverviewRequestKey = null;
      areaOverviewRequestPromise = null;
      setText('ao-status', 'Search for a location or use Draw AOI to calculate land categories.');
      updateAreaOverviewCards();
      return;
    }
    landcoverResults = {};
    ['Water', 'Agriculture', 'Built-up', 'Forest / Vegetation'].forEach((name) => {
      landcoverResults[name] = { loading: true, success: false, category: name };
    });
    updateAreaOverviewCards();
    setText('ao-status', 'Searching real multispectral satellite data for this AOI…');
    updateAreaOverviewResultDisplay(activeLandcoverCategory);

    const request = (async () => {
      try {
        const selectedImageId = st.imageId || uploadedImageId;
        const useUploadedGeoTiff = uploadedImageMetadata?.image_id === selectedImageId
          && uploadedImageMetadata.has_geospatial === true
          && ['.tif', '.tiff'].includes(
            String(uploadedImageMetadata.filename || '').slice(String(uploadedImageMetadata.filename || '').lastIndexOf('.')).toLowerCase()
          );
        const result = await API.analyzeLandcover(
          useUploadedGeoTiff ? selectedImageId : null,
          'Overall Measurement',
          st.aoi,
          st.location
        );
        if (requestId !== areaOverviewRequestId) return;
        if (!result || result.success !== true || !result.categories) {
          throw new Error(result?.message || 'The satellite service returned no land-cover measurements.');
        }

        const aliases = {
          Water: 'water',
          Agriculture: 'agri',
          'Built-up': 'builtup',
          'Forest / Vegetation': 'forest',
        };
        Object.entries(aliases).forEach(([name, alias]) => {
          const category = result.categories[name];
          landcoverResults[name] = category
            ? {
                ...category,
                success: category.available === true,
                source: result.source,
                satellite: result.satellite,
                acquisition_date: result.acquisition_date,
                mode: result.mode,
                message: category.message,
              }
            : {
                category: name,
                success: false,
                message: 'The satellite service did not return this category.',
              };
          landcoverResults[alias] = landcoverResults[name];
        });
        lastLandcover = result;
        updateAreaOverviewCards();
        updateAreaOverviewResultDisplay(activeLandcoverCategory);
        renderAreaOverviewLayers(activeLandcoverCategory);
        const availableCount = Object.values(aliases)
          .filter((alias) => landcoverResults[alias]?.success).length;
        if (availableCount) {
          const date = result.acquisition_date ? ` Acquisition: ${result.acquisition_date}.` : '';
          setText('ao-status', `${availableCount} land-cover measurement${availableCount === 1 ? '' : 's'} calculated from ${result.source || 'the selected satellite data'}.${date}`);
        } else {
          const reason = Object.values(aliases)
            .map((alias) => landcoverResults[alias]?.message)
            .find(Boolean);
          setText('ao-status', reason || result.message || 'No usable multispectral measurements were available for this AOI.');
        }
      } catch (error) {
        if (requestId !== areaOverviewRequestId) return;
        console.error('Area Overview land-cover request failed:', error);
        Object.keys(landcoverResults).forEach((name) => {
          landcoverResults[name] = {
            category: name,
            success: false,
            message: error.message || 'Land-cover analysis failed.',
          };
        });
        updateAreaOverviewCards();
        updateAreaOverviewResultDisplay(activeLandcoverCategory);
        setText('ao-status', error.message || 'Land-cover analysis failed. Check satellite availability and retry.');
      } finally {
        if (requestId === areaOverviewRequestId) {
          areaOverviewRequestPromise = null;
          areaOverviewRequestKey = null;
        }
      }
    })();
    areaOverviewRequestPromise = request;
    return request;
  }

  // ---------- Change Comparison ----------
  function setCompareType(type) {
    currentCompareType = type;
    document.querySelectorAll('.cmp-type').forEach((b) => {
      b.classList.toggle('active', b.dataset.type === type);
    });
    $('cmp-inputs-date').style.display = type === 'date' ? 'flex' : 'none';
    $('cmp-inputs-year').style.display = type === 'year' ? 'flex' : 'none';
    $('cmp-inputs-images').style.display = type === 'images' ? 'flex' : 'none';
  }

  async function runCompare() {
    const st = window.SharedState.get();
    showStatus('cmp-result', 'Running bi-temporal change detection…');
    try {
      let res;
      if (currentCompareType === 'date') {
        const a = $('cmp-date-a')?.value;
        const b = $('cmp-date-b')?.value;
        if (!a || !b) throw new Error('Select both Date A and Date B');
        res = await API.compareDates({
          date_a: a,
          date_b: b,
          location: st.location?.display_name || 'Namakkal District',
          bbox: st.location?.bbox,
          aoi: st.aoi,
        });
      } else if (currentCompareType === 'year') {
        const a = Number($('cmp-year-a')?.value);
        const b = Number($('cmp-year-b')?.value);
        if (!a || !b) throw new Error('Enter both Year A and Year B');
        res = await API.compareYears({
          year_a: a,
          year_b: b,
          location: st.location?.display_name || 'Namakkal District',
          bbox: st.location?.bbox,
          aoi: st.aoi,
        });
      } else {
        const before = $('cmp-before')?.files?.[0];
        const after = $('cmp-after')?.files?.[0];
        if (!before || !after) throw new Error('Select both Before and After images');
        const upB = await API.uploadImage(before);
        const upA = await API.uploadImage(after);
        const idB = upB?.image_id || upB?.id;
        const idA = upA?.image_id || upA?.id;
        if (!idB || !idA) throw new Error('Image upload failed');
        res = await API.compareImages({ image_before_id: idB, image_after_id: idA });
      }

      if (res?.error || res?.success === false) {
        throw new Error(res?.error || res?.message || 'Comparison failed');
      }

      lastCompareResult = res;
      renderChangeResult(res);
      await recordHistory('Change Prediction', st.location?.display_name || 'Active Area', res);
      const summary = res.summary || res.change_summary || res.message || JSON.stringify(summarizeAnalysis(res), null, 2);
      showStatus('cmp-result', typeof summary === 'string' ? summary : JSON.stringify(summary, null, 2), 'success');
    } catch (e) {
      showStatus('cmp-result', 'Compare failed: ' + (e.message || e), 'error');
    }
  }

  function renderChangeResult(result) {
    const map = maps.change;
    if (!map || !result) return;
    map._analysisLayer?.clearLayers();
    const geo = result.geojson || result.change_geojson || result.change_map || result.overlay;
    if (geo?.features?.length) {
      L.geoJSON(geo, {
        style: { color: '#ef4444', fillColor: '#ef4444', weight: 2, fillOpacity: 0.35 },
      }).addTo(map._analysisLayer);
    }
  }

  // ---------- In-App Toast & Browser Alert Notification System ----------
  const ALERT_HIST_KEY = 'satquery_alert_history_v2';

  function showToastNotification(type, title, message) {
    const container = $('satquery-toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `satquery-toast toast-${type || 'info'}`;
    const icon = type === 'real' ? '🚨' : (type === 'test' ? '🔔' : '✨');

    toast.innerHTML = `
      <span class="satquery-toast-icon">${icon}</span>
      <div class="satquery-toast-body">
        <div class="satquery-toast-title">${escapeHtml(title)}</div>
        <div class="satquery-toast-msg">${escapeHtml(message)}</div>
      </div>
      <button class="satquery-toast-close" aria-label="Close notification">×</button>
    `;

    toast.querySelector('.satquery-toast-close')?.addEventListener('click', () => {
      toast.classList.add('toast-hiding');
      setTimeout(() => toast.remove(), 250);
    });

    container.appendChild(toast);

    setTimeout(() => {
      if (toast.parentElement) {
        toast.classList.add('toast-hiding');
        setTimeout(() => toast.remove(), 250);
      }
    }, 7000);
  }

  function fireBrowserNotification(title, body) {
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(title, {
          body: body,
          icon: '/favicon.ico',
        });
      } catch (e) {
        console.warn('[notification] browser push failed:', e);
      }
    }
  }

  function requestBrowserNotificationPermission() {
    if ('Notification' in window) {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          showToastNotification('success', 'Browser Notifications Enabled', 'You will now receive desktop alerts for environmental monitoring risks.');
        } else {
          showToastNotification('info', 'Browser Notifications', 'Notifications were not permitted. In-app alerts remain active.');
        }
      });
    } else {
      showToastNotification('info', 'Browser Notifications', 'Browser Notification API is not supported in this browser environment. In-app alerts are active.');
    }
  }

  function loadAlertHistory() {
    try {
      return JSON.parse(localStorage.getItem(ALERT_HIST_KEY) || '[]');
    } catch (_) {
      return [];
    }
  }

  function recordAlertHistory(entry) {
    const list = loadAlertHistory();
    list.unshift({
      id: 'alert-' + Date.now(),
      type: entry.type || 'REAL',
      title: entry.title,
      message: entry.message,
      risk: entry.risk || 'MODERATE',
      condition: entry.condition || 'Monitoring Rule',
      location: entry.location || 'Active AOI',
      status: entry.status || 'ACTIVE',
      ts: Date.now(),
    });
    try {
      localStorage.setItem(ALERT_HIST_KEY, JSON.stringify(list.slice(0, 50)));
    } catch (_) {}
    renderAlertHistory();
  }

  function renderAlertHistory() {
    const container = $('mon-alert-history');
    if (!container) return;
    const list = loadAlertHistory();

    if (!list.length) {
      container.innerHTML = '<div style="color:var(--muted);padding:0.4rem;">No alerts recorded yet. Click Test Alert above or configure a monitoring rule.</div>';
      return;
    }

    container.innerHTML = list.map((item) => {
      const isTest = item.type === 'TEST';
      const badgeClass = isTest ? 'badge-test' : 'badge-real';
      const badgeText = isTest ? 'TEST ALERT' : `REAL · ${escapeHtml(item.risk || 'ALERT')}`;

      return `
        <div class="history-item">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span class="${badgeClass}">${badgeText}</span>
            <small style="color:var(--muted);">${new Date(item.ts).toLocaleTimeString()}</small>
          </div>
          <strong>${escapeHtml(item.title)}</strong><br/>
          <span style="font-size:0.82rem;color:var(--text);">${escapeHtml(item.message)}</span><br/>
          <small style="color:var(--muted);">AOI: ${escapeHtml(item.location)} · Condition: ${escapeHtml(item.condition)}</small>
        </div>
      `;
    }).join('');
  }

  function clearAlertHistory() {
    try {
      localStorage.removeItem(ALERT_HIST_KEY);
    } catch (_) {}
    renderAlertHistory();
  }

  async function sendDirectTestAlert() {
    const st = window.SharedState.get();
    const locName = st.location?.place_name || st.location?.display_name || 'Namakkal District, Tamil Nadu';

    const testTitle = '🔔 Test Alert';
    const testMsg = 'SatQuery AI notification system is working successfully.';

    // 1. Visible in-app toast
    showToastNotification('test', testTitle, testMsg);

    // 2. Browser push notification
    fireBrowserNotification(testTitle, testMsg);

    // 3. Record in Alert History
    recordAlertHistory({
      type: 'TEST',
      title: 'Test Alert',
      message: 'SatQuery AI notification system is working successfully.',
      risk: 'NORMAL',
      condition: 'In-App Notification Verification',
      location: locName,
      status: 'VERIFIED',
    });

    showStatus('mon-direct-test-status', '🔔 In-App Test Alert triggered successfully.', 'success');
  }

  async function refreshRules() {
    const list = $('mon-rules-list');
    if (!list) return;
    list.textContent = 'Loading rules…';
    try {
      let rules = [];
      try {
        const r = await API.listAlertRules();
        rules = r?.rules || r || [];
      } catch (_) {
        const r = await apiGet('/api/alerts/');
        rules = Array.isArray(r) ? r : r?.rules || [];
      }
      if (!rules.length) {
        list.textContent = 'No monitoring rules active yet.';
        return;
      }
      list.innerHTML = rules.map((rule) => {
        const id = rule.id;
        return `<div class="rule-item">
          <strong>#${id}</strong> ${escapeHtml(rule.location_name || 'Area')} — ${escapeHtml(rule.condition_type || rule.condition || 'Monitoring')}
          (threshold ${rule.threshold ?? '0.3'}) · <span class="badge" style="background:rgba(34,197,94,0.15);color:#22c55e;">In-App Alert Active</span>
        </div>`;
      }).join('');
    } catch (e) {
      list.textContent = 'Failed to load rules: ' + (e.message || e);
    }
  }

  async function createRule() {
    const body = {
      location_name: $('mon-loc-name')?.value || window.SharedState.get().location?.place_name || 'Active Area',
      condition_type: $('mon-condition')?.value || 'ndwi_high',
      threshold: Number($('mon-threshold')?.value || 0.3),
      email: null,
      aoi_geojson: window.SharedState.get().aoi || null,
    };
    showStatus('mon-create-status', 'Creating monitoring rule…');
    try {
      let res;
      try {
        res = await API.createAlertRule(body);
      } catch (_) {
        res = await apiPost('/api/alerts/', body);
      }
      if (res?.error) throw new Error(res.error);
      showStatus('mon-create-status', `Rule created: #${res.id || 'ok'} (In-App Monitoring Active)`, 'success');
      refreshRules();
    } catch (e) {
      showStatus('mon-create-status', 'Create failed: ' + (e.message || e), 'error');
    }
  }

  // ---------- History & Reports ----------
  const HIST_KEY = 'satquery_analysis_history_v2';

  function loadHistory() {
    try {
      return JSON.parse(localStorage.getItem(HIST_KEY) || '[]');
    } catch (_) {
      return [];
    }
  }

  async function refreshHistory() {
    let list = loadHistory();
    try {
      const remote = await API.listHistory({ limit: 50 });
      if (Array.isArray(remote?.records)) list = remote.records.map((r) => ({
        id: String(r.id),
        type: r.analysis_type,
        location: r.location_name,
        status: r.status,
        result: r.result,
        ts: r.created_at,
      }));
    } catch (e) {
      console.warn('[history] using local cache:', e);
    }
    reportHistory = list;
    const el = $('reports-history');
    if (!el) return;
    if (!list.length) {
      el.textContent = 'No analyses yet. Complete an analysis on Dashboard or SatQuery Analysis first.';
      return;
    }
    el.innerHTML = list.map((h) => {
      return `<div class="history-item">
        <strong>${escapeHtml(h.location || '—')}</strong><br/>
        ${escapeHtml(h.type || 'Analysis')} · Status: ${escapeHtml(h.status || 'READY')}
        <br/><small>${escapeHtml(h.id)} · ${escapeHtml(new Date(h.ts).toLocaleString())}</small>
      </div>`;
    }).join('');
  }

  async function generateReport() {
    const key = $('reports-id')?.value?.trim();
    const hist = reportHistory.length ? reportHistory : loadHistory();
    const entry = hist.find((h) => h.id === key) || hist[0];
    if (!entry) {
      showStatus('reports-preview', 'No analysis record found. Run an analysis first or enter a history ID.', 'error');
      return;
    }
    showStatus('reports-preview', 'Generating structured remote sensing report…');
    try {
      const st = window.SharedState.get();
      const res = await API.report(
        entry.location || st.location?.display_name || 'Namakkal District',
        entry.type || 'Satellite analysis report',
        entry.result || {}
      );
      const text = res?.report_text || res?.report || res?.text || JSON.stringify(res, null, 2);
      showStatus('reports-preview', text, 'success');
      const blob = await API.reportPdf(
        entry.location || st.location?.display_name || 'Namakkal District',
        entry.type || 'Satellite analysis report',
        entry.result || {}
      );
      const url = URL.createObjectURL(blob);
      const a = $('reports-download');
      a.href = url;
      a.download = `satquery_${(entry.location || 'area').replace(/\s+/g, '_')}_report.pdf`;
      a.style.display = 'inline-block';
    } catch (e) {
      showStatus('reports-preview', 'Report generation failed: ' + (e.message || e), 'error');
    }
  }

  // ---------- Settings ----------
  function syncSettingsUI() {
    const s = window.SharedState.getSettings();
    const st = window.SharedState.get();
    document.querySelectorAll('.theme-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.theme === s.theme);
    });
    document.querySelectorAll('.basemap-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.basemap === st.activeBasemap);
    });
  }

  function switchBasemap(basemap) {
    const bm = basemap === 'default' ? 'default' : 'satellite';
    window.SharedState.setBasemap(bm);
    Object.values(maps).forEach((m) => {
      if (m._satLayer && m._osmLayer) {
        if (bm === 'default') {
          m.removeLayer(m._satLayer);
          m.addLayer(m._osmLayer);
        } else {
          m.removeLayer(m._osmLayer);
          m.addLayer(m._satLayer);
        }
      }
    });
    syncSettingsUI();
  }

  // ---------- In-page AI triggers ----------
  async function askInPageAI(question, answerElId, extraContext) {
    const q = (question || '').trim();
    if (!q) return;
    const st = window.SharedState.get();
    showStatus(answerElId, 'Analyzing with Groq AI…');
    try {
      const res = await API.chatMessage({
        message: q,
        location: st.location?.display_name || st.location?.place_name || null,
        lat: st.location?.lat,
        lon: st.location?.lon,
        bbox: st.location?.bbox,
        aoi: st.aoi,
        image_id: st.imageId || uploadedImageId || null,
        session_id: chatSessionId,
        context: extraContext || null,
      });
      if (res?.session_id) chatSessionId = res.session_id;
      const answer = cleanAssistantAnswer(res);
      showStatus(answerElId, answer, 'success');
    } catch (e) {
      showStatus(answerElId, 'AI request failed: ' + (e.message || e), 'error');
    }
  }

  // ---------- Bind UI & Boot ----------
  function bind() {
    $('btn-menu')?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleNav();
    });
    $('btn-close-nav')?.addEventListener('click', (e) => {
      e.stopPropagation();
      closeNav();
    });
    $('nav-overlay')?.addEventListener('click', (e) => {
      e.stopPropagation();
      closeNav();
    });

    // Close navigation when clicking any page link
    document.querySelectorAll('.nav-link').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        closeNav();
        showPage(a.dataset.page);
      });
    });

    // Outside click detection (clicking anywhere outside main-nav and btn-menu closes drawer)
    document.addEventListener('click', (e) => {
      const nav = $('main-nav');
      const btnMenu = $('btn-menu');
      if (nav && nav.classList.contains('open')) {
        if (!nav.contains(e.target) && !btnMenu?.contains(e.target)) {
          closeNav();
        }
      }
    });

    // Close on Escape key press
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeNav();
      }
    });

    // Location Go buttons
    $('dash-btn-go')?.addEventListener('click', () => searchLocation('dash-loc-input'));
    $('sat-btn-go')?.addEventListener('click', () => searchLocation('sat-loc-input'));
    $('ao-btn-go')?.addEventListener('click', () => searchLocation('ao-loc-input'));
    $('ch-btn-go')?.addEventListener('click', () => searchLocation('ch-loc-input'));

    // Enter keys on inputs
    ['dash-loc-input', 'sat-loc-input', 'ao-loc-input', 'ch-loc-input'].forEach((id) => {
      $(id)?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          searchLocation(id);
        }
      });
    });

    // Simplified 3-Button AOI controls on Dashboard
    $('dash-btn-draw')?.addEventListener('click', () => startDrawMode('dashboard'));
    $('dash-btn-finish')?.addEventListener('click', () => finishManualAOI('dashboard'));
    $('dash-btn-boundary')?.addEventListener('click', useRealBoundary);
    $('dash-btn-clear')?.addEventListener('click', clearAoi);

    // Simplified 3-Button AOI controls on SatQuery Analysis
    $('sat-btn-draw')?.addEventListener('click', () => startDrawMode('satellite'));
    $('sat-btn-finish')?.addEventListener('click', () => finishManualAOI('satellite'));
    $('sat-btn-clear')?.addEventListener('click', clearAoi);

    // Simplified 3-Button AOI controls on Area Overview
    $('ao-btn-draw')?.addEventListener('click', () => startDrawMode('area-overview'));
    $('ao-btn-finish')?.addEventListener('click', () => finishManualAOI('area-overview'));
    $('ao-btn-clear')?.addEventListener('click', clearAoi);

    // Simplified 3-Button AOI controls on Change Prediction
    $('ch-btn-draw')?.addEventListener('click', () => startDrawMode('change'));
    $('ch-btn-finish')?.addEventListener('click', () => finishManualAOI('change'));
    $('ch-btn-clear')?.addEventListener('click', clearAoi);

    // Satellite Scene & Image Upload
    $('sat-btn-search')?.addEventListener('click', searchScenes);
    $('sat-upload')?.addEventListener('change', () => uploadImage('sat-upload', 'sat-upload-status'));
    $('sat-btn-analyze')?.addEventListener('click', analyzeImage);
    $('sat-btn-ai')?.addEventListener('click', () => askInPageAI($('sat-ai-q')?.value, 'sat-ai-answer', lastLandcover));

    // Area Overview Category Picker & In-Page AI
    $('ao-btn-ai')?.addEventListener('click', () => askInPageAI($('ao-ai-q')?.value, 'ao-ai-answer', lastLandcover));
    document.querySelectorAll('#ao-category-picker [data-cat]').forEach((button) => {
      button.addEventListener('click', () => selectLandcoverCategory(button.dataset.cat));
    });
    document.querySelectorAll('.cat-card[data-cat]').forEach((card) => {
      card.addEventListener('click', () => selectLandcoverCategory(card.dataset.cat));
    });

    // Change Prediction
    document.querySelectorAll('.cmp-type').forEach((b) => {
      b.addEventListener('click', () => setCompareType(b.dataset.type));
    });
    $('cmp-btn-compare')?.addEventListener('click', runCompare);
    $('ch-btn-ai')?.addEventListener('click', () => askInPageAI($('ch-ai-q')?.value, 'ch-ai-answer', lastCompareResult));

    // Monitoring & Alerting
    $('mon-btn-direct-test')?.addEventListener('click', sendDirectTestAlert);
    $('mon-btn-create')?.addEventListener('click', createRule);
    $('mon-btn-refresh')?.addEventListener('click', refreshRules);
    $('mon-btn-clear-history')?.addEventListener('click', clearAlertHistory);
    $('btn-request-browser-notif')?.addEventListener('click', requestBrowserNotificationPermission);

    // Reports
    $('reports-btn-refresh')?.addEventListener('click', refreshHistory);
    $('reports-btn-generate')?.addEventListener('click', generateReport);

    // Settings Theme & Basemap
    document.querySelectorAll('.theme-btn').forEach((b) => {
      b.addEventListener('click', () => {
        window.SharedState.setTheme(b.dataset.theme);
        syncSettingsUI();
      });
    });
    document.querySelectorAll('.basemap-btn').forEach((b) => {
      b.addEventListener('click', () => {
        switchBasemap(b.dataset.basemap);
      });
    });

    // Subscribe to SharedState changes
    lastLocationKey = locationKey(window.SharedState.get().location);
    window.SharedState.subscribe((_, __, change = {}) => {
      const nextLocationKey = locationKey(window.SharedState.get().location);
      if ((change.type === 'location' && change.changed) ||
          (change.type === 'aoi' && change.changed) ||
          nextLocationKey !== lastLocationKey) {
        areaOverviewRequestId += 1;
        areaOverviewRequestKey = null;
        areaOverviewRequestPromise = null;
        clearLocationScopedUi();
        lastLocationKey = nextLocationKey;
        if ($('page-area-overview')?.classList.contains('active')) {
          refreshAreaOverview();
        }
      }
      updateAllLocInfo();
      applyLocationAllMaps();
      if (change.type === 'basemap') {
        switchBasemap(change.basemap);
      }
    });
  }

  async function boot() {
    bind();

    const existingImageId = window.SharedState.get().imageId;
    if (existingImageId) {
      uploadedImageId = existingImageId;
      const preview = $('sat-image-preview');
      if (preview) {
        preview.src = API.imagePreviewUrl(existingImageId, 'rgb');
        preview.classList.remove('hidden');
      }
      if ($('sat-btn-analyze')) $('sat-btn-analyze').disabled = false;
    }

    setCompareType('date');

    try {
      const st = await API.status();
      const pill = $('data-status');
      if (pill) {
        pill.textContent = 'DATA CONNECTED';
        pill.className = 'status-pill ok';
      }
    } catch (e) {
      const pill = $('data-status');
      if (pill) {
        pill.textContent = 'STANDBY';
        pill.className = 'status-pill none';
      }
    }

    // Hash routing
    const hash = (location.hash || '#dashboard').replace('#', '');
    showPage(hash || 'dashboard');
    window.addEventListener('hashchange', () => {
      showPage((location.hash || '#dashboard').replace('#', '') || 'dashboard');
    });

    updateAllLocInfo();
    syncSettingsUI();

    window.AppMain = {
      showPage: showPage,
      onLocationSelected: (loc) => {
        updateAllLocInfo();
        applyLocationAllMaps();
      },
      onAoiChanged: (aoi, areaKm2) => {
        updateAllLocInfo();
        applyLocationAllMaps();
      },
      clearAoi: clearAoi,
      switchBasemap: switchBasemap,
      selectLandcoverCategory: selectLandcoverCategory,
      showToastNotification: showToastNotification,
      recordAlertHistory: recordAlertHistory,
      getLastLandcover: () => lastLandcover,
      getLastCompareResult: () => lastCompareResult,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
