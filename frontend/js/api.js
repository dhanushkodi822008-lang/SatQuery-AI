/**
 * Backend API client. All secrets stay on the server.
 */
const API_BASE = window.location.origin.includes('5500') || window.location.protocol === 'file:'
  ? 'http://127.0.0.1:8000'
  : '';

async function apiGet(path, params = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
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
    let detail = text;
    try {
      const payload = JSON.parse(text);
      detail = payload.detail || JSON.stringify(payload);
    } catch (_) {}
    throw new Error(detail.slice(0, 250));
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
  models: () => apiGet('/api/analyze/models'),
  uploadImage: (file) => apiUploadImage(file),
  landcoverCategories: () => apiGet('/api/landcover/supported'),
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
  }),
};

window.API = API;
