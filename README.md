# SatQuery AI (Upgraded)

**Interactive Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Text Queries**

Smart India Hackathon — SIH26167

## Upgrade highlights (this build)

| Feature | Status |
|---------|--------|
| **Real VQA** | Pluggable VLM provider (`backend/ai/vlm_provider.py`). Uses hosted API when `VLM_API_KEY` is set; otherwise evidence-only answers grounded in NDVI/NDWI/NDBI + STAC metadata. **Never fabricates numbers.** |
| **Conversational chat** | `POST /api/chat/message`, `GET /api/chat/history/{id}`, SQLite sessions (`data/satquery.db`). Frontend scrolling chat panel with evidence chips. |
| **Uploaded image everywhere** | `image_id` threaded into VQA / captioning / grounding. `GET /api/images/{id}/preview.png?render=rgb\|false\|ndvi\|ndwi\|ndbi`. |
| **Visual grounding** | Spectral masks → GeoJSON polygons + area km² + bboxes via `grounding.py` / chat. |
| **Captioning** | Image-derived via VLM when chip available; metadata fallback with `degraded: true`. |

### Quick start (Windows / VS Code)

```bash
# 1. Unzip, open folder in VS Code
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 2. Optional: copy .env.example → .env and set VLM_API_KEY for neural VQA
copy .env.example .env

# 3. Run
python run.py
# Open http://127.0.0.1:8000
```

### Manual tests (priority features)

1. **VQA (evidence-only)**  
   - Search location e.g. `Chilika Lake`.  
   - Ask: `What is the water extent and NDWI in this area?`  
   - Expect answer citing NDWI/area or honest "could not compute".

2. **Chat multi-turn**  
   - Ask about water, then follow up: `and what about vegetation?`  
   - Same `session_id` should be reused; bubbles appear in chat panel.

3. **Image upload + preview + grounding**  
   - Upload a multi-band GeoTIFF.  
   - Open `/api/images/{image_id}/preview.png?render=ndvi` in browser.  
   - Ask: `show me where the water is` → grounded GeoJSON on map + area km².

4. **No fabrication**  
   - With no VLM key and no bands: answers must say data unavailable, not invent %.

---

# SatQuery AI

**Interactive Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Text Queries**

Smart India Hackathon 2026 — Problem Statement **SIH26167**

Mode: **REAL_DATA_MODE** by default (`DEMO_MODE=false`).  
The app does **not** invent satellite percentages, gauge levels, or observation dates.

---

## What works (real external data)

| Capability | Source / method |
|------------|-----------------|
| Place search + AOI | Nominatim (OpenStreetMap) |
| Interactive map | Leaflet + OSM tiles (base map ≠ satellite) |
| Satellite scene search | Microsoft Planetary Computer STAC |
| Sentinel-2 / Landsat / Sentinel-1 discovery | Planetary Computer collections |
| Optical indices NDVI / NDWI / NDBI | Real COG band windowed reads when reachable |
| Weather | Open-Meteo (no API key) |
| Named rivers / lakes | OSM Overpass |
| Agentic routing | QueryRouter → specialist tools |
| Change detection | Dual-year STAC + optional real NDWI change |
| Optical + SAR | Paired search + NDWI/NDBI + SAR backscatter stats |
| Flood-risk indicator | Evidence from rainfall + water extent availability (not official warning) |
| Reports | Downloadable text report |
| Execution trace | Observable steps in UI |
| Land-use / land-cover (baseline spectral detection) | NDWI / NDVI / NDBI on uploaded GeoTIFFs |

## Honest limitations

| Item | Status |
|------|--------|
| Fine-tuned RS-VQA checkpoint | **Not bundled** → `MODEL_UNAVAILABLE` |
| India CWC live river gauge (metres) | **Not connected** → clear unavailable message |
| Full-resolution index maps as WMS tiles | Sample points on map; full rasters need more compute |
| Same-day “live” satellite | Satellites do not revisit daily; UI shows **latest available** date |

**Water extent (km² from NDWI) ≠ gauge water level (metres).**

## Land-use / land-cover analysis (uploaded GeoTIFFs)

The app now supports a transparent baseline land-cover workflow for uploaded `.tif`/`.tiff` images. This is not a trained model unless a checkpoint is later added in the project’s model registry.

### Implemented analysis methods
- Water: NDWI using green and near-infrared bands (`Green - NIR` / `Green + NIR`)
- Agriculture: NDVI-based vegetation proxy using red and near-infrared bands
- Forest / Vegetation: NDVI thresholding using red and near-infrared bands
- Built-up: NDBI using shortwave infrared and near-infrared bands

### Required bands
- Water: green + nir
- Agriculture / Forest / Vegetation: red + nir
- Built-up: swir16 + nir

