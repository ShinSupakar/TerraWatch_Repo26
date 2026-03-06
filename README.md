# 🌍 TerraWatch: Advanced AI-Driven Crisis Management Platform
### *Bridging the "Information Void" from T+0 to Field Recovery*

TerraWatch is a high-fidelity disaster response system designed to provide actionable intelligence in the first 72 hours of a seismic event. This branch (**full-demo**) integrates real-time geophysics, multimodal AI, and resilient edge architecture into a single, unified command dashboard.

---

## Key Platform Features

### 1. Live ShakeMap & Demographic Exposure (Real-Time)
- **Automatic Polling:** Background tasks monitor the USGS ComCat feed every 60s for new M5+ events.
- **Dynamic Shaking Overlays:** Automatically fetches/generates ShakeMap grids.
- **WorldPop Integration:** Cross-references intensity polygons with global 100m population density data to estimate "Estimated Exposed Population" within minutes of an event.
- **Interactive Heatmap:** Custom Leaflet-powered engine renders seismic intensity as color-coded polygons.

### 2. CCTV & Video Damage Assessment (Computer Vision)
- **Multimodal Inference:** Upload Recorded CCTV footage to detect structural damage.
- **YOLOv8n Triage:** Identifies `Destroyed`, `Major Damage`, and `Minor Damage` to feed the Rescue Priority Queue.
- **Demo Ready:** Curated video assets for Turkey, Nepal, and Japan are included.

### 3. Offline-First PWA (Resilient Field Mode)
- **Installable Native UI:** Standalone PWA experience for mobile responders.
- **IndexedDB Sync Engine:** Queue damage reports in "Signal-Zero" zones that automatically synchronize upon connection return.
- **Service Worker Caching:** Zero-latency UI loading during network collapse.

---

## System Architecture & Design

### Design Philosophy: Resilience by Design
TerraWatch is built to be **Resilient**. Every AI component is designed with a "Deterministic Fallback" mode. If weights (YOLO, ESRGAN) are missing or the system is under compute load, it gracefully degrades to physics-based stubs, ensuring the Command HQ never goes blind.

### Tech Stack
- **Backend:** FastAPI (Python), Uvicorn, Asyncio, Httpx.
- **AI/ML:** PyTorch (Aftershock Transformer), Ultralytics (YOLOv8), Real-ESRGAN (Super-Res).
- **Geospatial:** Leaflet, GeoJSON, WorldPop Density Rasters.
- **Frontend:** React, Vite, Workbox (PWA), IndexedDB (IDB).

---

## Project Files

- `backend.py`: FastAPI application containing all geophysical and AI service logic.
- `requirements.txt`: Python dependencies.
- `Dockerfile`: Container build for the consolidated backend.
- `docker-compose.yml`: One-command local deployment.
- `start_all.sh` / `stop_all.sh`: Helper scripts for local process management.

---

## Quick Start (Docker)

> **Pre‑build step:** Ensure the weight files exist locally. Run the asset checker (which auto-fetches the ESRGAN model if missing) or invoke the fetch script directly:
>
> ```bash
> bash scripts/check_assets.py   # or: bash scripts/fetch_weights.sh
> ```
>
> The Dockerfile copies these files into the image; the build will fail if they are absent.

```bash
docker compose up --build
```

- **Backend URL:** `http://localhost:8000`
- **Frontend URL (Served by FastAPI):** `http://localhost:8000/`
- **Health Check:** `GET http://localhost:8000/health`

**Docker image bundles:**
- Frontend static build (`frontend/dist`)
- `aftershock_transformer_scripted.pt`
- YOLO weights (`terrawatch/models/.../weights/best.pt`)
- Real-ESRGAN weights (`terrawatch/RealESRGAN_x4plus.pth`)

---

## Local Run in VS Code (Recommended)

1. Open the project root folder in VS Code.
2. Copy `.env.example` to `.env`.
3. Run task: `Python: Create venv`.
4. Run task: `Python: Install backend deps`.
5. Run task: `Frontend: Install deps`.
6. (Optional sanity check) run: `python3 scripts/check_assets.py`

