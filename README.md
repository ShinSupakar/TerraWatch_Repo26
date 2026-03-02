# TerraWatch Backend

Production-style FastAPI backend for TerraWatch disaster prediction and response workflows.

## Features

- Geophysics hazard engine:
  - Historical focal depth autofill from cached USGS catalog.
  - PGA estimation using a Joyner-Boore-style attenuation relation.
  - Worst-case design-basis earthquake simulation.
- AI aftershock forecaster:
  - TorchScript model loading (`aftershock_transformer_scripted.pt`).
  - 6-feature normalization + 48-hour historical seismicity input.
  - 24-hour M4+ probability output.
- Live data + geospatial:
  - Background USGS ComCat polling (rolling 48-hour history).
  - Fault distance mock service (swap with OSM/GEM implementation).
- Zero-hour impact:
  - ShakeMap fetch workflow (with synthetic fallback).
  - Population overlay and impact/casualty estimation stub.
- Multimodal CV damage assessment:
  - `/api/damage` accepts imagery.
  - ESRGAN + YOLOv8n detailed stubs (easy to replace with local weights).
  - Causative quake tagging via nearest-event lookup.
- IoT + crowdsourcing + realtime:
  - Sensor ingest (`/api/sensor`), citizen reports (`/api/report`), WebSocket live stream (`/ws/live`).
- Layman translation engine:
  - `/api/layman_summary` returns strict JSON-safe public safety text output.

## Project Files

- `backend.py`: FastAPI application and all service logic.
- `requirements.txt`: Python dependencies.
- `Dockerfile`: Container build for backend.
- `docker-compose.yml`: One-command local deployment.

## Quick Start (Docker)

```bash
docker compose up --build
```

Backend URL:

- `http://localhost:8000`
- Frontend URL (served by FastAPI): `http://localhost:8000/`

Health check:

- `GET http://localhost:8000/health`

Docker image now bundles:
- frontend static build (`frontend/dist`)
- `aftershock_transformer_scripted.pt`
- YOLO weights (`terrawatch/models/.../weights/best.pt`)
- Real-ESRGAN weights (`terrawatch/RealESRGAN_x4plus.pth`)

So a single `docker compose up --build` is enough for uniform evaluator setup.

## Local Run in VS Code (Recommended)

1. Open the project root folder in VS Code.
2. Copy `.env.example` to `.env`.
3. Run task: `Python: Create venv`.
4. Run task: `Python: Install backend deps`.
5. Run task: `Frontend: Install deps`.
6. (Optional sanity check) run:

```bash
python3 scripts/check_assets.py
```

7. Start backend:
   - Launch config: `TerraWatch Backend (uvicorn)`
   - or task: `Backend: Run uvicorn`
8. Open `http://127.0.0.1:8000`

You can run frontend separately with task `Frontend: Run dev server` (`http://127.0.0.1:5173`).

### One-Command Local Start

```bash
./start_all.sh
```

This starts backend + frontend and writes logs to `.run/backend.log` and `.run/frontend.log`.

To stop:

```bash
./stop_all.sh
```

### Required Model/Data Asset Locations

- `./aftershock_transformer_scripted.pt` (aftershock TorchScript model)
- `./terrawatch/RealESRGAN_x4plus.pth` (image enhancement model)
- `./terrawatch/models/enhanced_yolov8n/weights/best.pt` (preferred detector)
- `./terrawatch/models/baseline_yolov8n/weights/best.pt` (fallback detector)

## Local Frontend Development (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Vite dev server:

- `http://localhost:5173`

To point Vite at a separate backend host, set:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

To build frontend for FastAPI static hosting:

```bash
cd frontend
npm run build
```

## Environment Variables

- `LOG_LEVEL` (default: `INFO`)
- `TERRAWATCH_DATA_DIR` (default: `./data`)
- `USGS_CACHE_CSV` (default: `./data/usgs_catalog.csv`)
- `AFTERSHOCK_MODEL_PATH` (default: `./aftershock_transformer_scripted.pt`)
- `USGS_POLL_SECONDS` (default: `180`)
- `LIVE_CATALOG_HOURS` (default: `48`)
- `TERRAWATCH_MODEL_ROOT` (default: `./terrawatch/models`)
- `YOLO_RUNS_DIR` (default: `./runs/detect`)
- `YOLO_WEIGHTS_PATH` (default: auto-discovery)
- `YOLO_CONF_THRESHOLD` (default: `0.25`)
- `YOLO_IOU_THRESHOLD` (default: `0.45`)
- `YOLO_IMAGE_SIZE` (default: `640`)
- `ESRGAN_WEIGHTS_PATH` (default: `./terrawatch/RealESRGAN_x4plus.pth`)
- `ESRGAN_SCALE` (default: `4`)
- `ESRGAN_OUTSCALE` (default: `2.0`)

## Key API Endpoints

### Health

- `GET /health`

### Hazard Engine

- `POST /api/hazard/depth`
- `POST /api/hazard/pga`
- `POST /api/hazard/worst_case`

### AI Forecaster

- `POST /api/aftershock`

### Live + Geospatial

- `GET /api/live/events`
- `POST /api/fault_distance`

### ShakeMap + Impact

- `POST /api/shakemap`
- `POST /api/impact/{event_id}`

### Damage Assessment

- `POST /api/damage` (multipart form-data, image + optional lat/lon)

### IoT + Crowdsourcing

- `POST /api/sensor`
- `POST /api/report` (multipart form-data)
- `WS /ws/live`

### Layman Summary

- `POST /api/layman_summary`

## Example Requests

### Aftershock Forecast

```bash
curl -X POST http://localhost:8000/api/aftershock \
  -H "Content-Type: application/json" \
  -d '{
    "mainshock": {
      "magnitude": 6.7,
      "depth_km": 14.2,
      "latitude": 37.65,
      "longitude": -122.45,
      "hour_utc": 9,
      "day_of_year": 60
    },
    "historical_seismicity_48h": [
      0,1,0,2,1,0,0,1,1,0,0,0,
      1,2,1,0,0,0,1,1,0,0,2,1,
      0,0,1,0,1,1,0,0,0,1,0,0,
      1,0,2,1,0,0,0,1,1,0,0,1
    ]
  }'
```

### Layman Summary

```bash
curl -X POST http://localhost:8000/api/layman_summary \
  -H "Content-Type: application/json" \
  -d '{
    "magnitude": 6.8,
    "focal_depth_km": 12.0,
    "pga_percent_g": 42.5,
    "aftershock_probability_24h": 0.61
  }'
```

## Notes for Model/Data Swap

- Real-ESRGAN and YOLOv8n inference are loaded dynamically when weights are found.
- If a model file is missing or fails to load, backend falls back to deterministic stubs.
- Replace `population_density_stub` with raster/census lookup.
- Replace `nearest_fault_distance` with line-to-point distance against OSM/GEM fault geometries.
- Replace layman translation stub with your LLM provider call while keeping strict JSON schema.

## Testbench (For Graders)

Required testing docs are in:

- `testbench/SETUP_AND_RUN.md`
- `testbench/INFERENCE_TESTS.md`
