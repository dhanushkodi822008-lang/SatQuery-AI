/**
 * SatQuery AI — District Overview Dashboard
 */
(function () {
  let map = null;
  let aoiLayer = null;
  let markerLayer = null;
  let currentOverview = null;
  let currentLoc = null;
  let selectedHazard = 'flood';
  let hazardsMeta = {};

  const CLASS_COLORS = {
    'Agricultural Land': '#22c55e',
    'Agriculture': '#22c55e',
    'Built-up Area': '#ef4444',
    'Built-up': '#ef4444',
    'Water Bodies': '#3b82f6',
    'Water': '#3b82f6',
    'Other Land': '#94a3b8',
    'Other': '#94a3b8',
    'Vegetation': '#16a34a',
    'Forest / Vegetation': '#16a34a',
  };

  function $(id) { return document.getElementById(id); }

  function toast(msg, severe) {
    const el = document.createElement('div');
    el.className = 'toast' + (severe ? ' severe' : '');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  function setStatus(text, cls) {
    const el = $('data-status');
    if (!el) return;
    el.textContent = text;
    el.className = 'status-pill' + (cls ? ' ' + cls : '');
  }

  // ---- Map ----
  function initMap() {
    map = L.map('dash-map', { zoomControl: true }).setView([20.5937, 78.9629], 5);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles © Esri',
      maxZoom: 18,
    }).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Labels © Esri',
      maxZoom: 18,
      opacity: 0.7,
    }).addTo(map);
  }

  function setAoi(geojson, center) {
    if (aoiLayer) { map.removeLayer(aoiLayer); aoiLayer = null; }
    if (markerLayer) { map.removeLayer(markerLayer); markerLayer = null; }
    if (geojson) {
      aoiLayer = L.geoJSON(geojson, {
        style: { color: '#ffffff', weight: 2, dashArray: '6 4', fillOpacity: 0.05 },
      }).addTo(map);
      try { map.fitBounds(aoiLayer.getBounds(), { padding: [24, 24] }); } catch (_) {}
    }
    if (center) {
      markerLayer = L.marker([center.lat, center.lon]).addTo(map);
      if (!geojson) map.setView([center.lat, center.lon], 11);
    }
  }

  // ---- Composition donut (canvas) ----
  function drawDonut(classes, totalKm2) {
    const canvas = $('composition-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, r = 70, rw = 22;

    if (!classes || !classes.length) {
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = rw;
      ctx.stroke();
      $('composition-center').textContent = '— km²';
      $('composition-legend').innerHTML = '';
      return;
    }

    let start = -Math.PI / 2;
    const legend = $('composition-legend');
    legend.innerHTML = '';
    classes.forEach((c) => {
      const pct = Number(c.percent) || 0;
      const angle = (pct / 100) * Math.PI * 2;
      const color = CLASS_COLORS[c.name] || '#64748b';
      ctx.beginPath();
      ctx.arc(cx, cy, r, start, start + angle);
      ctx.strokeStyle = color;
      ctx.lineWidth = rw;
      ctx.lineCap = 'butt';
      ctx.stroke();
      start += angle;

      const li = document.createElement('li');
      li.innerHTML = `<span class="swatch" style="background:${color}"></span>
        ${c.name}: <strong>${pct}%</strong> (${c.area_km2 != null ? c.area_km2 + ' km²' : '—'})`;
      legend.appendChild(li);
    });

    // hole
    ctx.beginPath();
    ctx.arc(cx, cy, r - rw / 2 - 2, 0, Math.PI * 2);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#121a2b';
    ctx.fill();

    $('composition-center').textContent = totalKm2 != null ? `${totalKm2} km²` : '— km²';
  }

  function updateStatCards(classes) {
    const find = (names) => classes.find(c => names.some(n => (c.name || '').toLowerCase().includes(n))) || {};
    const agri = find(['agricult', 'crop']);
    const built = find(['built']);
    const water = find(['water']);
    const other = find(['other']) || { percent: Math.max(0, 100 - [agri, built, water].reduce((s, c) => s + (Number(c.percent) || 0), 0)) };

    const set = (pctId, kmId, c) => {
      $(pctId).textContent = c.percent != null ? `${c.percent}%` : 'unavailable';
      $(kmId).textContent = c.area_km2 != null ? `${c.area_km2} km²` : '— km²';
    };
    set('stat-agri-pct', 'stat-agri-km', agri);
    set('stat-built-pct', 'stat-built-km', built);
    set('stat-water-pct', 'stat-water-km', water);
    set('stat-other-pct', 'stat-other-km', other);
  }

  // ---- Water table ----
  function renderWaterBodies(wb) {
    const tbody = $('water-tbody');
    tbody.innerHTML = '';
    const items = (wb && wb.items) || [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">No water-body data for this AOI (live gauges not connected or none found).</td></tr>';
      return;
    }
    items.forEach((w) => {
      const tr = document.createElement('tr');
      const change = w.change_vs_last_year;
      let changeHtml = '—';
      if (change != null) {
        const up = Number(change) >= 0;
        changeHtml = `<span class="${up ? 'arrow-up' : 'arrow-down'}">${up ? '▲' : '▼'} ${Math.abs(change)}</span>`;
      }
      tr.innerHTML = `
        <td>${w.name || '—'}</td>
        <td>${w.type || '—'}</td>
        <td>${w.current_level_m != null ? w.current_level_m : 'unavailable'}</td>
        <td>${changeHtml}</td>`;
      tbody.appendChild(tr);
    });
  }

  // ---- Change detection ----
  function renderChange(cd) {
    const list = $('change-list');
    list.innerHTML = '';
    const items = (cd && cd.items) || [];
    if (!items.length) {
      list.innerHTML = '<li class="empty">Change detection unavailable — run dual-date analysis first.</li>';
      return;
    }
    items.forEach((c) => {
      const li = document.createElement('li');
      const dir = c.direction === 'up' ? '▲' : (c.direction === 'down' ? '▼' : '•');
      const cls = c.direction === 'up' ? 'arrow-up' : (c.direction === 'down' ? 'arrow-down' : '');
      li.innerHTML = `
        <div class="change-thumb">img</div>
        <div class="change-meta">
          <div class="cls">${c.class}</div>
          <div class="delta"><span class="${cls}">${dir} ${c.percent_change != null ? c.percent_change + '%' : '—'}</span>
            ${c.delta_km2 != null ? ` · ${c.delta_km2} km²` : ''}</div>
        </div>`;
      list.appendChild(li);
    });
  }

  // ---- Risk UI ----
  function renderHazardChips(hazards) {
    const wrap = $('hazard-chips');
    wrap.innerHTML = '';
    Object.keys(hazards || {}).forEach((id) => {
      const h = hazards[id];
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'hazard-chip' + (id === selectedHazard ? ' active' : '');
      chip.setAttribute('role', 'tab');
      chip.dataset.hazard = id;
      chip.innerHTML = `<span class="dot" style="background:${h.color || '#64748b'}"></span>${h.label || id}`;
      chip.addEventListener('click', () => {
        selectedHazard = id;
        wrap.querySelectorAll('.hazard-chip').forEach(c => c.classList.toggle('active', c.dataset.hazard === id));
        showHazard(hazards[id]);
      });
      wrap.appendChild(chip);
    });
  }

  function setGauge(score) {
    const arc = $('gauge-arc');
    const text = $('gauge-text');
    const circ = 2 * Math.PI * 50;
    const pct = Math.max(0, Math.min(100, Number(score) || 0)) / 100;
    arc.style.strokeDasharray = `${pct * circ} ${circ}`;
    const sev = score >= 75 ? '#ef4444' : score >= 50 ? '#f97316' : score >= 25 ? '#f59e0b' : '#22c55e';
    arc.style.stroke = sev;
    text.textContent = score != null ? `${Math.round(score)}` : '—';
  }

  function showHazard(h) {
    if (!h) return;
    const sev = h.severity || 'LOW';
    const label = $('hazard-severity');
    label.textContent = sev;
    label.className = 'severity-label ' + sev;
    setGauge(h.score);
    $('hazard-explanation').textContent = h.explanation || '—';
    const fl = $('factor-list');
    fl.innerHTML = '';
    (h.contributing_factors || []).forEach((f) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${f.name}${f.detail ? ' · ' + f.detail : ''}</span>
        <span class="rating ${f.rating || ''}">${f.rating || '—'}</span>`;
      fl.appendChild(li);
    });
  }

  function renderComposite(comp) {
    $('composite-summary').textContent = comp?.explanation || '—';
    const top = $('composite-top');
    top.innerHTML = '';
    (comp?.top_hazards || []).forEach((t) => {
      const pill = document.createElement('span');
      pill.className = 'composite-pill';
      pill.textContent = `${t.label}: ${t.severity} (${t.score})`;
      top.appendChild(pill);
    });
  }

  // ---- Load overview ----
  async function loadOverview(loc) {
    setStatus('LOADING', 'partial');
    $('dash-loc-status').textContent = 'Fetching weather, landcover signals & risk…';
    $('dash-loc-status').className = 'search-status loading';

    let weather = null, waterLevel = null;
    try {
      weather = await API.weather(loc.lat, loc.lon);
    } catch (e) { console.warn('weather', e); }
    try {
      waterLevel = await API.waterLevel(loc.lat, loc.lon, loc.display_name || loc.name);
    } catch (e) { console.warn('water', e); }

    // Optional: try a quick landcover analyse if we have nothing — honest unavailable otherwise
    const body = {
      district: loc.display_name || loc.name || 'AOI',
      lat: loc.lat,
      lon: loc.lon,
      aoi_area_km2: loc.aoi_area_km2 || loc.area_km2 || null,
      aoi_geojson: loc.geojson || loc.aoi || null,
      weather,
      water_level: waterLevel,
      // landcover / change left null unless caller supplies — UI shows unavailable
    };

    try {
      const data = await API.dashboardOverview(body);
      currentOverview = data;
      currentLoc = loc;

      $('district-title').textContent = `${data.district} Overview`;
      $('total-area').textContent = data.aoi_area_km2 != null ? data.aoi_area_km2 : '—';
      $('analysis-date').textContent = data.analysis_date || '—';
      $('risk-updated').textContent = 'Updated ' + (data.assessed_at || '').replace('T', ' ').slice(0, 19) + ' UTC';

      const comp = data.composition || {};
      drawDonut(comp.classes || [], comp.total_area_km2 || data.aoi_area_km2);
      updateStatCards(comp.classes || []);
      $('composition-status').textContent = comp.unavailable
        ? 'Composition unavailable — run land-cover analysis on the main page for quantitative classes.'
        : (comp.source ? `Source: ${comp.source}` : '');

      renderWaterBodies(data.water_bodies);
      renderChange(data.change_detection);

      const hazards = (data.risk && data.risk.hazards) || {};
      renderHazardChips(hazards);
      if (hazards[selectedHazard]) showHazard(hazards[selectedHazard]);
      else if (Object.keys(hazards).length) {
        selectedHazard = Object.keys(hazards)[0];
        showHazard(hazards[selectedHazard]);
      }
      renderComposite(data.risk && data.risk.composite);

      setAoi(loc.geojson || loc.aoi || null, { lat: loc.lat, lon: loc.lon });

      // Evaluate alert rules
      try {
        const ev = await API.evaluateAlerts(data.analysis_id);
        if (ev.new_alerts && ev.new_alerts.length) {
          ev.new_alerts.forEach(a => toast(a.message, a.severity === 'SEVERE'));
          refreshAlerts();
        }
      } catch (_) {}

      setStatus('DATA_CONNECTED', 'ok');
      $('dash-loc-status').textContent = 'Overview loaded.';
      $('dash-loc-status').className = 'search-status success';
    } catch (e) {
      console.error(e);
      setStatus('ERROR', 'none');
      $('dash-loc-status').textContent = e.message || 'Failed to load overview';
      $('dash-loc-status').className = 'search-status error';
    }
  }

  async function onLocate() {
    const q = $('dash-location-input').value.trim();
    if (!q) return;
    $('dash-loc-status').textContent = 'Searching…';
    $('dash-loc-status').className = 'search-status loading';
    try {
      const res = await API.searchLocation(q);
      // API normally returns one location object; also accept legacy wrapper shapes.
      const loc = res?.results?.[0] || res?.location || res;
      const lat = Number(loc?.lat ?? loc?.latitude);
      const lon = Number(loc?.lon ?? loc?.longitude);
      if (!loc || loc.success === false || !Number.isFinite(lat) || !Number.isFinite(lon)) {
        throw new Error(loc?.error || 'No valid location was returned by the geocoding service.');
      }
      const normalized = {
        lat,
        lon,
        display_name: loc.display_name || loc.name || q,
        name: loc.name || q,
        aoi_area_km2: loc.aoi_area_km2,
        geojson: loc.geojson || loc.aoi || null,
        bbox: loc.bbox,
      };
      await loadOverview(normalized);
    } catch (e) {
      $('dash-loc-status').textContent = e.message || 'Search failed';
      $('dash-loc-status').className = 'search-status error';
    }
  }

  // ---- Download ZIP ----
  async function downloadZip() {
    if (!currentOverview) {
      toast('Load an AOI first');
      return;
    }
    setStatus('EXPORTING', 'partial');
    try {
      const blob = await API.exportZip({
        district: currentOverview.district,
        analysis_date: currentOverview.analysis_date,
        aoi_geojson: currentLoc && (currentLoc.geojson || currentLoc.aoi),
        composition: currentOverview.composition,
        water_bodies: (currentOverview.water_bodies && currentOverview.water_bodies.items) || [],
        change_detection: (currentOverview.change_detection && currentOverview.change_detection.items) || [],
        risk_scores: currentOverview.risk,
        indicators: {
          assessed_at: currentOverview.assessed_at,
          aoi_area_km2: currentOverview.aoi_area_km2,
        },
        metadata: {
          analysis_id: currentOverview.analysis_id,
          note: 'Generated by SatQuery AI dashboard export',
        },
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(currentOverview.district || 'aoi').replace(/\s+/g, '_')}_${currentOverview.analysis_date || 'export'}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      toast('ZIP download started');
      setStatus('DATA_CONNECTED', 'ok');
    } catch (e) {
      toast('Export failed: ' + (e.message || e));
      setStatus('ERROR', 'none');
    }
  }

  // ---- Share ----
  function shareAnalysis() {
    if (!currentOverview) { toast('Load an AOI first'); return; }
    const url = `${window.location.origin}/dashboard?aoi=${encodeURIComponent(currentOverview.district)}&id=${currentOverview.analysis_id}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => toast('Share link copied to clipboard'));
    } else {
      prompt('Copy share link:', url);
    }
  }

  // ---- Alerts ----
  async function refreshAlerts() {
    try {
      const res = await API.listAlerts();
      const badge = $('unread-badge');
      const n = res.unread_count || 0;
      if (n > 0) {
        badge.textContent = n;
        badge.classList.remove('hidden');
      } else {
        badge.classList.add('hidden');
      }
      const list = $('notif-list');
      list.innerHTML = '';
      (res.alerts || []).slice(0, 30).forEach((a) => {
        const div = document.createElement('div');
        div.className = 'notif-item' + (a.read ? '' : ' unread');
        div.innerHTML = `<div class="n-title">${a.message || a.label}</div>
          <div class="n-meta">${a.severity} · ${a.aoi_name || ''} · ${(a.timestamp || '').slice(0, 16)}</div>`;
        div.addEventListener('click', async () => {
          try { await API.markAlertRead(a.id); refreshAlerts(); } catch (_) {}
        });
        list.appendChild(div);
      });
      if (!(res.alerts || []).length) {
        list.innerHTML = '<p class="hint" style="padding:0.5rem">No alerts yet.</p>';
      }
    } catch (_) {}
  }

  async function createAlert() {
    if (!currentOverview) { toast('Load an AOI first'); return; }
    const hazard = $('alert-hazard').value;
    const severity = $('alert-severity').value;
    const channel = $('alert-channel').value;
    try {
      await API.createAlertRule({
        aoi_id: currentOverview.analysis_id,
        aoi_name: currentOverview.district,
        hazard,
        threshold_severity: severity,
        channel,
      });
      $('alert-form-status').textContent = 'Rule created.';
      toast('Alert rule created');
      // Re-evaluate immediately
      await API.evaluateAlerts(currentOverview.analysis_id);
      refreshAlerts();
    } catch (e) {
      $('alert-form-status').textContent = e.message || 'Failed';
    }
  }

  function enablePush() {
    if (!('Notification' in window)) {
      toast('This browser does not support notifications');
      return;
    }
    // If in iframe, warn
    if (window.self !== window.top) {
      toast('Open the app in its own tab to enable notifications');
      return;
    }
    Notification.requestPermission().then((perm) => {
      toast(perm === 'granted' ? 'Notifications enabled' : 'Permission: ' + perm);
    });
  }

  // ---- Full risk modal ----
  async function openFullRisk() {
    if (!currentOverview) return;
    const modal = $('risk-modal');
    const body = $('modal-body');
    $('modal-hazard-title').textContent = (hazardsMeta[selectedHazard]?.label || selectedHazard) + ' — Full Analysis';
    body.innerHTML = '<p class="hint">Loading…</p>';
    modal.classList.remove('hidden');
    try {
      const detail = await API.hazardDetail(selectedHazard, currentOverview.analysis_id);
      const h = detail.hazard || {};
      const actions = (detail.recommended_actions || []).map(a => `<li>${a}</li>`).join('');
      const sources = (h.dataSources || []).map(s =>
        `<li>${s.name} (${s.type}) — ${s.updated_at || '—'}</li>`).join('') || '<li>No live sources for this hazard</li>';
      body.innerHTML = `
        <p><strong>Severity:</strong> ${h.severity} · <strong>Score:</strong> ${h.score}/100 ·
           <strong>Confidence:</strong> ${((h.confidence || 0) * 100).toFixed(0)}%</p>
        <p>${h.explanation || ''}</p>
        <h4>30-day trend</h4>
        <p class="hint">${detail.trend?.message || 'Not available'}</p>
        <h4>Data sources</h4>
        <ul>${sources}</ul>
        <h4>Recommended actions</h4>
        <ul>${actions}</ul>
        <p class="hint" style="margin-top:1rem">Scores are analytical indicators, not official emergency warnings.</p>
      `;
    } catch (e) {
      body.innerHTML = `<p class="hint">${e.message}</p>`;
    }
  }

  // ---- Boot ----
  async function boot() {
    initMap();
    try {
      const hz = await API.listHazards();
      (hz.hazards || []).forEach(h => { hazardsMeta[h.id] = h; });
      const sel = $('alert-hazard');
      sel.innerHTML = (hz.hazards || []).map(h =>
        `<option value="${h.id}">${h.label}</option>`).join('');
    } catch (_) {}

    $('btn-dash-locate').addEventListener('click', onLocate);
    $('dash-location-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') onLocate(); });
    $('btn-download-zip').addEventListener('click', downloadZip);
    $('btn-download-zip-header').addEventListener('click', downloadZip);
    $('btn-share').addEventListener('click', shareAnalysis);
    $('btn-refresh-risk').addEventListener('click', () => { if (currentLoc) loadOverview(currentLoc); });
    $('btn-create-alert').addEventListener('click', createAlert);
    $('btn-enable-push').addEventListener('click', enablePush);
    $('btn-full-risk').addEventListener('click', openFullRisk);
    $('btn-close-modal').addEventListener('click', () => $('risk-modal').classList.add('hidden'));
    $('btn-bell').addEventListener('click', () => {
      $('notif-panel').classList.toggle('hidden');
      refreshAlerts();
    });
    $('btn-close-notif').addEventListener('click', () => $('notif-panel').classList.add('hidden'));
    $('btn-area-info').addEventListener('click', () => {
      if (currentOverview) {
        toast(`${currentOverview.district} · ${currentOverview.aoi_area_km2 || '—'} km² · ${currentOverview.analysis_date}`);
      } else toast('No AOI loaded');
    });

    // Prefill from query string
    const params = new URLSearchParams(window.location.search);
    const aoiQ = params.get('aoi');
    if (aoiQ) {
      $('dash-location-input').value = aoiQ;
      onLocate();
    }

    refreshAlerts();
    setStatus('READY', 'ok');
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
