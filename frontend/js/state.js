/**
 * SatQuery AI — Shared client-side state
 * Global active location, real administrative boundary, and AOI persist across all 7 pages.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'satquery_shared_state_v2';
  const SETTINGS_KEY = 'satquery_settings_v2';

  const defaultState = {
    location: null,       // { place_name, display_name, admin_level, country, state, district, lat, lon, bbox, geometry, area_km2, has_real_boundary, ... }
    aoi: null,            // GeoJSON Polygon / MultiPolygon geometry
    aoiAreaKm2: null,     // Geodesic area in km²
    aoiAreaHa: null,      // Geodesic area in hectares
    aoiAreaSqFt: null,    // Geodesic area in sq ft
    selectedScene: null,
    lastAnalysisId: null,
    imageId: null,
    activeBasemap: 'satellite', // 'satellite' | 'default'
  };

  const defaultSettings = {
    theme: 'dark',                    // 'light' | 'dark'
    defaultBasemap: 'satellite',      // 'satellite' | 'default'
    notificationType: 'default',      // 'email'
  };

  function load(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return { ...fallback };
      return { ...fallback, ...JSON.parse(raw) };
    } catch (e) {
      console.warn('[state] load failed', e);
      return { ...fallback };
    }
  }

  function save(key, obj) {
    try {
      localStorage.setItem(key, JSON.stringify(obj));
    } catch (e) {
      console.warn('[state] save failed', e);
    }
  }

  let state = load(STORAGE_KEY, defaultState);
  let settings = load(SETTINGS_KEY, defaultSettings);

  const listeners = new Set();

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

  function notify(change = {}) {
    listeners.forEach((fn) => {
      try { fn(state, settings, change); } catch (e) { console.error(e); }
    });
  }

  window.SharedState = {
    get() { return { ...state }; },
    getSettings() { return { ...settings }; },

    setLocation(loc) {
      const changed = locationKey(state.location) !== locationKey(loc);
      state.location = loc ? { ...loc } : null;

      if (loc && (loc.geometry || loc.aoi) && (loc.has_real_boundary || loc.geometry?.type === 'Polygon' || loc.geometry?.type === 'MultiPolygon')) {
        state.aoi = loc.geometry || loc.aoi;
        state.aoiAreaKm2 = loc.area_km2 || loc.aoi_area_km2 || null;
        state.aoiAreaHa = loc.area_ha || (state.aoiAreaKm2 ? state.aoiAreaKm2 * 100 : null);
        state.aoiAreaSqFt = loc.area_sqft || (state.aoiAreaKm2 ? state.aoiAreaKm2 * 10763910.41671 : null);
      } else if (changed && !loc?.aoi) {
        state.aoi = null;
        state.aoiAreaKm2 = null;
        state.aoiAreaHa = null;
        state.aoiAreaSqFt = null;
      }

      state.selectedScene = null;
      state.lastAnalysisId = null;
      save(STORAGE_KEY, state);
      notify({ type: 'location', changed });
    },

    setAoi(aoi, areaKm2) {
      state.aoi = aoi || null;
      state.aoiAreaKm2 = areaKm2 != null ? Number(areaKm2) : null;
      state.aoiAreaHa = state.aoiAreaKm2 != null ? state.aoiAreaKm2 * 100.0 : null;
      state.aoiAreaSqFt = state.aoiAreaKm2 != null ? state.aoiAreaKm2 * 10763910.41671 : null;
      state.selectedScene = null;
      state.lastAnalysisId = null;
      save(STORAGE_KEY, state);
      notify({ type: 'aoi', changed: true });
    },

    setScene(scene) {
      state.selectedScene = scene || null;
      save(STORAGE_KEY, state);
      notify({ type: 'scene' });
    },

    setImageId(id) {
      state.imageId = id || null;
      save(STORAGE_KEY, state);
      notify({ type: 'image' });
    },

    setAnalysisId(id) {
      state.lastAnalysisId = id || null;
      save(STORAGE_KEY, state);
      notify({ type: 'analysis' });
    },

    setBasemap(basemap) {
      const bm = basemap === 'default' ? 'default' : 'satellite';
      state.activeBasemap = bm;
      save(STORAGE_KEY, state);
      notify({ type: 'basemap', basemap: bm });
    },

    clearArea() {
      state.aoi = null;
      state.aoiAreaKm2 = null;
      state.aoiAreaHa = null;
      state.aoiAreaSqFt = null;
      state.selectedScene = null;
      state.lastAnalysisId = null;
      state.imageId = null;
      save(STORAGE_KEY, state);
      notify({ type: 'aoi', changed: true });
    },

    setTheme(theme) {
      settings.theme = theme === 'light' ? 'light' : 'dark';
      save(SETTINGS_KEY, settings);
      document.documentElement.setAttribute('data-theme', settings.theme);
      notify({ type: 'theme' });
    },

    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },

    applyTheme() {
      document.documentElement.setAttribute('data-theme', settings.theme);
    },
  };

  // Apply immediately on load
  window.SharedState.applyTheme();
})();
