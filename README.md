# 🌍 TerraWatch: Advanced AI-Driven Crisis Management Platform
### *Bridging the "Information Void" from T+0 to Field Recovery*

TerraWatch is a high-fidelity disaster response system designed to solve the critical data gap that exists in the first 72 hours of a seismic event. By integrating real-time geophysics, multimodal AI, and resilient edge architecture, TerraWatch provides command centers with ground truth when traditional communication fails.

---

## 1. Problem Framing & Motivation

### The "Information Void" Problem
In the minutes following a major earthquake (M5.0+), authorities face a "blind period." Satellite imagery takes hours to task and download, and field reports from first responders are often delayed by cellular network collapse. Decisions involving millions of dollars and thousands of lives are made on incomplete data.

### Our Mission
TerraWatch empowers incident commanders with **Zero-Hour Impact Intelligence**. We aim to:
1. **Estimate Exposure at T+5m**: Using ShakeMap and demographic overlays before the first photo arrives.
2. **Resilient Communication**: Enable field responders to document damage in "Signal-Zero" zones.
3. **Automated Recon**: Transform existing CCTV and drone feeds into quantitative rescue priorities using Computer Vision.

---

## 2. Solution Design & Innovation

### System Architecture
TerraWatch utilizes a **Multimodal Hybrid Cloud/Edge** architecture:
- **Core Engine (Python/FastAPI)**: Orchestrates background polling, AI inference, and geospatial processing.
- **AI Triage Layer**: A chain of specialized models (Aftershock Transformers → YOLO Structural Detectors → ESRGAN Enhancers).
- **Resilient Frontend (React/PWA)**: An offline-first interface that treats "No Connection" as a first-class state, not an error.

### Innovation Highlights
- **Synthetic/Live Hybrid ShakeMap**: If USGS GeoJSON is delayed, our engine generates a physics-based intensity grid using Joyner-Boore point-source attenuation.
- **Demographic Multiplier**: We don't just show shaking; we cross-reference intensity polygons with cached **WorldPop** 100m resolution rasters to estimate human impact per 5km cell.
- **Asynchronous Sync Engine**: A custom IndexedDB implementation that handles large-scale offline damage report queuing and automatic reconciliation upon signal return.

---

## 3. Technical Depth

### Geophysical Hazard Engine
- **PGA Estimation**: Implements the Joyner-Boore acceleration model where $\log_{10}(PGA) = a + b(M-6) + c(M-6)^2 + d\log_{10}(r) + e \cdot r$, accounting for geometric spreading and anelastic attenuation.
- **Focal Depth Interpolation**: Uses historical ComCat metadata to interpolate missing depth values based on regional seismic profiles.

### Multimodal AI Models
- **AI Aftershock Forecaster**: A 1D-Transformer trained on the global USGS earthquake catalog. It ingests 48 hours of historical seismicity (6-feature vectors) to output a 24-hour M4+ probability score.
- **Structural Damage Detector**: Custom-trained YOLOv8n weights optimized for identifying `Destroyed`, `Major Damage`, and `Minor Damage` in aerial and CCTV perspectives.
- **ESRGAN (Super-Resolution)**: Post-processes low-bandwidth drone images using real-time Super-Resolution to clarify structural cracks for manual assessment.

### Resilient Implementation
- **Worker Workflow**: Background polling runs every 60s using `httpx` and `asyncio` to monitor the USGS GeoJSON feed.
- **PWA Service Workers**: Leverages `Workbox` for precaching core assets and `IndexedDB` for persistent report storage during outages.

---

## 4. Demo Effectiveness: Step-by-Step Walkthrough

### 🚀 Setup & Launch
```bash
./start_all.sh  # Launches Backend (8000) & Frontend (5173)
```

### 🎬 The Demo Sequence
1. **Live Feed (Center Panel)**: Navigate to the bottom to see the **Live ShakeMap Overlay**. This shows the most recent global M5+ quake (e.g., Alaska M5.4) with population exposure numbers pulled from WorldPop data.
2. **Video Triage**: Select **Turkey-Syria** in the sidebar. Upload `turkey_2023_cctv.mp4`. Click **ANALYSE VIDEO**. Watch the "Rescue Priority" queue update dynamically as the AI identifies severe vs. minor damage.
3. **Offline Mode**: In Chrome DevTools, set Network to **"Offline"**. Go to the "Field Report" section. Submit a report. Observe that it **Queues Locally** (Live Feed shows "queuing offline"). Toggle Network back to **"Online"** and watch the automatic sync.

---

## 5. Communication & Presentation Strategy

The dashboard is structured into three clear cognitive zones:
- **Left (Awareness)**: Live global event feed and incident selection.
- **Center (Intel)**: High-resolution visual proof (Before/After imagery and ShakeMap Heatmaps).
- **Right (Action)**: Prioritized rescue queue and AI-generated public safety briefs for laymen.

*Tip for Delivery:* Focus on the transition from **Raw Data (Left)** → **AI Assessment (Center)** → **Decision (Right)**.

---

## 6. Impact & Future Potential

### Real-World Adoption
- **NGO Deployment**: Small search-and-rescue teams can run TerraWatch locally on a laptop with a portable Wi-Fi AP, maintaining situational awareness without a backbone connection.
- **Scalability**: The system is designed to handle thousands of concurrent field reports via the asynchronous sync middleware.

### Future Roadmap
- **Satellite Change Detection**: Integration with Sentinel-1 SAR (Synthetic Aperture Radar) for cloud-penetrating damage assessment.
- **LLM Localization**: Replacing the layman summary stub with localized LLMs (Llama 3 on-edge) to provide safety instructions in dozens of regional dialects.

---
*TerraWatch — Engineering certainty in chaos.*
