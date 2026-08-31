/**
 * Leaflet map — real interactive map (OpenStreetMap tiles).
 * Base map is NOT satellite data.
 */
let map, markerLayer, aoiLayer, waterLayer, indexLayer, uploadedImageLayer, currentLandcoverLayer;
let manualAoiLayer, manualAoiPoints = [], manualAoiDrawing = false;
let landcoverOpacity = 70;
const detectionLayers = {};

function initMap() {
  if (window.__satquery_map_initialized && window.__satquery_map) return window.__satquery_map;

  const mapContainer = document.getElementById('map');
  if (!mapContainer) {
    console.error('[SatQuery] #map container not found during initMap()');
    return null;
  }

  if (mapContainer._leaflet_id && mapContainer._leaflet_map) {
    return mapContainer._leaflet_map;
  }

  map = L.map('map', { zoomControl: true }).setView([10.82177, 78.38287], 10);
  window.__satquery_map = map;
  window.map = map;
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors | Base map is OSM, not satellite imagery',
  }).addTo(map);

  map.whenReady(() => {
    setTimeout(() => map.invalidateSize(), 150);
  });

  markerLayer = L.layerGroup().addTo(map);
  aoiLayer = L.layerGroup().addTo(map);
  waterLayer = L.layerGroup().addTo(map);
  indexLayer = L.layerGroup().addTo(map);
  uploadedImageLayer = L.layerGroup().addTo(map);
  currentLandcoverLayer = L.layerGroup().addTo(map);
  manualAoiLayer = L.layerGroup().addTo(map);
  detectionLayers.water = L.layerGroup().addTo(map);
  detectionLayers.vegetation = L.layerGroup().addTo(map);
  detectionLayers.builtup = L.layerGroup().addTo(map);

  window.__satquery_map_initialized = true;
  mapContainer._leaflet_map = map;

  document.getElementById('ly-aoi')?.addEventListener('change', (e) => {
    if (e.target.checked) map.addLayer(aoiLayer); else map.removeLayer(aoiLayer);
  });
  document.getElementById('ly-osm-water')?.addEventListener('change', (e) => {
    if (e.target.checked) map.addLayer(waterLayer); else map.removeLayer(waterLayer);
  });
  document.getElementById('ly-marker')?.addEventListener('change', (e) => {
    if (e.target.checked) map.addLayer(markerLayer); else map.removeLayer(markerLayer);
  });
  ['water', 'vegetation', 'builtup'].forEach((name) => {
    document.getElementById(`ly-detection-${name}`)?.addEventListener('change', (e) => {
      if (e.target.checked) map.addLayer(detectionLayers[name]);
      else map.removeLayer(detectionLayers[name]);
    });
  });
}

