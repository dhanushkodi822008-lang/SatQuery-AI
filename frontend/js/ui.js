/**
 * UI Helper Module — SatQuery AI
 * Handles status updates, messages, and DOM manipulation
 */

const UI = {
  /**
   * Set application-wide status badge
   */
  setStatus(status) {
    const pill = document.getElementById('data-status');
    if (!pill) return;
    
    const statusMap = {
      'INITIALIZING': { text: 'INITIALIZING', class: 'partial' },
      'DATA_CONNECTED': { text: 'DATA CONNECTED', class: 'ok' },
      'PARTIAL_DATA': { text: 'PARTIAL DATA', class: 'partial' },
      'NO_CURRENT_DATA': { text: 'NO DATA', class: 'none' },
    };
    
    const config = statusMap[status] || { text: status, class: 'partial' };
    pill.textContent = config.text;
    pill.className = `status-pill ${config.class}`;
  },

  /**
   * Render SIH requirement status list
   */
  renderSihStatus(requirements) {
    const list = document.getElementById('sih-status');
    if (!list || !requirements) return;
    
    list.innerHTML = '';
    Object.entries(requirements).forEach(([key, desc]) => {
      const li = document.createElement('li');
      li.textContent = desc;
      li.className = typeof desc === 'string' && desc.includes('IMPLEMENTED') ? 'impl' : 'partial';
      list.appendChild(li);
    });
  },

  /**
   * Update area selection status message
   */
  setAreaStatus(message, type = 'default') {
    const el = document.getElementById('area-status');
    if (!el) return;
    el.textContent = message;
    el.className = `area-status ${type === 'success' || type === 'error' ? type : ''}`;
  },

  /**
   * Update location search status
   */
  setLocationSearchStatus(message, type = 'default') {
    const el = document.getElementById('location-search-status');
    if (!el) return;
    el.textContent = message;
    el.className = `search-status ${type}`;
  },

  /**
   * Display location information card
   */
  setLocationInfo(location) {
    const card = document.getElementById('location-info');
    if (!card || !location) return;
    
    if (!location.success && !location.display_name) {
      card.classList.add('hidden');
      return;
    }
    
    const lat = Number(location.lat ?? location.latitude ?? 0);
    const lon = Number(location.lon ?? location.longitude ?? 0);
    const aoiArea = Number(location.aoi_area_km2 ?? location.aoi ?? 0);
    
    document.getElementById('loc-name').textContent = location.display_name || '—';
    document.getElementById('loc-lat').textContent = lat.toFixed(5);
    document.getElementById('loc-lon').textContent = lon.toFixed(5);
    document.getElementById('loc-aoi').textContent = aoiArea > 0 ? aoiArea.toFixed(2) : '—';
    document.getElementById('loc-src').textContent = location.source || 'Unknown';
    
    card.classList.remove('hidden');
  },

  /**
   * Set selected image filename display
   */
  setSelectedImageName(filename) {
    const el = document.getElementById('upload-file-name');
    if (!el) return;
    el.textContent = filename || 'No file selected';
  },

  /**
   * Update upload status message
   */
  setUploadMessage(message, type = 'default') {
    const el = document.getElementById('upload-status');
    if (!el) return;
    el.textContent = message;
    el.className = `upload-status ${type}`;
  },

  /**
   * Update land cover analysis status
   */
  setLandcoverStatus(message, type = 'default') {
    const el = document.getElementById('landcover-status');
    if (!el) return;
    el.textContent = message;
    el.className = `upload-status ${type}`;
  },

  /**
   * Render land cover analysis summary
   */
  renderLandcoverSummary(result) {
    const card = document.getElementById('landcover-summary');
    if (!card) return;
    
    if (!result || !result.success) {
      card.classList.add('hidden');
      return;
    }
    
    const category = result.selected_category || result.class || 'Land-cover';
    const method = result.analysis_method || result.method || 'Analysis';
    const percentage = result.percentage ?? result.percentage_detected ?? 0;
    const pixelCount = result.pixel_count ?? result.detected_pixel_count ?? 0;
    
    card.innerHTML = `
      <div style="font-weight: 600; color: var(--accent);">${category}</div>
      <div style="margin-top: 0.3rem; color: var(--text);">
        <strong>${percentage.toFixed(1)}%</strong> detected
      </div>
      <div style="font-size: 0.75rem; color: var(--muted); margin-top: 0.2rem;">
        ${pixelCount} pixels · ${method}
      </div>
    `;
    
    card.classList.remove('hidden');
  },

  /**
   * Render image metadata card
   */
  renderImageMetadata(result) {
    const card = document.getElementById('image-metadata');
    if (!card) return;
    
    if (!result || !result.success) {
      card.classList.add('hidden');
      return;
    }
    
    const crs = result.crs || 'No CRS';
    const bands = result.bands || 0;
    const width = result.width || 0;
    const height = result.height || 0;
    const resolution = result.resolution || {};
    const hasGeo = result.has_geospatial !== false;
    
    card.innerHTML = `
      <div><strong>CRS:</strong> ${crs}</div>
      <div><strong>Dimensions:</strong> ${width} × ${height} px</div>
      <div><strong>Bands:</strong> ${bands}</div>
      <div><strong>Resolution:</strong> ${resolution.x ? Number(resolution.x).toFixed(6) : 'n/a'} × ${resolution.y ? Number(resolution.y).toFixed(6) : 'n/a'}</div>
      ${!hasGeo ? '<div style="color: var(--warn);">⚠ No geospatial metadata</div>' : ''}
    `;
    
    card.classList.remove('hidden');
  },

  /**
   * Show global progress indicator
   */
  showProgress(message = 'Working…') {
    const progress = document.getElementById('progress');
    if (!progress) return;
    
    const text = document.getElementById('progress-text');
    if (text) text.textContent = message;
    
    progress.classList.remove('hidden');
  },

  /**
   * Hide progress indicator
   */
  hideProgress() {
    const progress = document.getElementById('progress');
    if (!progress) return;
    progress.classList.add('hidden');
  },

  /**
   * Render analysis answer
   */
  renderAnswer(analysis) {
    const panel = document.getElementById('answer-text');
    if (!panel) return;
    
    const text = analysis.answer_text || analysis.content || 'No answer';
    panel.textContent = text;
    
    // Render metrics if available
    const metricsEl = document.getElementById('metrics');
    if (metricsEl && analysis.metrics) {
      let html = '<strong>Metrics:</strong> ';
      html += Object.entries(analysis.metrics)
        .map(([k, v]) => `${k}: ${v}`)
        .join(' · ');
      metricsEl.innerHTML = html;
    }
    
    // Render confidence if available
    const confEl = document.getElementById('confidence');
    if (confEl && analysis.confidence != null) {
      confEl.innerHTML = `<strong>Confidence:</strong> ${(analysis.confidence * 100).toFixed(0)}%`;
    }
    
    // Render sources if available
    const srcEl = document.getElementById('sources');
    if (srcEl && analysis.sources) {
      let html = '<strong>Sources:</strong> ';
      if (Array.isArray(analysis.sources)) {
        html += analysis.sources.join(', ');
      } else {
        html += Object.entries(analysis.sources)
          .map(([k, v]) => `${k}: ${v}`)
          .join('; ');
      }
      srcEl.innerHTML = html;
    }
    
    // Render execution trace if available
    const traceEl = document.getElementById('trace');
    if (traceEl && analysis.trace) {
      traceEl.innerHTML = '';
      const items = Array.isArray(analysis.trace) ? analysis.trace : [analysis.trace];
      items.forEach(item => {
        const li = document.createElement('li');
        li.textContent = typeof item === 'string' ? item : JSON.stringify(item);
        traceEl.appendChild(li);
      });
    }
  }
};

// Export for global use
window.UI = UI;
