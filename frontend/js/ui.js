function setStatus(status) {
  const el = document.getElementById('data-status');
  if (!el) return;
  el.classList.remove('ok', 'partial', 'none');
  const map = {
    DATA_CONNECTED: ['DATA CONNECTED', 'ok'],
    PARTIAL_DATA: ['PARTIAL DATA', 'partial'],
    NO_CURRENT_DATA: ['NO CURRENT DATA', 'none'],
    INITIALIZING: ['INITIALIZING', ''],
  };
  const [text, cls] = map[status] || [status, 'partial'];
  el.textContent = text;
  if (cls) el.classList.add(cls);
}

function showProgress(msg) {
  const p = document.getElementById('progress');
  const t = document.getElementById('progress-text');
  if (p) p.classList.remove('hidden');
  if (t) t.textContent = msg || 'Working…';
}

function hideProgress() {
  document.getElementById('progress')?.classList.add('hidden');
}

function setLocationInfo(loc) {
  const card = document.getElementById('location-info');
  if (!loc || !loc.success) {
    card?.classList.add('hidden');
    return;
  }
  card.classList.remove('hidden');
  document.getElementById('loc-name').textContent = loc.display_name || '—';
  document.getElementById('loc-lat').textContent = Number(loc.lat).toFixed(5);
  document.getElementById('loc-lon').textContent = Number(loc.lon).toFixed(5);
  document.getElementById('loc-aoi').textContent = loc.aoi_area_km2 ?? '—';
  document.getElementById('loc-src').textContent = loc.source || '—';
}

function setLocationSearchStatus(message, type = '') {
  const el = document.getElementById('location-search-status');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'search-status';
  if (type) el.classList.add(type);
}

function renderAnswer(result) {
  const body = document.getElementById('answer-text');
  body.textContent = result.answer_text || JSON.stringify(result, null, 2);

  const metrics = document.getElementById('metrics');
  if (result.metrics && Object.keys(result.metrics).length) {
    metrics.innerHTML = '<strong>Metrics:</strong> ' + Object.entries(result.metrics)
      .map(([k, v]) => `${k}=${v}`).join(' · ');
  } else metrics.innerHTML = '';

  const fresh = document.getElementById('freshness');
  if (result.freshness && Object.keys(result.freshness).length) {
    fresh.innerHTML = '<strong>DATA STATUS / Freshness:</strong><br>' +
      Object.entries(result.freshness).map(([k, v]) => `${k}: ${v}`).join('<br>');
  } else fresh.innerHTML = '';

  const sources = document.getElementById('sources');
  if (result.sources && result.sources.length) {
    sources.innerHTML = '<strong>Sources:</strong> ' + result.sources.map(s =>
      typeof s === 'string' ? s : (s.name || JSON.stringify(s))
    ).join(' · ');
  } else sources.innerHTML = '';

  const conf = document.getElementById('confidence');
  conf.innerHTML = result.confidence != null
    ? `<strong>Confidence:</strong> ${(result.confidence * 100).toFixed(0)}% (analytical)`
    : '';

  const trace = document.getElementById('trace');
  trace.innerHTML = '';
  (result.execution_trace || []).forEach(step => {
    const li = document.createElement('li');
    li.textContent = `[${step.status}] ${step.step}`;
    trace.appendChild(li);
  });

  setStatus(result.data_status || 'PARTIAL_DATA');
}

function renderSihStatus(statusObj) {
  const ul = document.getElementById('sih-status');
  if (!ul || !statusObj) return;
  ul.innerHTML = '';
  Object.entries(statusObj).forEach(([k, v]) => {
    const li = document.createElement('li');
    const upper = String(v).toUpperCase();
    let cls = 'partial';
    if (upper.startsWith('IMPLEMENTED')) cls = 'impl';
    else if (upper.startsWith('NOT')) cls = 'no';
    li.className = cls;
    li.textContent = `${upper.startsWith('IMPLEMENTED') ? '✓' : upper.startsWith('PARTIAL') ? '◐' : '✗'} ${k}: ${v}`;
    ul.appendChild(li);
  });
}

function setLandcoverStatus(message, type = 'success') {
  const el = document.getElementById('landcover-status');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'upload-status';
  if (message) el.classList.add(type);
}

function setAreaStatus(message, type = 'success') {
  const el = document.getElementById('area-status');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'area-status';
  if (message) el.classList.add(type);
}