function showLocation(loc) {
  markerLayer.clearLayers();
  aoiLayer.clearLayers();
  if (!loc || !loc.success) return;

  const lat = Number(loc.lat ?? loc.latitude), lon = Number(loc.lon ?? loc.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  L.marker([lat, lon]).addTo(markerLayer)
    .bindPopup(`<b>${loc.display_name || 'Location'}</b><br>${lat.toFixed(5)}, ${lon.toFixed(5)}<br>AOI ≈ ${loc.aoi_area_km2 || '—'} km²`);

  if (loc.bbox && loc.bbox.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = loc.bbox;
    const bounds = [[minLat, minLon], [maxLat, maxLon]];
    L.rectangle(bounds, {
      color: '#3b82f6', weight: 2, fillOpacity: 0.08, dashArray: '6 4',
    }).addTo(aoiLayer);
    map.fitBounds(bounds, { padding: [40, 40] });
  } else {
    map.setView([lat, lon], 12);
  }
}

function showOsmWater(features) {
  waterLayer.clearLayers();
  if (!features || !features.length) return;
  features.forEach((f) => {
    if (f.lat == null || f.lon == null) return;
    L.circleMarker([f.lat, f.lon], {
      radius: 6, color: '#0ea5e9', fillColor: '#38bdf8', fillOpacity: 0.8, weight: 1,
    }).addTo(waterLayer).bindPopup(
      `<b>${f.name || 'Water feature'}</b><br>${f.waterway || f.natural || ''}<br>Source: OSM`
    );
  });
}

function showIndexPoints(points, color, label) {
  if (!points || !points.length) return;
  points.forEach((p) => {
    if (p.lat == null || p.lon == null) return;
    L.circleMarker([p.lat, p.lon], {
      radius: 3, color: color, fillColor: color, fillOpacity: 0.7, weight: 0,
    }).addTo(indexLayer).bindPopup(label || 'Index sample');
  });
}

function showMaskGeoJSON(geojson, color, label, category = 'water') {
  if (!geojson || !Array.isArray(geojson.features) || !geojson.features.length) return;
  L.geoJSON(geojson, {
    style: { color, fillColor: color, weight: 1, fillOpacity: 0.45 },
    onEachFeature: (feature, layer) => layer.bindPopup(label || 'Detected region'),
  }).addTo(detectionLayers[category] || indexLayer);
}

function clearIndexLayer() {
  indexLayer?.clearLayers();
  Object.values(detectionLayers).forEach((layer) => layer.clearLayers());
}

function startAreaSelection(onChange) {
  cancelAreaSelection();
  manualAoiDrawing = true;
  manualAoiPoints = [];
  map.on('click', onAreaClick);
  function onAreaClick(event) {
    manualAoiPoints.push(event.latlng);
    renderManualAoi(false);
    onChange?.(manualAoiPoints.length);
  }
  map._satqueryAreaClick = onAreaClick;
}

function renderManualAoi(complete) {
  manualAoiLayer.clearLayers();
  if (manualAoiPoints.length < 1) return;
  const points = manualAoiPoints.map((point) => [point.lat, point.lng]);
  if (complete) points.push(points[0]);
  const shape = complete ? L.polygon(points, { color: '#a78bfa', weight: 3, fillOpacity: 0.16 }) : L.polyline(points, { color: '#a78bfa', weight: 3, dashArray: '5 5' });
  shape.addTo(manualAoiLayer);
}

function finishAreaSelection() {
  const result = validateManualAoi();
  if (!result.valid) return null;
  manualAoiPoints = result.aoi.coordinates[0].slice(0, -1).map(([lon, lat]) => L.latLng(lat, lon));
  console.debug('[SatQuery] validated manual AOI GeoJSON', result.aoi);
  manualAoiDrawing = false;
  if (map._satqueryAreaClick) map.off('click', map._satqueryAreaClick);
  renderManualAoi(true);
  return result.aoi;
}

function cancelAreaSelection() {
  if (map?._satqueryAreaClick) map.off('click', map._satqueryAreaClick);
  manualAoiDrawing = false;
  manualAoiPoints = [];
  manualAoiLayer?.clearLayers();
}

function clearAreaSelection() {
  cancelAreaSelection();
}

function getManualAoi() {
  const result = validateManualAoi();
  return result.valid && !manualAoiDrawing ? result.aoi : null;
}

function hasAreaPoints() {
  return manualAoiPoints.length > 0;
}

function isAreaDrawing() {
  return manualAoiDrawing;
}

function validateManualAoi() {
  const coordinates = [];
  for (const point of manualAoiPoints) {
    const coordinate = [Number(point.lng), Number(point.lat)];
    const previous = coordinates[coordinates.length - 1];
    if (!previous || coordinate[0] !== previous[0] || coordinate[1] !== previous[1]) {
      coordinates.push(coordinate);
    }
  }

  if (coordinates.length < 3) {
    return { valid: false, error: 'Select at least three distinct points.' };
  }
  const uniqueCoordinates = new Set(coordinates.map(([lon, lat]) => `${lon},${lat}`));
  if (uniqueCoordinates.size < 3) {
    return { valid: false, error: 'Select at least three distinct points.' };
  }
  const first = coordinates[0];
  const last = coordinates[coordinates.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) coordinates.pop();
  if (coordinates.length < 3) {
    return { valid: false, error: 'Select at least three distinct points.' };
  }
  if (coordinates.some(([lon, lat]) => !Number.isFinite(lon) || !Number.isFinite(lat) || lon < -180 || lon > 180 || lat < -90 || lat > 90)) {
    return { valid: false, error: 'Area coordinates are outside the valid map range.' };
  }

  const ring = [...coordinates, coordinates[0]];
  if (Math.abs(polygonSignedArea(ring)) < Number.EPSILON) {
    return { valid: false, error: 'Area must cover a non-zero region.' };
  }
  for (let firstIndex = 0; firstIndex < ring.length - 1; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < ring.length - 1; secondIndex += 1) {
      if (secondIndex === firstIndex + 1 || (firstIndex === 0 && secondIndex === ring.length - 2)) continue;
      if (segmentsIntersect(ring[firstIndex], ring[firstIndex + 1], ring[secondIndex], ring[secondIndex + 1])) {
        return { valid: false, error: 'Invalid area. Please draw a simple area without crossing the boundary.' };
      }
    }
  }
  return { valid: true, aoi: { type: 'Polygon', coordinates: [ring] } };
}

