# 🌍 TerraWatch: Advanced Crisis Dashboard
### *Full Demo Edition — [Offline PWA + Live ShakeMap + Multimodal AI]*

TerraWatch is a next-generation disaster response platform designed to provide actionable intelligence from **T+0** (the moment a quake hits) to **T+72h** (field recovery). This branch integrates three mission-critical features into a single, cohesive emergency response system.

---

## 🔥 Key Demo Features

### 1. ⚡ Zero-Hour ShakeMap & Demographic Exposure (Live)
**Actionable at T+0.**
- **Automatic Polling:** Background tasks check the USGS ComCat feed every 60s for new M5+ events.
- **Dynamic Shaking Overlays:** When an event occurs, TerraWatch fetches/generates a ShakeMap grid.
- **WorldPop Integration:** Shaking intensity is automatically cross-referenced against global 100m population density data to output "Estimated X people exposed in high-shaking zone" within minutes—before any satellite/recon imagery exists.
- **Interactive Heatmap:** A custom Leaflet-powered engine renders the seismic intensity as a color-coded heatmap over the incident site.

### 2. 📹 CCTV & Video Damage Assessment (AI)
**Refining the damage picture.**
- **Video Inference:** Upload recorded CCTV footage (`.mp4`, `.mov`) from disaster zones.
- **Automated Scanning:** The YOLOv8n detector scans video frames to count destroyed vs. minor structural damage.
- **Decision Prioritization:** Aggregated video data feeds directly into the Rescue Priority Queue, helping commanders decide where to send teams first based on visual evidence of destruction.
- **Demo Assets:** Includes pre-rendered CCTV footage for Turkey (2023), Nepal (2015), and Japan (2011) to showcase the system.

### 3. 📵 Offline-First PWA (Field Responder Mode)
**Reliable in Signal-Zero zones.**
- **Installable Native Experience:** Install TerraWatch to your smartphone Home Screen with a custom icon and standalone UI.
- **Service Worker Caching:** The entire dashboard UI loads instantly from local cache even with *no internet connection*.
- **IndexedDB Offline Queue:** Field responders can draft and "Submit" damage reports while deep in a disaster zone. Reports are queued locally in `IndexedDB`.
- **Automatic Sync:** The moment the responder re-enters cellular/Wi-Fi signal, the background service worker automatically synchronizes the backlog to the Command HQ API.

---

## 🚀 Quick Start (Full Demo)

### 🛠 1. Prerequisites
Ensure you have Python 3.9+ and Node.js 18+ installed.

### 📦 2. Setup
```bash
# Install Backend Dependencies
./.venv/bin/pip install -r requirements.txt

# Install Frontend Dependencies
cd frontend
npm install
cd ..
```

### ⚡ 3. Start the Platform
Run the consolidated start script to launch both the FastAPI backend and the Vite frontend:
```bash
./start_all.sh
```

- **Dashbord URL:** `http://127.0.0.1:5173`
- **Backend API:** `http://127.0.0.1:8000`
- **API Docs (Swagger):** `http://127.0.0.1:8000/docs`

---

## 🧪 How to Test for Demo

### Test 1: Live ShakeMap
1. Open the dashboard.
2. Scroll down the center panel to find the **Live ShakeMap × WorldPop Overlay**.
3. Observe real-time data from the latest global M5+ earthquake.
4. Hover over the intensity tiles to see estimated population counts for those specific 5km cells.

### Test 2: CCTV Analysis
1. Select the **Turkey-Syria Earthquake** from the sidebar.
2. Under "CCTV / Video Assessment," upload `turkey_2023_cctv.mp4` from the project root.
3. Click **ANALYSE VIDEO**.
4. Watch as the AI identifies structures and updates the "Rescue Decision Output" and "Detections" statistics.

### Test 3: Offline Sync (Responder Flow)
1. Open the dashboard in **Chrome**.
2. Right-click → Inspect → **Network Tab**.
3. Select **"Offline"** in the throttling dropdown.
4. Scroll to **Field Report (PWA Offline)**.
5. Enter a report: *"Block 12 collapsed, requires medical evac."*
6. Click **QUEUE REPORT (OFFLINE)**. Note the Live Feed confirmation.
7. Switch Network back to **"No Throttling"**.
8. Observe the Live Feed: `Synced X offline reports`. The data is now live at HQ.

---

## 📂 Project Structure Extensions
- `frontend/src/ShakeMapViewer.jsx`: Leaflet component for demographic heatmaps.
- `frontend/src/offlineSync.js`: IndexedDB management logic for disconnected zones.
- `backend.py`: Added background USGS polling, WorldPop synthesis, and report persistence.
- `*.mp4`: High-fidelity curated CCTV footage for demonstration purposes.

---
*TerraWatch — Scaling response beyond the signal.*
