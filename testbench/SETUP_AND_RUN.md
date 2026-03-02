# TerraWatch Testbench: Setup and Run

This document is for graders to run the project end-to-end.

## 1) Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- macOS/Linux shell (bash/zsh)

## 2) Open Project

```bash
cd <PROJECT_ROOT>
```

## 3) Backend Environment

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## 4) Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## 5) Asset Verification

```bash
python3 scripts/check_assets.py
```

Expected: all required assets show `[OK]`.

## 6) Run Both Services

```bash
./start_all.sh
```

URLs:
- Backend: http://127.0.0.1:8000
- Frontend Dev: http://127.0.0.1:5173
- Backend-served Frontend: http://127.0.0.1:8000

### Docker Alternative (Uniform Judge Setup)

```bash
docker compose up --build
```

Then open:
- http://127.0.0.1:8000

Stop:

```bash
docker compose down
```

## 7) Stop Services

```bash
./stop_all.sh
```

## 8) VS Code Alternative

- Run `Python: Create venv` task
- Run `Python: Install backend deps` task
- Run `Frontend: Install deps` task
- Start launch config: `TerraWatch Backend (uvicorn)`

## 9) Docker and Uniformity Guidance

### Why Docker matters here

Docker is used to make runtime behavior reproducible across machines (same OS libs, same Python stack, same startup behavior), which helps judges run the app consistently.

### Current project Docker scope

- Current `docker-compose.yml` is backend-focused.
- Frontend can still be served by backend static build (`frontend/dist`) or run separately with Vite.

### Recommended uniform grading setup

1. Use one fixed backend port (default `8000`) for all tests.
2. Use the `BASE` variable pattern from `testbench/INFERENCE_TESTS.md`.
3. Validate APIs using terminal `curl` POST commands (not browser GET).
4. Use the same sample image paths listed in the testbench for consistent outputs.