function polygonSignedArea(ring) {
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    area += ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1];
  }
  return area / 2;
}

function segmentsIntersect(firstStart, firstEnd, secondStart, secondEnd) {
  const epsilon = 1e-12;
  const orientation = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const onSegment = (a, b, point) =>
    point[0] >= Math.min(a[0], b[0]) - epsilon && point[0] <= Math.max(a[0], b[0]) + epsilon &&
    point[1] >= Math.min(a[1], b[1]) - epsilon && point[1] <= Math.max(a[1], b[1]) + epsilon;
  const first = orientation(firstStart, firstEnd, secondStart);
  const second = orientation(firstStart, firstEnd, secondEnd);
  const third = orientation(secondStart, secondEnd, firstStart);
  const fourth = orientation(secondStart, secondEnd, firstEnd);
  if (((first > epsilon && second < -epsilon) || (first < -epsilon && second > epsilon)) &&
      ((third > epsilon && fourth < -epsilon) || (third < -epsilon && fourth > epsilon))) {
    return true;
  }
  return (Math.abs(first) <= epsilon && onSegment(firstStart, firstEnd, secondStart)) ||
    (Math.abs(second) <= epsilon && onSegment(firstStart, firstEnd, secondEnd)) ||
    (Math.abs(third) <= epsilon && onSegment(secondStart, secondEnd, firstStart)) ||
    (Math.abs(fourth) <= epsilon && onSegment(secondStart, secondEnd, firstEnd));
}

function getManualAoiCenter() {
  const aoi = getManualAoi();
  const ring = aoi?.coordinates?.[0] || [];
  if (ring.length < 4) return null;
  let crossSum = 0;
  let lonSum = 0;
  let latSum = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [lon1, lat1] = ring[index];
    const [lon2, lat2] = ring[index + 1];
    const cross = lon1 * lat2 - lon2 * lat1;
    crossSum += cross;
    lonSum += (lon1 + lon2) * cross;
    latSum += (lat1 + lat2) * cross;
  }
  if (crossSum === 0) return null;
  return { lon: lonSum / (3 * crossSum), lat: latSum / (3 * crossSum) };
}

function fitManualAoi() {
  if (!manualAoiLayer || !manualAoiPoints.length) return;
  map.fitBounds(L.latLngBounds(manualAoiPoints), { padding: [40, 40] });
}

