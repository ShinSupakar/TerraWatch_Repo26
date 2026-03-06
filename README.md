# 🌍 TerraWatch: Advanced AI-Driven Crisis Management Platform
### *Bridging the "Information Void" from T+0 to Field Recovery*

TerraWatch is a high-fidelity disaster response system designed to provide actionable intelligence in the first 72 hours of a seismic event. This branch (**full-demo**) integrates real-time geophysics, multimodal AI, and resilient edge architecture into a single, unified command dashboard.

---

## � Architecture Overview
TerraWatch uses a multi-layered architecture designed for resilience in low-connectivity environments.

```mermaid
graph TD
    subgraph "Field / Edge (PWA)"
        A[Offline Field Report] --> B(IndexedDB Queue)
        B --> C{Online?}
        C -- Yes --> D[API Sync - /api/report]
    }

    subgraph "Data Ingest (Backend)"
        E[Live CCTV Feed] -- Socket/Video --> F[FastAPI /api/damage/video]
        G[USGS ComCat] -- Poll 60s --> H[Geophysics Hazard Engine]
        I[WorldPop Rasters] -- Overlay --> J[Exposure Assessment]
    }

    subgraph "AI Inference Layer"
        D & F --> K[YOLOv8 Damage Detection]
        H --> L[Aftershock Transformer]
        K --> M[ESRGAN Super-Res]
    }

    subgraph "Command HQ Dashboard"
        J & L & M --> N[Real-time Leaflet Map]
        N --> O[Rescue Priority Queue]
        O --> P[Layman Public Brief]
    }
```

---

## ⏳ Evolution of Response: The Four Stages
TerraWatch is designed to scale its data confidence as an incident progresses through four distinct operational stages:

| **Stage** | **Timeframe** | **Data Source** | **Visualized Content** | **Confidence Label** |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1** | T+0 to T+5min | USGS + WorldPop | ShakeMap intensity grid & demographic exposure estimates. | **IMPACT ESTIMATE — Population model only.** |
| **Stage 2** | T+5 to T+30min | CCTV / IP Feeds | Building-level damage counts processed from existing camera networks. | **PARTIAL ASSESSMENT — Camera coverage only.** |
| **Stage 3** | T+1hr to T+6hr | PWA Field Reports | GPS-tagged, human-verified damage reports from responders in the zone. | **FIELD VERIFIED — Responder reports.** |
| **Stage 4** | T+6hr to T+48hr | Satellite + ML | Full-region high-res assessment processed via ESRGAN + YOLOv8n. | **FULL ASSESSMENT — Satellite + ML pipeline.** |

---

## 📁 Project Structure
```text
.
├── backend.py                   # FastAPI / AI Logic
├── data/                        # USGS Catalogs & Field Reports
│   └── usgs_catalog.csv
├── frontend/                    # React / Vite / PWA Source
│   ├── src/App.jsx              # Main Dashboard
│   ├── src/ShakeMapViewer.jsx   # Leaflet Map Engine
│   └── src/offlineSync.js       # PWA IndexedDB Logic
├── scripts/                     # Asset Management
│   ├── check_assets.py
│   └── fetch_weights.sh
├── terrawatch/                  # AI Weight Storage & ML Specs
│   └── models/
├── Dockerfile                   # Containerization
├── docker-compose.yml           # Local Cluster orchestration
├── README.md                    # Platform Documentation
└── *.mp4                        # High-fidelity Demo CCTV Footage
```

---

## �🚀 Key Platform Features

### 1. ⚡ Live ShakeMap & Demographic Exposure (Real-Time)
- **Automatic Polling:** Background tasks monitor the USGS ComCat feed every 60s for new M5+ events.
- **Dynamic Shaking Overlays:** Automatically fetches/generates ShakeMap grids.
- **WorldPop Integration:** Cross-references intensity polygons with global 100m population density data to estimate people exposed in minutes.
- **Interactive Heatmap:** Custom Leaflet-powered engine renders seismic intensity as color-coded polygons.

### 2. 📹 CCTV & Video Damage Assessment (Computer Vision)
- **Multimodal Inference:** Upload Recorded CCTV footage to detect structural damage.
- **YOLOv8n Triage:** Identifies `Destroyed`, `Major Damage`, and `Minor Damage` to feed the Rescue Priority Queue.
- **Demo Assets:** Pre-rendered footage from Turkey, Nepal, and Japan included.

### 3. 📵 Offline-First PWA (Resilient Field Mode)
- **Installable Native UI:** Standalone PWA experience (Installable to Home Screen).
- **IndexedDB Sync Engine:** Queue damage reports in "Signal-Zero" zones that automatically synchronize upon connection return.
- **Service Worker Caching:** Zero-latency UI loading during network collapse.

---

## 🏗 System Architecture & Design Choices
- **Design Philosophy: Resilience by Design**: Every AI component is designed with a "Deterministic Fallback" mode. If weights (YOLO, ESRGAN) are missing, the backend switches to physics-based stubs, ensuring CQHQ never goes blind.
- **Tech Stack**:
  - **Backend**: FastAPI, Asyncio, Httpx.
  - **AI/ML**: PyTorch (Transformer), Ultralytics (YOLOv8), Real-ESRGAN.
  - **Frontend**: React, Vite, Workbox (PWA), Leaflet.

---

## 🐳 Quick Start (Docker)

```bash
# Ensure weights exist locally
bash scripts/check_assets.py
docker compose up --build
```
- **Backend/Frontend Root:** `http://localhost:8000`
- **Health Check:** `GET /health`

---

## 💻 Local Run in VS Code (Recommended)
1. Open root folder.
2. Setup Venv & Install Deps (`requirements.txt`).
3. Run `start_all.sh` to launch both servers.
4. **Open `http://127.0.0.1:5173`**

---

## ⚙️ Environment Variables
- `USGS_POLL_SECONDS` (default: `60`) - Real-time polling frequency.
- `LIVE_CATALOG_HOURS` (default: `48`) - Historical seismicity window.
- `ESRGAN_WEIGHTS_PATH` - Path to Super-Res model.

---

## 📡 Key API Endpoints
- `GET /api/shakemap/latest`: Returns current seismic event + impact.
- `GET /api/shakemap/{event_id}`: Returns intensity grid × population.
- `POST /api/damage/video`: Uploads CCTV for structural triage.
- `POST /api/report`: Accepts multi-part field reports from offline responders.

---

## 🛡 Resilient Implementation & Fallbacks
- **Feature Robustness**: If the YOLO model fails to load, the backend switches to a **Deterministic Demo Output** so the UI remains functional.
- **PWA Offlining**: The Workbox service worker will serve cached content if the backend is unreachable.

---

## 🏗 Future Production Scaling
- **Raster Integration**: Moving from stubs to live WorldPop API cell lookups.
- **LLM Safety Briefs**: Integrating Llama 3 on-edge for localized risk summaries based on intensity.

## 🧪 Testbench
Required testing documentation found in `testbench/`.

---
*TerraWatch — Scaling response beyond the signal.*