7. **Start Backend:**
   - Launch config: `TerraWatch Backend (uvicorn)`
   - or task: `Backend: Run uvicorn`

8. **Open `http://127.0.0.1:8000`**

Separate Frontend Run: `Frontend: Run dev server` (`http://127.0.0.1:5173`).

### One-Command Local Start
```bash
./start_all.sh
```
*Logs available in `.run/backend.log` and `.run/frontend.log`.*

---

## Required Model & Asset Locations

- `./aftershock_transformer_scripted.pt` (TorchScript aftershock model)
- `./terrawatch/models/enhanced_yolov8n/weights/best.pt` (Preferred detector)
- `./terrawatch/models/baseline_yolov8n/weights/best.pt` (Fallback detector)

> **Note:** Real-ESRGAN weights (~25MB) are not checked in. You can obtain them via:
> 1. `bash scripts/fetch_weights.sh`
> 2. Manual download to `./terrawatch/RealESRGAN_x4plus.pth`

---

## Convenience & Scaling

- **`scripts/check_assets.py`**: Verifies required models and hints about missing weights.
- **`scripts/fetch_weights.sh`**: Downloads Real-ESRGAN and YOLO weights if missing.

### Local Frontend Development (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
- **Vite Dev Server:** `http://localhost:5173`
- **Proxy:** Configured in `vite.config.js` to route `/api` and `/ws` to port 8000.

---

## Environment Variables
- `USGS_POLL_SECONDS` (default: `60`) - Frequency of real-time event checks.
- `LIVE_CATALOG_HOURS` (default: `48`) - Rolling window for seismicity.
- `YOLO_CONF_THRESHOLD` (default: `0.25`) - Detection sensitivity.
- `AFTERSHOCK_MODEL_PATH` - Path to the `.pt` transformer.

---

## Key API Endpoints

### Health & Live Feed
- `GET /health`: Engine status and model load check.
- `WS /ws/live`: Real-time incident stream.

### ShakeMap & Impact
- `GET /api/shakemap/latest`: Returns latest M5+ event + impact assessment.
- `GET /api/shakemap/{event_id}`: Returns GeoJSON grid of intensity × population.
- `POST /api/impact/{event_id}`: Triggers population exposure calculation.

### AI Assessment
- `POST /api/damage/video`: Uploads CCTV for structural triage.
- `POST /api/damage`: Endpoint for drone/satellite image enhancement.

### Mobile/PWA
- `POST /api/report`: Accepts multi-part field reports from offline responders.

---

## Example Requests

### Aftershock Forecast
```bash
curl -X POST http://localhost:8000/api/aftershock \
  -H "Content-Type: application/json" \
  -d '{
    "mainshock": {"magnitude": 6.7, "latitude": 37.65, "longitude": -122.45},
    "historical_seismicity_48h": [0,1,0,2... (48 integers)]
  }'
```

---

## Resilient Implementation & Fallbacks

The system is designed to run immediately while supporting production-grade upgrades.
- **Feature Robustness**: If the YOLO model fails to load, the backend switches to a **Deterministic Demo Output** so the UI remains functional for the commander.
- **Geographic Resilience**: If certain regional fault data is missing, the Hazard Engine uses physics-based **Joyner-Boore point-source stubs** to continue providing risk estimates.
- **PWA Offlining**: The Workbox service worker will serve cached content if the backend is unreachable.

---

## Future Production Scaling
- **Population Density**: Replace stub with real-time Raster cell lookups against the WorldPop API.
- **Fault Geometry**: Integrate real-time fault distance against OSM/GEM datasets.
- **LLM Safety Briefs**: Replace stubs with Llama 3 on-edge to provide localized instructions based on intensity.

## Testbench
See documentation in:
- `testbench/SETUP_AND_RUN.md`
- `testbench/INFERENCE_TESTS.md`