function areaKm2(geojson) {
  const ring = geojson?.coordinates?.[0] || [];
  if (ring.length < 4) return 0;
  const meanLat = ring.reduce((sum, point) => sum + point[1], 0) / ring.length;
  const lonScale = 111 * Math.cos(meanLat * Math.PI / 180);
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    area += ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1];
  }
  return Math.abs(area / 2) * 111 * lonScale;
}

function showUploadedRaster(meta) {
  if (!uploadedImageLayer || !meta || !meta.success || !meta.bounds) return;
  uploadedImageLayer.clearLayers();

  const { left, bottom, right, top } = meta.bounds;
  if (left == null || bottom == null || right == null || top == null) return;

  const bounds = [[bottom, left], [top, right]];
  L.rectangle(bounds, {
    color: '#22c55e', weight: 2, fillOpacity: 0.08, dashArray: '4 5',
  }).addTo(uploadedImageLayer).bindPopup(`<b>${meta.filename || 'Uploaded image'}</b><br>${meta.width} × ${meta.height} px`);

  map.fitBounds(bounds, { padding: [40, 40] });
}

function setLandcoverOpacity(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return;
  landcoverOpacity = Math.min(100, Math.max(0, numeric));
  if (!currentLandcoverLayer) return;
  currentLandcoverLayer.eachLayer((layer) => {
    if (typeof layer.setStyle === 'function') {
      layer.setStyle({
        opacity: landcoverOpacity / 100,
        fillOpacity: (landcoverOpacity / 100) * 0.6,
      });
    }
  });
}

function showLandcoverOverlay(result) {
  if (!currentLandcoverLayer || !result || !result.success) return;
  currentLandcoverLayer.clearLayers();

  const geojson = result.geojson || result.map_geojson || result.overlay_geojson || null;
  const selectedCategory = result.selected_category || result.class || 'Land-cover';
  const color = {
    Water: '#38bdf8',
    Agriculture: '#84cc16',
    'Forest / Vegetation': '#22c55e',
    'Built-up': '#f59e0b',
  }[selectedCategory] || '#f8fafc';

  const popup = `<b>${selectedCategory}</b><br>${result.analysis_method || result.method || 'Satellite index'}<br>${result.pixel_count ?? result.detected_pixel_count ?? 0} detected pixels`;
  const opacity = landcoverOpacity / 100;

  if (geojson && geojson.features && geojson.features.length) {
    L.geoJSON(geojson, {
      style: () => ({
        color,
        weight: 1,
        fillColor: color,
        opacity,
        fillOpacity: opacity * 0.6,
      }),
      onEachFeature: (feature, layer) => layer.bindPopup(popup),
    }).addTo(currentLandcoverLayer);
  }

  const toggle = document.getElementById('ly-landcover');
  if (toggle && !toggle.checked) {
    map.removeLayer(currentLandcoverLayer);
  }
}

function clearLandcoverOverlay() {
  currentLandcoverLayer?.clearLayers();
}

function clearUploadedRaster() {
  uploadedImageLayer?.clearLayers();
}

function clearMapOverlays() {
  markerLayer?.clearLayers();
  aoiLayer?.clearLayers();
  waterLayer?.clearLayers();
  indexLayer?.clearLayers();
  clearUploadedRaster();
  clearLandcoverOverlay();
}

window.MapUI = {
  initMap,
  showLocation,
  showOsmWater,
  showIndexPoints,
  showMaskGeoJSON,
  clearIndexLayer,
  startAreaSelection,
  finishAreaSelection,
  cancelAreaSelection,
  clearAreaSelection,
  getManualAoi,
  hasAreaPoints,
  isAreaDrawing,
  validateManualAoi,
  getManualAoiCenter,
  fitManualAoi,
  areaKm2,
  showUploadedRaster,
  showLandcoverOverlay,
  clearLandcoverOverlay,
  clearUploadedRaster,
  clearMapOverlays,
  setLandcoverOpacity,
};