### Limitations
- These are spectral baselines, not certified land-use classifications.
- If the uploaded raster lacks the required bands or CRS, the backend returns a clear reason instead of inventing a result.
- Detection is restricted to the uploaded raster’s own geographic bounds and metadata.
- The frontend renders a georeferenced overlay aligned to the uploaded image extent.

### Frontend usage
- Upload a GeoTIFF using the existing upload section.
- Choose a category from the Land Use / Land Cover section.
- Click Analyze to send the current image ID and category to `/api/landcover/analyze`.
- The result appears in the summary panel and on the map as a bounded overlay.

---

## Windows setup (File Manager → VS Code)

### 1. Extract the ZIP

1. Download `satquery-ai.zip`
2. Right-click → **Extract All…**
3. Choose e.g. `C:\Users\<YOUR_NAME>\Documents\`
4. You should get:

```
C:\Users\<YOUR_NAME>\Documents\satquery-ai\
    frontend\
    backend\
    data\
    run.py
    requirements.txt
    .env.example
    README.md
```

### 2. Install Python 3.10+

- https://www.python.org/downloads/
- Check **“Add python.exe to PATH”**

### 3. Open in VS Code

```text
File → Open Folder → satquery-ai
```

### 4. Virtual environment + dependencies

In **Terminal** (PowerShell or cmd):

```bat
cd C:\Users\<YOUR_NAME>\Documents\satquery-ai
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**If `rasterio` / GDAL fails on Windows:**

- Prefer the conda route for geospatial stacks, **or**
- Install from https://github.com/cgohlke/geospatial-wheels (match your Python version), **or**
- Continue without full COG reads: STAC search, weather, OSM, routing still work; index areas stay metadata-only until rasterio works.

### 5. Environment file

```bat
copy .env.example .env
```

Leave keys empty unless you have Sentinel Hub / other optional services.  
**Open-Meteo, Nominatim, Planetary Computer search need no key.**

### 6. Run

```bat
python run.py
```

Open browser: **http://127.0.0.1:8000/**  
API docs: **http://127.0.0.1:8000/docs**

### 7. Quick tests

1. Location: `Karur, Tamil Nadu` → **Go**
2. Question chips: Water bodies / Rainfall / Change 2024–2025 / Optical + SAR / Flood risk
3. Confirm answers show **source + date**, not invented numbers

### 8. Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend not reachable | Ensure `python run.py` is running on port 8000 |
| Nominatim timeout | Wait / retry; do not spam (usage policy) |
| No satellite scene | Widen date range / accept higher cloud; shown honestly |
| rasterio import error | Install GDAL wheels or use conda-forge |
| VQA says MODEL_UNAVAILABLE | Expected until you add `models/vqa` checkpoint |
| Gauge level unavailable | Expected without CWC API |

---

## Linux / macOS

```bash
cd satquery-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Optional: `sudo apt-get install gdal-bin libgdal-dev`

---

## Architecture

```
Browser (Leaflet)
    → FastAPI (backend/app.py)
        → QueryRouter
        → geocoding / STAC / weather / OSM / water-level
        → raster_fetch (signed COGs) → NDVI/NDWI/NDBI
        → change / optical+SAR / flood indicator
```

### Main API endpoints

- `GET /api/location/search?q=`
- `GET /api/satellite/search`
- `GET /api/weather?lat=&lon=`
- `GET /api/water/level`
- `GET /api/water/features`
- `POST /api/analyze/query`  `{ "location": "...", "question": "..." }`
- `POST /api/report`
- `GET /api/status`

---

## Enabling optional RS-VQA

1. Obtain a legitimate remote-sensing VQA checkpoint (e.g. trained on RSVQA / related open models).
2. Place weights under `models/vqa/`.
3. Update `backend/ai/model_registry.py` / `vqa.py` to load the checkpoint.
4. Until then the API returns **MODEL_UNAVAILABLE** — never a fake answer.

---

## SIH26167 feature status

| Feature | Status |
|---------|--------|
| Single-image VQA | PARTIAL (adapter; no checkpoint) |
| Additional single-image task | IMPLEMENTED (captioning + spectral indices) |
| Multitemporal change | IMPLEMENTED (STAC + optional real NDWI Δ) |
| Optical + SAR | IMPLEMENTED (search + joint stats) |
| Agentic orchestration | IMPLEMENTED |
| RS model adapter | IMPLEMENTED |
| Natural-language queries | IMPLEMENTED |
| Visual evidence | IMPLEMENTED |
| Confidence | IMPLEMENTED (not invented) |
| Execution trace | IMPLEMENTED |
| Real satellite integration | IMPLEMENTED |

---

## Attribution

- © OpenStreetMap contributors  
- ESA Copernicus / USGS via Microsoft Planetary Computer  
- Weather: Open-Meteo  

Educational prototype for SIH 2026.
