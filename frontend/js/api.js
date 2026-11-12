/**
 * Backend API client. All secrets stay on the server.
 */
const API_BASE = window.location.origin.includes('5500') || window.location.protocol === 'file:'
  ? 'http://127.0.0.1:8000'
  : '';

function apiErrorMessage(status, text) {
  try {
    const payload = JSON.parse(text);
    if (typeof payload.detail === 'string') return `API ${status}: ${payload.detail}`;
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.map((item) => item.msg).filter(Boolean);
      if (messages.length) return `API ${status}: ${messages.join('; ')}`;
    }
  } catch (_) {}
  return `API ${status}: ${text.slice(0, 200)}`;
}

async function apiGet(path, params = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) {
    const text = await res.text();
    throw new Error(apiErrorMessage(res.status, text));
  }
  return res.json();
}

async function apiPost(path, body, { timeoutMs = 30000 } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(API_BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(apiErrorMessage(res.status, text));
    }
    return await res.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds. Please try a smaller AOI or try again.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function apiUploadImage(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(API_BASE + '/api/images/upload', {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(apiErrorMessage(res.status, text));
  }
  return res.json();
}

const API = {
  status: () => apiGet('/api/status'),
  searchLocation: (q) => apiGet('/api/location/search', { q }),
  reverseLocation: (lat, lon) => apiGet('/api/location/reverse', { lat, lon }),
  weather: (lat, lon) => apiGet('/api/weather', { lat, lon }),
  waterLevel: (lat, lon, place) => apiGet('/api/water/level', { lat, lon, place }),
  waterFeatures: (bbox) => apiGet('/api/water/features', {
    min_lon: bbox[0], min_lat: bbox[1], max_lon: bbox[2], max_lat: bbox[3],
  }),
  satelliteSearch: (bbox, opts = {}) => apiGet('/api/satellite/search', {
    min_lon: bbox[0], min_lat: bbox[1], max_lon: bbox[2], max_lat: bbox[3],
    ...opts,
  }),
  analyze: (location, question, aoi = null) => apiPost('/api/analyze/query', { location, question, ...(aoi ? { aoi } : {}) }),
  report: (location, question, analysis) => apiPost('/api/report', { location, question, analysis }),
  reportPdf: async (location, question, analysis) => {
    const res = await fetch(API_BASE + '/api/report/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ location, question, analysis }),
    });
    if (!res.ok) {
      const text = await res.text();
      let detail = text;
      try { detail = JSON.parse(text).detail || text; } catch (_) {}
      throw new Error(`PDF generation failed: ${detail.slice(0, 240)}`);
    }
    return res.blob();
  },
  saveHistory: (item) => apiPost('/api/history', item),
  listHistory: (params = {}) => apiGet('/api/history', params),
  models: () => apiGet('/api/analyze/models'),
  uploadImage: (file) => apiUploadImage(file),
  landcoverCategories: () => apiGet('/api/landcover/supported'),
  chat: (payload) => apiPost('/api/chat', payload),
  chatMessage: (payload) => apiPost('/api/chat/message', payload),
  chatHistory: (sessionId) => apiGet(`/api/chat/history/${sessionId}`),
  chatSessions: () => apiGet('/api/chat/sessions'),
  deleteChat: (sessionId) => fetch((window.location.origin.includes('5500') || window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '') + `/api/chat/${sessionId}`, { method: 'DELETE' }).then(r => r.json()),
  imagePreviewUrl: (imageId, render = 'rgb') => (window.location.origin.includes('5500') || window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '') + `/api/images/${imageId}/preview.png?render=${render}`,
  analyzeLandcover: (imageId, category, aoi = null, location = null) => apiPost('/api/landcover/analyze', {
    image_id: imageId || null,
    category,
    ...(aoi ? { aoi } : {}),
    ...(location ? { location, bbox: location.bbox || null } : {}),
  }, { timeoutMs: 180000 }),

  // Dashboard / risk / export / alerts
  dashboardOverview: (body) => apiPost('/api/dashboard/overview', body),
  hazardDetail: (hazard, analysisId) => apiGet(`/api/dashboard/risk/${hazard}`, analysisId ? { analysis_id: analysisId } : {}),
  listHazards: () => apiGet('/api/dashboard/hazards'),
  createAlertRule: (body) => apiPost('/api/dashboard/alerts/rules', body),
  listAlertRules: () => apiGet('/api/dashboard/alerts/rules'),
  listAlerts: (params = {}) => apiGet('/api/dashboard/alerts', params),
  sendDirectTestAlert: (body) => apiPost('/api/alerts/test', body),
  markAlertRead: (id) => apiPost(`/api/dashboard/alerts/${id}/read`, {}),
  evaluateAlerts: (analysisId) => apiPost(`/api/dashboard/alerts/evaluate?analysis_id=${encodeURIComponent(analysisId)}`, {}),
  compareDates: (body) => apiPost('/api/compare/dates', body),
  compareYears: (body) => apiPost('/api/compare/years', body),
  compareImages: (body) => apiPost('/api/compare/images', body),
  availableYears: (params) => apiGet('/api/compare/available-years', params),
  chartData: (body) => apiPost('/api/chart/data', body),
  exportZip: async (body) => {
    const res = await fetch(API_BASE + '/api/dashboard/export/zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Export failed: ${text.slice(0, 200)}`);
    }
    return res.blob();
  },
};

window.API = API;