function renderLandcoverSummary(result) {
  const el = document.getElementById('landcover-summary');
  const legend = document.getElementById('landcover-legend');
  const legendLabel = document.getElementById('landcover-legend-label');
  const legendSwatch = document.getElementById('landcover-legend-swatch');
  if (!el) return;
  if (!result || !result.success) {
    el.classList.add('hidden');
    el.innerHTML = '';
    if (legend) legend.classList.add('hidden');
    return;
  }

  const quality = result.quality || {};
  const selectedCategory = result.selected_category || result.class || 'Land-cover';
  const color = {
    Water: '#38bdf8',
    Agriculture: '#84cc16',
    'Forest / Vegetation': '#22c55e',
    'Built-up': '#f59e0b',
  }[selectedCategory] || '#f8fafc';
  const areaHa = Number(result.area_ha ?? ((result.detected_area_sq_km ?? 0) * 100.0));
  const aoiHa = Number(result.aoi_area_ha ?? 0);
  const coveragePct = Number(result.percentage ?? result.percentage_of_valid_pixels ?? 0);
  el.classList.remove('hidden');
  if (legend) {
    legend.classList.remove('hidden');
    if (legendLabel) legendLabel.textContent = `${selectedCategory}`;
    if (legendSwatch) legendSwatch.style.background = color;
  }
  el.innerHTML = `
    <div><strong>Category:</strong> ${selectedCategory}</div>
    <div><strong>Method:</strong> ${result.analysis_method || result.method || '—'}</div>
    <div><strong>Area:</strong> ${Number.isFinite(areaHa) ? areaHa.toFixed(2) : '—'} ha</div>
    <div><strong>AOI:</strong> ${Number.isFinite(aoiHa) ? aoiHa.toFixed(2) : '—'} ha</div>
    <div><strong>Coverage:</strong> ${Number.isFinite(coveragePct) ? coveragePct.toFixed(2) : '—'}%</div>
    <div><strong>Pixels detected:</strong> ${result.pixel_count ?? result.detected_pixel_count ?? '—'}</div>
    <div><strong>CRS:</strong> ${result.crs || '—'}</div>
    <div><strong>Bounds:</strong> ${result.bounds ? `${Number(result.bounds.left).toFixed(4)}, ${Number(result.bounds.bottom).toFixed(4)}, ${Number(result.bounds.right).toFixed(4)}, ${Number(result.bounds.top).toFixed(4)}` : '—'}</div>
    <div><strong>Quality:</strong> ${quality.confidence || '—'}</div>
    <div><strong>Note:</strong> ${quality.method_note || result.warning || '—'}</div>
  `;
}

function setSelectedImageName(fileName) {
  const el = document.getElementById('upload-file-name');
  if (!el) return;
  el.textContent = fileName ? `Selected: ${fileName}` : 'No file selected';
}

function setUploadMessage(message, type = 'success') {
  const el = document.getElementById('upload-status');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'upload-status';
  if (message) el.classList.add(type);
}

function renderImageMetadata(meta) {
  const el = document.getElementById('image-metadata');
  if (!el) return;
  if (!meta || !meta.success) {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }

  const bounds = meta.bounds || {};
  el.classList.remove('hidden');
  el.innerHTML = `
    <div><strong>Image name:</strong> ${meta.filename || '—'}</div>
    <div><strong>Dimensions:</strong> ${meta.width || '—'} × ${meta.height || '—'} px</div>
    <div><strong>Bands:</strong> ${meta.bands ?? '—'}</div>
    <div><strong>CRS:</strong> ${meta.crs || 'MISSING CRS'}</div>
    <div><strong>Resolution:</strong> ${meta.resolution ? `${Number(meta.resolution.x).toFixed(6)} × ${Number(meta.resolution.y).toFixed(6)}` : '—'}</div>
    <div><strong>Bounds:</strong> left ${Number(bounds.left ?? 0).toFixed(4)}, bottom ${Number(bounds.bottom ?? 0).toFixed(4)}, right ${Number(bounds.right ?? 0).toFixed(4)}, top ${Number(bounds.top ?? 0).toFixed(4)}</div>
    <div><strong>File size:</strong> ${meta.file_size_bytes ? `${(meta.file_size_bytes / 1024 / 1024).toFixed(2)} MB` : '—'}</div>
  `;
}

window.UI = {
  setStatus,
  showProgress,
  hideProgress,
  setLocationInfo,
  setLocationSearchStatus,
  renderAnswer,
  renderSihStatus,
  setSelectedImageName,
  setUploadMessage,
  renderImageMetadata,
  setLandcoverStatus,
  setAreaStatus,
  renderLandcoverSummary,
};
