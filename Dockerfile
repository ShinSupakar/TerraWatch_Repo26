FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/vite.config.js frontend/index.html /frontend/
COPY frontend/src /frontend/src
RUN npm install && npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

WORKDIR /app

# Runtime deps often needed by pandas/numpy/torch wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY backend.py /app/backend.py
COPY --from=frontend-builder /frontend/dist /app/frontend/dist
COPY aftershock_transformer_scripted.pt /app/aftershock_transformer_scripted.pt
COPY terrawatch/RealESRGAN_x4plus.pth /app/terrawatch/RealESRGAN_x4plus.pth
COPY terrawatch/models/enhanced_yolov8n/weights/best.pt /app/terrawatch/models/enhanced_yolov8n/weights/best.pt
COPY terrawatch/models/baseline_yolov8n/weights/best.pt /app/terrawatch/models/baseline_yolov8n/weights/best.pt
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]
