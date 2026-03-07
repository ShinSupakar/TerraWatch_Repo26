from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import os
import random
import time
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Literal

if TYPE_CHECKING:
    import torch
    from PIL import Image
    import cv2

import httpx
import numpy as np
import pandas as pd

if os.getenv("DISABLE_TORCH", "0") == "1":
    torch = None
else:
    try:
        import torch
    except ImportError:
        torch = None

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
try:
    from pydantic import field_validator
except ImportError:  # pydantic v1 fallback
    from pydantic import validator as field_validator

if not hasattr(BaseModel, "model_dump"):
    BaseModel.model_dump = BaseModel.dict  # type: ignore[attr-defined]
if not hasattr(BaseModel, "model_dump_json"):
    BaseModel.model_dump_json = BaseModel.json  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("terrawatch-backend")

DATA_DIR = Path(os.getenv("TERRAWATCH_DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST_DIR = Path(os.getenv("FRONTEND_DIST_DIR", "./frontend/dist"))
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

USGS_CACHE_CSV = Path(os.getenv("USGS_CACHE_CSV", str(DATA_DIR / "usgs_catalog.csv")))
AFTERSHOCK_MODEL_PATH = Path(
    os.getenv("AFTERSHOCK_MODEL_PATH", "./aftershock_transformer_scripted.pt")
)
MODEL_ROOT = Path(os.getenv("TERRAWATCH_MODEL_ROOT", "./terrawatch/models"))
RUNS_DETECT_DIR = Path(os.getenv("YOLO_RUNS_DIR", "./runs/detect"))
YOLO_WEIGHTS_PATH_ENV = os.getenv("YOLO_WEIGHTS_PATH", "").strip()
YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.25"))
YOLO_IOU_THRESHOLD = float(os.getenv("YOLO_IOU_THRESHOLD", "0.45"))
YOLO_IMAGE_SIZE = int(os.getenv("YOLO_IMAGE_SIZE", "640"))
YOLO_FAST_IMAGE_SIZE = int(os.getenv("YOLO_FAST_IMAGE_SIZE", "512"))
ESRGAN_WEIGHTS_PATH_ENV = os.getenv("ESRGAN_WEIGHTS_PATH", "").strip()
ESRGAN_SCALE = int(os.getenv("ESRGAN_SCALE", "4"))
ESRGAN_OUTSCALE = float(os.getenv("ESRGAN_OUTSCALE", "2.0"))
MAX_DAMAGE_IMAGE_SIDE = int(os.getenv("MAX_DAMAGE_IMAGE_SIDE", "960"))
DAMAGE_DEMO_FAST_DEFAULT = os.getenv("DAMAGE_DEMO_FAST_DEFAULT", "1") == "1"

LIVE_CATALOG_HOURS = int(os.getenv("LIVE_CATALOG_HOURS", "48"))
USGS_POLL_SECONDS = int(os.getenv("USGS_POLL_SECONDS", "60"))

MMI_THREAT_MAP = [
    (5.0, "Light"),
    (15.0, "Moderate"),
    (35.0, "Strong"),
    (60.0, "Very Strong"),
    (100.0, "Severe"),
]

# Mainshock normalization stats (align to notebook feature ordering)
# [Magnitude, Depth, Latitude, Longitude, Hour, DayOfYear]
FEATURE_MEAN = np.asarray([5.8, 18.0, 12.0, 15.0, 11.5, 183.0], dtype=np.float32)
FEATURE_STD = np.asarray([1.1, 22.0, 34.0, 78.0, 6.9, 105.0], dtype=np.float32)

DEFAULT_FAULT_POINTS = [
    {"name": "San Andreas", "lat": 35.7, "lon": -120.4},
    {"name": "Cascadia", "lat": 44.7, "lon": -124.9},
    {"name": "Hayward", "lat": 37.7, "lon": -122.1},
    {"name": "New Madrid", "lat": 36.6, "lon": -89.6},
]


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class MainshockFeatures(BaseModel):
    magnitude: float = Field(..., ge=0.0, le=10.0)
    depth_km: float = Field(..., ge=0.0, le=700.0)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    hour_utc: int = Field(..., ge=0, le=23)
    day_of_year: int = Field(..., ge=1, le=366)


class DepthAutofillRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    k_neighbors: int = Field(25, ge=1, le=500)


class DepthAutofillResponse(BaseModel):
    latitude: float
    longitude: float
    average_depth_km: float
    samples_used: int


class PGACalculationRequest(BaseModel):
    magnitude: float = Field(..., ge=0.0, le=10.0)
    focal_depth_km: float = Field(..., ge=0.0, le=700.0)
    epicentral_distance_km: float = Field(..., ge=0.0, le=1000.0)


class PGACalculationResponse(BaseModel):
    pga_percent_g: float
    model: str


class WorstCaseRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    search_radius_km: float = Field(100.0, ge=1.0, le=500.0)


class WorstCaseResponse(BaseModel):
    latitude: float
    longitude: float
    search_radius_km: float
    design_basis_magnitude: float
    autofilled_depth_km: float
    assumed_epicentral_distance_km: float
    pga_percent_g: float
    historical_events_considered: int


class AftershockRequest(BaseModel):
    mainshock: MainshockFeatures
    historical_seismicity_48h: list[int] = Field(..., min_items=48, max_items=48)

    @field_validator("historical_seismicity_48h")
    @classmethod
    def validate_non_negative(cls, v: list[int]) -> list[int]:
        if any(x < 0 for x in v):
            raise ValueError("historical_seismicity_48h values must be non-negative integers")
        return v


class AftershockResponse(BaseModel):
    forecast_horizon_hours: int
    probabilities_m4_plus: list[float]
    generated_at_utc: datetime
    model_source: Literal["torchscript", "heuristic_stub"]


class FaultDistanceRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class FaultDistanceResponse(BaseModel):
    nearest_fault_name: str
    distance_km: float


class ShakeMapFetchRequest(BaseModel):
    event_id: str = Field(..., min_length=1)


class IntensityPolygon(BaseModel):
    intensity_label: str
    pga_range_percent_g: tuple[float, float]
    area_km2: float
    centroid_lat: float
    centroid_lon: float


class ShakeMapResponse(BaseModel):
    event_id: str
    polygons: list[IntensityPolygon]
    source: Literal["usgs_shakemap", "synthetic_stub"]


class ImpactAssessmentResponse(BaseModel):
    event_id: str
    exposed_population_estimate: int
    casualty_estimate_low: int
    casualty_estimate_high: int
    methodology: str


class DamageBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    damage_class: Literal[0, 1, 2, 3]
    damage_label: str


class DamageResponse(BaseModel):
    image_id: str
    image_width: int
    image_height: int
    damage_boxes: list[DamageBox]
    aggregated_counts: dict[str, int]
    max_damage_class: int
    causative_event_id: str | None
    causative_magnitude: float | None
    causative_depth_km: float | None
    enhanced_image_b64: str | None = None
    overlay_image_b64: str | None = None
    notes: str


class VideoDamageResponse(BaseModel):
    video_id: str
    frames_analyzed: int
    frame_dimensions: tuple[int, int]
    damage_boxes: list[DamageBox]
    aggregated_counts: dict[str, int]
    max_damage_class: int
    causative_event_id: str | None
    causative_magnitude: float | None
    causative_depth_km: float | None
    representative_frame_b64: str | None = None
    overlay_image_b64: str | None = None
    notes: str


class SensorReading(BaseModel):
    sensor_id: str = Field(..., min_length=2, max_length=120)
    timestamp_utc: datetime
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accel_x_g: float = Field(..., ge=-16.0, le=16.0)
    accel_y_g: float = Field(..., ge=-16.0, le=16.0)
    accel_z_g: float = Field(..., ge=-16.0, le=16.0)
    battery_pct: float = Field(..., ge=0.0, le=100.0)


class SensorAck(BaseModel):
    accepted: bool
    trigger_level: Literal["normal", "elevated", "critical"]
    acceleration_resultant_g: float


class ReportResponse(BaseModel):
    report_id: str
    stored_photo_path: str | None
    causative_event_id: str | None
    status: Literal["received"]


class LaymanSummaryRequest(BaseModel):
    magnitude: float = Field(..., ge=0.0, le=10.0)
    focal_depth_km: float = Field(..., ge=0.0, le=700.0)
    pga_percent_g: float = Field(..., ge=0.0, le=500.0)
    aftershock_probability_24h: float = Field(..., ge=0.0, le=1.0)


class LaymanSummaryResponse(BaseModel):
    threat_level: Literal["Light", "Moderate", "Strong", "Very Strong", "Severe"]
    summary: str
    safety_steps: list[str] = Field(..., min_items=3, max_items=3)


# ---------------------------------------------------------------------------
# State / Infrastructure
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_json(payload)
                except Exception:
                    stale.append(conn)
            for conn in stale:
                self._connections.discard(conn)


class AppState:
    def __init__(self) -> None:
        self.usgs_catalog: pd.DataFrame = pd.DataFrame(
            columns=["id", "time", "latitude", "longitude", "depth", "mag", "place"]
        )
        self.catalog_lock = asyncio.Lock()

        self.live_events: Deque[dict[str, Any]] = deque(maxlen=5000)
        self.sensor_events: Deque[dict[str, Any]] = deque(maxlen=20000)

        self.connections = ConnectionManager()
        self.model: torch.jit.ScriptModule | None = None
        self.model_source: Literal["torchscript", "heuristic_stub"] = "heuristic_stub"
        self.damage_detector: Any | None = None
        self.damage_detector_source: str = "yolo_stub"
        self.image_enhancer: Any | None = None
        self.image_enhancer_source: str = "esrgan_lazy"


state = AppState()


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_vec(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(lats)
    lon2 = np.radians(lons)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return r * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def ensure_catalog_types(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    required = ["id", "time", "latitude", "longitude", "depth", "mag", "place"]
    for col in required:
        if col not in out.columns:
            out[col] = np.nan

    out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    out["depth"] = pd.to_numeric(out["depth"], errors="coerce")
    out["mag"] = pd.to_numeric(out["mag"], errors="coerce")
    out["place"] = out["place"].fillna("unknown")
    out = out.dropna(subset=["time", "latitude", "longitude", "depth", "mag"])  # critical fields

    out = out.drop_duplicates(subset=["id"], keep="first")
    out = out.sort_values("time").reset_index(drop=True)
    return out


def load_usgs_catalog_from_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        logger.warning("USGS cache not found at %s. Starting with empty catalog.", path)
        return ensure_catalog_types(pd.DataFrame())

    try:
        df = pd.read_csv(path)
        return ensure_catalog_types(df)
    except Exception as exc:
        logger.exception("Failed to read USGS cache CSV: %s", exc)
        return ensure_catalog_types(pd.DataFrame())


def save_usgs_catalog_to_cache(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_csv(path, index=False)
    except Exception as exc:
        logger.exception("Failed to persist USGS cache CSV: %s", exc)


def historical_depth_autofill(
    df: pd.DataFrame, latitude: float, longitude: float, k_neighbors: int = 25
) -> tuple[float, int]:
    if df.empty:
        return 10.0, 0

    distances = haversine_vec(
        latitude,
        longitude,
        df["latitude"].to_numpy(dtype=float),
        df["longitude"].to_numpy(dtype=float),
    )
    nearest_idx = np.argsort(distances)[: min(k_neighbors, len(df))]
    nearest_depths = df.iloc[nearest_idx]["depth"].to_numpy(dtype=float)

    if nearest_depths.size == 0:
        return 10.0, 0

    return float(np.nanmean(nearest_depths)), int(nearest_depths.size)


def pga_joyner_boore_percent_g(
    magnitude: float, focal_depth_km: float, epicentral_distance_km: float
) -> float:
    """
    Simplified Joyner-Boore-style attenuation approximation.
    Returns PGA in percent g.

    log10(PGA_g) = -1.02 + 0.249*M - log10(R) - 0.00255*R
    where R = sqrt(distance^2 + depth^2 + 7.3^2)
    """
    r = math.sqrt(epicentral_distance_km**2 + focal_depth_km**2 + 7.3**2)
    log10_pga_g = -1.02 + (0.249 * magnitude) - math.log10(max(r, 1e-3)) - (0.00255 * r)
    pga_g = 10 ** log10_pga_g
    pga_percent_g = max(0.0, pga_g * 100.0)
    return float(pga_percent_g)


def design_basis_worst_case(
    df: pd.DataFrame, latitude: float, longitude: float, search_radius_km: float
) -> WorstCaseResponse:
    if df.empty:
        fallback_mag = 6.5
        fallback_depth = 12.0
        fallback_distance = 5.0
        return WorstCaseResponse(
            latitude=latitude,
            longitude=longitude,
            search_radius_km=search_radius_km,
            design_basis_magnitude=fallback_mag,
            autofilled_depth_km=fallback_depth,
            assumed_epicentral_distance_km=fallback_distance,
            pga_percent_g=pga_joyner_boore_percent_g(
                fallback_mag, fallback_depth, fallback_distance
            ),
            historical_events_considered=0,
        )

    distances = haversine_vec(
        latitude,
        longitude,
        df["latitude"].to_numpy(dtype=float),
        df["longitude"].to_numpy(dtype=float),
    )
    local_df = df.loc[distances <= search_radius_km]

    if local_df.empty:
        local_df = df

    mmax = float(local_df["mag"].max())
    depth_km, samples = historical_depth_autofill(local_df, latitude, longitude, k_neighbors=25)
    assumed_distance = 5.0
    pga = pga_joyner_boore_percent_g(mmax, depth_km, assumed_distance)

    return WorstCaseResponse(
        latitude=latitude,
        longitude=longitude,
        search_radius_km=search_radius_km,
        design_basis_magnitude=mmax,
        autofilled_depth_km=depth_km,
        assumed_epicentral_distance_km=assumed_distance,
        pga_percent_g=pga,
        historical_events_considered=int(len(local_df)),
    )


def normalize_mainshock(ms: MainshockFeatures) -> torch.Tensor:
    feat = np.asarray(
        [
            ms.magnitude,
            ms.depth_km,
            ms.latitude,
            ms.longitude,
            float(ms.hour_utc),
            float(ms.day_of_year),
        ],
        dtype=np.float32,
    )
    return (feat - FEATURE_MEAN) / (FEATURE_STD + 1e-6)


def heuristic_aftershock_forecast(
    mainshock: MainshockFeatures, history_48h: list[int]
) -> list[float]:
    hist = np.asarray(history_48h, dtype=np.float32)
    hist_rate = float(np.clip(np.mean(hist), 0.0, 50.0))
    magnitude_factor = max(0.0, mainshock.magnitude - 4.0) / 4.0
    baseline = min(0.9, 0.05 + 0.55 * magnitude_factor + 0.02 * min(hist_rate, 10.0))

    probs: list[float] = []
    for h in range(24):
        decay = math.exp(-h / 9.0)
        p = baseline * decay
        probs.append(float(np.clip(p, 0.001, 0.99)))
    return probs


def load_aftershock_model(path: Path) -> tuple[torch.jit.ScriptModule | None, Literal["torchscript", "heuristic_stub"]]:
    if torch is None:
        logger.warning("Torch import unavailable. Falling back to heuristic.")
        return None, "heuristic_stub"
    if not path.exists():
        logger.warning("TorchScript model not found at %s. Falling back to heuristic.", path)
        return None, "heuristic_stub"
    try:
        model = torch.jit.load(str(path), map_location="cpu")
        model.eval()
        logger.info("Loaded aftershock TorchScript model from %s", path)
        return model, "torchscript"
    except Exception as exc:
        logger.exception("Failed to load TorchScript model: %s", exc)
        return None, "heuristic_stub"


def nearest_fault_distance(latitude: float, longitude: float) -> FaultDistanceResponse:
    """
    Mockable tectonic fault proximity service.
    Swap with OSM/GEM polyline distance for production GIS.
    """
    min_fault = "unknown"
    min_dist = float("inf")

    for fp in DEFAULT_FAULT_POINTS:
        d = haversine_km(latitude, longitude, float(fp["lat"]), float(fp["lon"]))
        if d < min_dist:
            min_dist = d
            min_fault = str(fp["name"])

    return FaultDistanceResponse(nearest_fault_name=min_fault, distance_km=float(min_dist))


def classify_threat_level(pga_percent_g: float) -> Literal[
    "Light", "Moderate", "Strong", "Very Strong", "Severe"
]:
    for threshold, label in MMI_THREAT_MAP:
        if pga_percent_g < threshold:
            return label  # type: ignore[return-value]
    return "Severe"


def rigid_llm_prompt(payload: LaymanSummaryRequest) -> str:
    return (
        "You are an emergency risk translator. "
        "Return ONLY valid JSON with EXACT keys: threat_level, summary, safety_steps. "
        "threat_level must be one of: Light, Moderate, Strong, Very Strong, Severe. "
        "summary must be exactly 2 sentences in plain English. "
        "safety_steps must be an array of exactly 3 short, actionable strings. "
        "No markdown, no extra keys, no commentary. "
        f"Input payload: {payload.model_dump_json()}"
    )


def llm_layman_translation_stub(payload: LaymanSummaryRequest) -> LaymanSummaryResponse:
    """
    Stub for LLM integration (OpenAI gpt-4o-mini or equivalent).
    This deterministic fallback follows the same rigid schema for UI safety.
    """
    _prompt = rigid_llm_prompt(payload)
    threat = classify_threat_level(payload.pga_percent_g)

    if payload.aftershock_probability_24h >= 0.6:
        aftershock_phrase = "High aftershock likelihood is expected over the next 24 hours"
    elif payload.aftershock_probability_24h >= 0.3:
        aftershock_phrase = "A moderate chance of aftershocks remains over the next 24 hours"
    else:
        aftershock_phrase = "Aftershock risk is currently lower but still possible over the next 24 hours"

    summary = (
        f"This earthquake can cause {threat.lower()} shaking near the affected area, especially close to the epicenter. "
        f"{aftershock_phrase}, so stay alert and follow official updates."
    )

    steps = [
        "Drop, Cover, and Hold On during any shaking.",
        "Check for gas leaks, electrical damage, and unstable structures before re-entering buildings.",
        "Keep phone lines clear for emergencies and monitor official local alerts.",
    ]

    # Keep prompt referenced for easy swap-in when integrating an actual LLM API.
    logger.debug("Layman translation prompt prepared: %s", _prompt)

    return LaymanSummaryResponse(
        threat_level=threat,
        summary=summary,
        safety_steps=steps,
    )


def synthetic_shakemap_polygons(event: dict[str, Any]) -> list[IntensityPolygon]:
    mag = float(event.get("mag", 5.0))
    lat = float(event.get("latitude", 0.0))
    lon = float(event.get("longitude", 0.0))

    # Conceptual concentric intensity zones, parameterized by magnitude
    zones = [
        ("Severe", (80.0, 140.0), 30.0 * mag),
        ("Strong", (40.0, 80.0), 120.0 * mag),
        ("Moderate", (15.0, 40.0), 350.0 * mag),
        ("Light", (5.0, 15.0), 800.0 * mag),
    ]
    out: list[IntensityPolygon] = []
    for label, pga_range, area in zones:
        jitter_lat = lat + random.uniform(-0.08, 0.08)
        jitter_lon = lon + random.uniform(-0.08, 0.08)
        out.append(
            IntensityPolygon(
                intensity_label=label,
                pga_range_percent_g=pga_range,
                area_km2=max(area, 1.0),
                centroid_lat=jitter_lat,
                centroid_lon=jitter_lon,
            )
        )
    return out


def population_density_stub(latitude: float, longitude: float) -> float:
    """
    Mock population density (persons/km^2), swappable with raster lookup.
    """
    coastal_bonus = 3000.0 if abs(longitude) < 30 or abs(longitude) > 100 else 800.0
    lat_factor = max(100.0, 3000.0 - abs(latitude) * 25.0)
    return float(lat_factor + coastal_bonus)


def estimate_impact(event_id: str, polygons: list[IntensityPolygon]) -> ImpactAssessmentResponse:
    severity_weight = {
        "Light": 0.0003,
        "Moderate": 0.0015,
        "Strong": 0.004,
        "Severe": 0.01,
    }

    exposed_pop = 0.0
    casualty_low = 0.0
    casualty_high = 0.0

    for p in polygons:
        lat = float(p.centroid_lat) if np.isfinite(float(p.centroid_lat)) else 0.0
        lon = float(p.centroid_lon) if np.isfinite(float(p.centroid_lon)) else 0.0
        area_km2 = float(p.area_km2) if np.isfinite(float(p.area_km2)) else 0.0
        density = population_density_stub(lat, lon)
        zone_pop = density * area_km2
        exposed_pop += zone_pop

        w = severity_weight.get(p.intensity_label, 0.001)
        casualty_low += zone_pop * w
        casualty_high += zone_pop * w * 2.4

    safe_exposed = 0 if not np.isfinite(exposed_pop) else int(max(exposed_pop, 0.0))
    safe_low = 0 if not np.isfinite(casualty_low) else int(max(casualty_low, 0.0))
    safe_high = 0 if not np.isfinite(casualty_high) else int(max(casualty_high, 0.0))

    return ImpactAssessmentResponse(
        event_id=event_id,
        exposed_population_estimate=safe_exposed,
        casualty_estimate_low=safe_low,
        casualty_estimate_high=safe_high,
        methodology=(
            "Synthetic ShakeMap intensity zones intersected with mock population density. "
            "Replace with rasterized census/population grids for operational use."
        ),
    )


def parse_image_bytes(upload: UploadFile, payload: bytes) -> np.ndarray:
    try:
        from PIL import Image

        pil = Image.open(io.BytesIO(payload)).convert("RGB")
        return np.array(pil)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file {upload.filename}: {exc}")


def downscale_for_realtime(img: np.ndarray, max_side: int = MAX_DAMAGE_IMAGE_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    side = max(h, w)
    if side <= max_side:
        return img
    scale = max_side / float(side)
    nh, nw = int(h * scale), int(w * scale)
    from PIL import Image
    pil = Image.fromarray(img)
    resized = pil.resize((max(1, nw), max(1, nh)), Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.uint8)


def image_to_jpeg_b64(img: np.ndarray, quality: int = 80) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def draw_damage_overlay(img: np.ndarray, boxes: list[DamageBox]) -> np.ndarray:
    from PIL import Image, ImageDraw
    out = Image.fromarray(img.copy())
    draw = ImageDraw.Draw(out)
    color_map = {
        0: (74, 210, 149),
        1: (246, 211, 91),
        2: (255, 139, 61),
        3: (239, 68, 68),
    }
    for b in boxes:
        c = color_map.get(b.damage_class, (255, 255, 255))
        draw.rectangle((b.x1, b.y1, b.x2, b.y2), outline=c, width=3)
    return np.asarray(out, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Video Frame Extraction & Processing
# ---------------------------------------------------------------------------

def extract_frames_from_video(
    video_source: str | bytes,
    sample_interval_sec: float = 1.0,
    max_frames: int = 100,
    is_file: bool = True,
) -> tuple[list[np.ndarray], tuple[int, int]]:
    """
    Extract frames from a video source at approximately 1 frame per second.
    
    Args:
        video_source: File path (str) or bytes buffer
        sample_interval_sec: Target interval between frames in seconds (default 1.0)
        max_frames: Maximum number of frames to extract (default 100)
        is_file: True if video_source is a file path, False if bytes
    
    Returns:
        Tuple of (frames list, frame dimensions as (height, width))
    
    Raises:
        HTTPException: If video cannot be read or is invalid
    """
    try:
        import cv2
    except ImportError:
        raise HTTPException(status_code=500, detail="OpenCV not installed on backend")
    
    cap = None
    try:
        if is_file:
            cap = cv2.VideoCapture(video_source)
        else:
            # For bytes, write to temp file first
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(video_source)
                tmp_path = tmp.name
            cap = cv2.VideoCapture(tmp_path)
        
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Failed to open video file")
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        
        if frame_height <= 0 or frame_width <= 0:
            raise HTTPException(status_code=400, detail="Invalid video dimensions")
        
        frames: list[np.ndarray] = []
        frame_count = 0
        sample_frame_count = max(1, int(sample_interval_sec * fps))
        target_frame_idx = 0
        
        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Sample at specified interval
            if frame_count == target_frame_idx:
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                target_frame_idx += sample_frame_count
            
            frame_count += 1
        
        if not frames:
            raise HTTPException(status_code=400, detail="No frames could be extracted from video")
        
        return frames, (frame_height, frame_width)
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Video frame extraction failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Video processing error: {exc}")
    finally:
        if cap is not None:
            cap.release()


def process_video_frames(
    frames: list[np.ndarray],
    demo_fast: bool = True,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[list[DamageBox], dict[str, int], int, np.ndarray]:
    """
    Process a list of video frames through the damage assessment pipeline.
    Returns the worst-case damage assessment across all frames.
    
    Args:
        frames: List of RGB numpy arrays
        demo_fast: Whether to use fast inference mode
        latitude: Optional latitude for event context
        longitude: Optional longitude for event context
    
    Returns:
        Tuple of (damage_boxes, aggregated_counts, max_damage_class, representative_frame)
    """
    if not frames:
        raise ValueError("No frames provided")
    
    all_boxes: list[DamageBox] = []
    max_damage_class_overall = 0
    representative_frame_idx = 0
    max_damage_count = 0
    
    for frame_idx, frame in enumerate(frames):
        logger.debug(f"Processing video frame {frame_idx + 1}/{len(frames)}")
        
        # Prepare frame
        img = downscale_for_realtime(frame)
        
        # Enhancement
        if (not demo_fast) and state.image_enhancer is None:
            enhancer, enhancer_source = load_image_enhancer()
            state.image_enhancer = enhancer
            state.image_enhancer_source = enhancer_source
        
        if (not demo_fast) and state.image_enhancer is not None:
            try:
                enhanced = esrgan_upscale(state.image_enhancer, img)
            except Exception as exc:
                logger.exception("ESRGAN enhancement failed on frame %d, using stub: %s", frame_idx, exc)
                enhanced = esrgan_upscale_stub(img)
        else:
            enhanced = esrgan_upscale_stub(img)
        
        # Damage detection
        if state.damage_detector is not None:
            try:
                boxes = yolo_damage_inference_fast(state.damage_detector, enhanced) if demo_fast else yolo_damage_inference(state.damage_detector, enhanced)
            except Exception as exc:
                logger.exception("YOLO inference failed on frame %d, using stub: %s", frame_idx, exc)
                boxes = yolo_damage_inference_stub(enhanced)
        else:
            boxes = yolo_damage_inference_stub(enhanced)
        
        all_boxes.extend(boxes)
        
        # Track frame with worst damage
        frame_damage_count = len([b for b in boxes if b.damage_class >= 2])
        max_damage_in_frame = max([b.damage_class for b in boxes], default=0)
        if frame_damage_count > max_damage_count or (frame_damage_count == max_damage_count and max_damage_in_frame > 0):
            max_damage_count = frame_damage_count
            representative_frame_idx = frame_idx
        
        max_class = max([b.damage_class for b in boxes], default=0)
        if max_class > max_damage_class_overall:
            max_damage_class_overall = max_class
    
    # Aggregate counts across all frames
    counts = {"no-damage": 0, "minor-damage": 0, "major-damage": 0, "destroyed": 0}
    for b in all_boxes:
        counts[b.damage_label] += 1
    
    return all_boxes, counts, max_damage_class_overall, frames[representative_frame_idx]


def esrgan_upscale_stub(img: np.ndarray) -> np.ndarray:
    """
    Stub for ESRGAN super-resolution stage.
    Swap with RealESRGANer.enhance(...) when weights are available.
    """
    # Keep input shape for endpoint speed; in production this can upscale x4 then resize for detector.
    return img


def resolve_esrgan_weights_path() -> Path | None:
    if ESRGAN_WEIGHTS_PATH_ENV:
        env_path = Path(ESRGAN_WEIGHTS_PATH_ENV)
        if env_path.exists():
            return env_path

    candidate_paths = [
        Path("./terrawatch/RealESRGAN_x4plus.pth"),
        Path("./RealESRGAN_x4plus.pth"),
        MODEL_ROOT / "RealESRGAN_x4plus.pth",
    ]
    for path in candidate_paths:
        if path.exists():
            return path
    return None


def load_image_enhancer() -> tuple[Any | None, str]:
    weights_path = resolve_esrgan_weights_path()
    if weights_path is None:
        logger.warning("No Real-ESRGAN weights found. Using ESRGAN stub.")
        return None, "esrgan_stub"

    if torch is None:
        logger.warning("Torch unavailable; cannot load Real-ESRGAN. Using stub.")
        return None, "esrgan_stub"

    try:
        # basicsr in some releases imports torchvision.transforms.functional_tensor,
        # which is missing in newer torchvision builds. Provide a compatibility shim.
        import sys
        import types
        import torchvision.transforms.functional as F  # type: ignore[import-untyped]
        if "torchvision.transforms.functional_tensor" not in sys.modules:
            functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
            functional_tensor.rgb_to_grayscale = F.rgb_to_grayscale
            sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor

        from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore[import-untyped]
        from realesrgan import RealESRGANer  # type: ignore[import-untyped]

        rrdb = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=ESRGAN_SCALE,
        )
        enhancer = RealESRGANer(
            scale=ESRGAN_SCALE,
            model_path=str(weights_path),
            model=rrdb,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=False,
            gpu_id=None,
        )
        logger.info("Loaded Real-ESRGAN enhancer from %s", weights_path)
        return enhancer, f"esrgan:{weights_path}"
    except Exception as exc:
        logger.exception("Failed to load Real-ESRGAN from %s: %s", weights_path, exc)
        return None, "esrgan_stub"


def esrgan_upscale(enhancer: Any, img: np.ndarray) -> np.ndarray:
    # RealESRGANer expects BGR; convert back to RGB for API pipeline.
    bgr = img[:, :, ::-1]
    output_bgr, _ = enhancer.enhance(bgr, outscale=ESRGAN_OUTSCALE)
    output_rgb = output_bgr[:, :, ::-1]
    return np.asarray(output_rgb, dtype=np.uint8)


def _latest_detect_weights(runs_dir: Path) -> Path | None:
    candidates = [p for p in runs_dir.glob("*/weights/best.pt") if p.exists()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def resolve_yolo_weights_path() -> Path | None:
    if YOLO_WEIGHTS_PATH_ENV:
        env_path = Path(YOLO_WEIGHTS_PATH_ENV)
        if env_path.exists():
            return env_path

    candidate_paths = [
        MODEL_ROOT / "enhanced_yolov8n" / "weights" / "best.pt",
        MODEL_ROOT / "baseline_yolov8n" / "weights" / "best.pt",
        Path("./terrawatch/yolov8n.pt"),
        Path("./yolov8n.pt"),
    ]
    for path in candidate_paths:
        if path.exists():
            return path

    return _latest_detect_weights(RUNS_DETECT_DIR)


def canonical_damage_label(raw: str) -> tuple[int, str]:
    key = raw.strip().lower().replace("_", "-")
    aliases: dict[str, tuple[int, str]] = {
        "no-damage": (0, "no-damage"),
        "no damage": (0, "no-damage"),
        "minor-damage": (1, "minor-damage"),
        "minor damage": (1, "minor-damage"),
        "major-damage": (2, "major-damage"),
        "major damage": (2, "major-damage"),
        "destroyed": (3, "destroyed"),
        "collapse": (3, "destroyed"),
        "collapsed": (3, "destroyed"),
    }
    return aliases.get(key, (0, "no-damage"))


def load_damage_detector() -> tuple[Any | None, str]:
    weights_path = resolve_yolo_weights_path()
    if weights_path is None:
        logger.warning("No YOLO weights found. Using damage stub inference.")
        return None, "yolo_stub"

    try:
        from ultralytics import YOLO  # type: ignore[import-untyped]

        model = YOLO(str(weights_path))
        logger.info("Loaded YOLO detector weights from %s", weights_path)
        return model, f"yolo:{weights_path}"
    except Exception as exc:
        logger.exception("Failed to load YOLO detector from %s: %s", weights_path, exc)
        return None, "yolo_stub"


def yolo_damage_inference(model: Any, img: np.ndarray) -> list[DamageBox]:
    results = model.predict(
        source=img,
        verbose=False,
        conf=YOLO_CONF_THRESHOLD,
        iou=YOLO_IOU_THRESHOLD,
        imgsz=YOLO_IMAGE_SIZE,
        device="cpu",
    )
    if not results:
        return []

    names: dict[int, str] = results[0].names or {}
    boxes: list[DamageBox] = []
    for b in results[0].boxes:
        cls_idx = int(b.cls.item())
        conf = float(b.conf.item())
        x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
        raw_label = str(names.get(cls_idx, str(cls_idx)))
        damage_class, damage_label = canonical_damage_label(raw_label)
        boxes.append(
            DamageBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=float(np.clip(conf, 0.0, 1.0)),
                damage_class=damage_class,
                damage_label=damage_label,
            )
        )
    return boxes


def yolo_damage_inference_fast(model: Any, img: np.ndarray) -> list[DamageBox]:
    results = model.predict(
        source=img,
        verbose=False,
        conf=max(0.2, YOLO_CONF_THRESHOLD),
        iou=YOLO_IOU_THRESHOLD,
        imgsz=YOLO_FAST_IMAGE_SIZE,
        device="cpu",
    )
    if (not results) or (results and len(results[0].boxes) == 0):
        # Demo fallback: relax confidence once to avoid empty overlays on difficult imagery.
        results = model.predict(
            source=img,
            verbose=False,
            conf=0.05,
            iou=YOLO_IOU_THRESHOLD,
            imgsz=max(YOLO_FAST_IMAGE_SIZE, 640),
            device="cpu",
        )
    if not results:
        return []

    names: dict[int, str] = results[0].names or {}
    boxes: list[DamageBox] = []
    for b in results[0].boxes:
        cls_idx = int(b.cls.item())
        conf = float(b.conf.item())
        x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
        raw_label = str(names.get(cls_idx, str(cls_idx)))
        damage_class, damage_label = canonical_damage_label(raw_label)
        boxes.append(
            DamageBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=float(np.clip(conf, 0.0, 1.0)),
                damage_class=damage_class,
                damage_label=damage_label,
            )
        )
    return boxes


def yolo_damage_inference_stub(img: np.ndarray) -> list[DamageBox]:
    """
    Stub detector/classifier for building damage levels (0-3).
    Replace with Ultralytics YOLOv8 inference results parsing.
    """
    h, w, _ = img.shape
    random.seed(int(img.mean()) + h + w)

    n = min(12, max(2, int((img.std() / 255.0) * 15)))
    labels = ["no-damage", "minor-damage", "major-damage", "destroyed"]

    boxes: list[DamageBox] = []
    for _ in range(n):
        bw = random.randint(max(12, w // 20), max(25, w // 6))
        bh = random.randint(max(12, h // 20), max(25, h // 6))
        x1 = random.randint(0, max(1, w - bw - 1))
        y1 = random.randint(0, max(1, h - bh - 1))
        x2 = x1 + bw
        y2 = y1 + bh
        damage_class = random.choices([0, 1, 2, 3], weights=[0.35, 0.30, 0.22, 0.13])[0]
        conf = round(random.uniform(0.4, 0.95), 3)
        boxes.append(
            DamageBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=conf,
                damage_class=damage_class,
                damage_label=labels[damage_class],
            )
        )
    return boxes


def nearest_event_context(
    df: pd.DataFrame, latitude: float | None, longitude: float | None
) -> tuple[str | None, float | None, float | None]:
    if latitude is None or longitude is None or df.empty:
        return None, None, None

    distances = haversine_vec(
        latitude,
        longitude,
        df["latitude"].to_numpy(dtype=float),
        df["longitude"].to_numpy(dtype=float),
    )
    idx = int(np.argmin(distances))
    row = df.iloc[idx]

    if float(distances[idx]) > 300.0:
        return None, None, None

    return str(row.get("id")), float(row.get("mag")), float(row.get("depth"))


def compute_resultant_g(x: float, y: float, z: float) -> float:
    return float(math.sqrt(x * x + y * y + z * z))


def sensor_trigger_level(resultant_g: float) -> Literal["normal", "elevated", "critical"]:
    if resultant_g >= 1.2:
        return "critical"
    if resultant_g >= 0.6:
        return "elevated"
    return "normal"


# ---------------------------------------------------------------------------
# USGS / ShakeMap I/O
# ---------------------------------------------------------------------------

async def fetch_usgs_events_last_48h() -> list[dict[str, Any]]:
    end = datetime.now(tz=UTC)
    start = end - timedelta(hours=LIVE_CATALOG_HOURS)

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
        "orderby": "time",
        "limit": 20000,
    }

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    out: list[dict[str, Any]] = []
    for feat in payload.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [None, None, None])
        event = {
            "id": feat.get("id"),
            "time": datetime.fromtimestamp(props.get("time", 0) / 1000, tz=UTC),
            "latitude": coords[1],
            "longitude": coords[0],
            "depth": coords[2],
            "mag": props.get("mag"),
            "place": props.get("place", "unknown"),
            "detail_url": props.get("detail"),
        }
        if event["id"] and event["latitude"] is not None and event["mag"] is not None:
            out.append(event)
    return out


async def fetch_shakemap_from_usgs_detail(detail_url: str) -> list[IntensityPolygon] | None:
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(detail_url)
        resp.raise_for_status()
        detail = resp.json()

    products = detail.get("properties", {}).get("products", {})
    shakemaps = products.get("shakemap", [])
    if not shakemaps:
        return None

    # Highly simplified extraction. Real integration should parse stationlist/grid.xml/contours.
    out: list[IntensityPolygon] = []
    for sm in shakemaps[:1]:
        props = sm.get("properties", {})
        maxmmi = float(props.get("maxmmi", 6.0))
        maxpga = float(props.get("maxpga", 30.0))

        out.append(
            IntensityPolygon(
                intensity_label="Strong" if maxmmi >= 6 else "Moderate",
                pga_range_percent_g=(max(5.0, maxpga * 0.4), maxpga),
                area_km2=400.0 + maxmmi * 150.0,
                centroid_lat=0.0,
                centroid_lon=0.0,
            )
        )
    return out


async def poll_usgs_loop() -> None:
    logger.info("USGS polling loop started (interval=%ss)", USGS_POLL_SECONDS)
    seen_ids: set[str] = set()

    while True:
        try:
            events = await fetch_usgs_events_last_48h()
            new_events: list[dict[str, Any]] = []

            async with state.catalog_lock:
                current = state.usgs_catalog
                new_df = pd.DataFrame(events)
                merged = pd.concat([current, new_df], ignore_index=True)
                merged = ensure_catalog_types(merged)
                state.usgs_catalog = merged
                save_usgs_catalog_to_cache(state.usgs_catalog, USGS_CACHE_CSV)

            for e in events:
                eid = str(e.get("id"))
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    new_events.append(e)
                    state.live_events.append(e)

            for e in new_events:
                await state.connections.broadcast({"type": "usgs_event", "payload": json_safe(e)})

                if float(e.get("mag", 0.0)) >= 5.0:
                    polygons = await trigger_shakemap_and_impact(e)
                    await state.connections.broadcast(
                        {
                            "type": "impact_assessment",
                            "payload": {
                                "event_id": e.get("id"),
                                "polygons": [p.model_dump() for p in polygons],
                            },
                        }
                    )

        except Exception as exc:
            logger.exception("USGS polling loop error: %s", exc)

        await asyncio.sleep(USGS_POLL_SECONDS)


def json_safe(event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in event.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


async def trigger_shakemap_and_impact(event: dict[str, Any]) -> list[IntensityPolygon]:
    event_id = str(event.get("id"))
    detail_url = str(event.get("detail_url") or "")

    polygons: list[IntensityPolygon] | None = None
    source: Literal["usgs_shakemap", "synthetic_stub"] = "synthetic_stub"

    if detail_url:
        try:
            fetched = await fetch_shakemap_from_usgs_detail(detail_url)
            if fetched:
                polygons = fetched
                source = "usgs_shakemap"
        except Exception as exc:
            logger.warning("ShakeMap fetch failed for %s: %s", event_id, exc)

    if polygons is None:
        polygons = synthetic_shakemap_polygons(event)

    impact = estimate_impact(event_id=event_id, polygons=polygons)
    await state.connections.broadcast(
        {
            "type": "shakemap",
            "payload": {
                "event_id": event_id,
                "source": source,
                "polygons": [p.model_dump() for p in polygons],
                "impact": impact.model_dump(),
            },
        }
    )
    return polygons


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TerraWatch Backend",
    version="1.0.0",
    description="FastAPI backend for multi-modal disaster prediction and response",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Initializing TerraWatch backend...")

    state.usgs_catalog = load_usgs_catalog_from_cache(USGS_CACHE_CSV)
    state.model, state.model_source = load_aftershock_model(AFTERSHOCK_MODEL_PATH)
    # Load ESRGAN lazily during non-fast damage refinement to keep startup responsive.
    state.image_enhancer = None
    state.image_enhancer_source = "esrgan_lazy"
    state.damage_detector, state.damage_detector_source = load_damage_detector()

    asyncio.create_task(poll_usgs_loop())
    logger.info("Startup complete. Catalog rows=%s", len(state.usgs_catalog))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "catalog_rows": int(len(state.usgs_catalog)),
        "aftershock_model_source": state.model_source,
        "enhancer_model_source": state.image_enhancer_source,
        "damage_model_source": state.damage_detector_source,
    }


# ---------------------------------------------------------------------------
# 1) Core Geophysics & Hazard Engine
# ---------------------------------------------------------------------------

@app.post("/api/hazard/depth", response_model=DepthAutofillResponse)
async def api_depth_autofill(req: DepthAutofillRequest) -> DepthAutofillResponse:
    async with state.catalog_lock:
        depth, samples = historical_depth_autofill(
            state.usgs_catalog, req.latitude, req.longitude, req.k_neighbors
        )

    return DepthAutofillResponse(
        latitude=req.latitude,
        longitude=req.longitude,
        average_depth_km=depth,
        samples_used=samples,
    )


@app.post("/api/hazard/pga", response_model=PGACalculationResponse)
async def api_pga(req: PGACalculationRequest) -> PGACalculationResponse:
    pga = pga_joyner_boore_percent_g(
        req.magnitude,
        req.focal_depth_km,
        req.epicentral_distance_km,
    )
    return PGACalculationResponse(
        pga_percent_g=pga,
        model="simplified_joyner_boore",
    )


@app.post("/api/hazard/worst_case", response_model=WorstCaseResponse)
async def api_worst_case(req: WorstCaseRequest) -> WorstCaseResponse:
    async with state.catalog_lock:
        return design_basis_worst_case(
            state.usgs_catalog,
            req.latitude,
            req.longitude,
            req.search_radius_km,
        )


# ---------------------------------------------------------------------------
# 2) AI Forecaster (PyTorch Transformer)
# ---------------------------------------------------------------------------

@app.post("/api/aftershock", response_model=AftershockResponse)
async def api_aftershock(req: AftershockRequest) -> AftershockResponse:
    probs: list[float]
    source = state.model_source

    if state.model is not None and torch is not None:
        try:
            ms_norm = torch.as_tensor(normalize_mainshock(req.mainshock), dtype=torch.float32).view(1, 6)
            hist = torch.tensor(req.historical_seismicity_48h, dtype=torch.float32).view(1, 48)
            with torch.no_grad():
                pred = state.model(ms_norm, hist)
                probs_np = pred.detach().cpu().numpy().reshape(-1)
                probs = [float(np.clip(x, 0.0, 1.0)) for x in probs_np[:24]]
                if len(probs) != 24:
                    raise RuntimeError("Unexpected model output shape")
        except Exception as exc:
            logger.exception("Model inference failed, switching to heuristic: %s", exc)
            probs = heuristic_aftershock_forecast(req.mainshock, req.historical_seismicity_48h)
            source = "heuristic_stub"
    else:
        probs = heuristic_aftershock_forecast(req.mainshock, req.historical_seismicity_48h)
        source = "heuristic_stub"

    payload = AftershockResponse(
        forecast_horizon_hours=24,
        probabilities_m4_plus=probs,
        generated_at_utc=datetime.now(tz=UTC),
        model_source=source,
    )

    await state.connections.broadcast({"type": "aftershock_forecast", "payload": payload.model_dump(mode="json")})
    return payload


# ---------------------------------------------------------------------------
# 3) Live Data Pipelines & Geospatial APIs
# ---------------------------------------------------------------------------

@app.get("/api/live/events")
async def api_live_events(limit: int = 200) -> dict[str, Any]:
    if limit < 1 or limit > 5000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 5000")
    events = list(state.live_events)[-limit:]
    return {"count": len(events), "events": [json_safe(e) for e in events]}


@app.post("/api/fault_distance", response_model=FaultDistanceResponse)
async def api_fault_distance(req: FaultDistanceRequest) -> FaultDistanceResponse:
    return nearest_fault_distance(req.latitude, req.longitude)


# ---------------------------------------------------------------------------
# 4) Zero-Hour Impact Assessment (ShakeMap Integration)
# ---------------------------------------------------------------------------

@app.post("/api/shakemap", response_model=ShakeMapResponse)
async def api_shakemap(req: ShakeMapFetchRequest) -> ShakeMapResponse:
    async with state.catalog_lock:
        df = state.usgs_catalog.copy()

    if df.empty:
        raise HTTPException(status_code=404, detail="No catalog loaded")

    row = df[df["id"] == req.event_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Event {req.event_id} not found")

    ev = {
        "id": req.event_id,
        "mag": float(row.iloc[0]["mag"]),
        "latitude": float(row.iloc[0]["latitude"]),
        "longitude": float(row.iloc[0]["longitude"]),
        "detail_url": None,
    }

    polys = synthetic_shakemap_polygons(ev)
    return ShakeMapResponse(event_id=req.event_id, polygons=polys, source="synthetic_stub")

@app.get("/api/shakemap/latest")
async def api_shakemap_latest() -> dict[str, Any]:
    events = state.live_events
    m5_events = [e for e in events if float(e.get("mag", 0.0)) >= 5.0]
    if not m5_events:
        return {"status": "no_recent_events"}
    
    latest = m5_events[-1]
    event_id = str(latest["id"])
    
    polys = synthetic_shakemap_polygons(latest)
    impact = estimate_impact(event_id=event_id, polygons=polys)
    
    return {
        "status": "success",
        "event": json_safe(latest),
        "impact": impact.model_dump()
    }

@app.get("/api/shakemap/{event_id}")
async def api_shakemap_grid(event_id: str) -> dict[str, Any]:
    async with state.catalog_lock:
        df = state.usgs_catalog.copy()
    row = df[df["id"] == event_id]
    if row.empty:
        # Check live events
        live_matches = [e for e in state.live_events if e["id"] == event_id]
        if live_matches:
            lat = float(live_matches[0]["latitude"])
            lon = float(live_matches[0]["longitude"])
            mag = float(live_matches[0]["mag"])
        else:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    else:
        lat = float(row.iloc[0]["latitude"])
        lon = float(row.iloc[0]["longitude"])
        mag = float(row.iloc[0]["mag"])

    # Generate synthetic GeoJSON grid representing shaking x WorldPop density
    features = []
    grid_size = 0.05 # roughly 5km
    radius = int(math.ceil(mag)) * 2
    
    for i in range(-radius, radius + 1):
        for j in range(-radius, radius + 1):
            clat = lat + i * grid_size
            clon = lon + j * grid_size
            
            # Simple distance-based intensity
            dist = math.sqrt(i*i + j*j)
            if dist > radius:
                continue
                
            intensity = max(0, mag - (dist * 0.5))
            if intensity < 3.0:
                continue
                
            # Synthetic worldpop data correlation
            pop_density = random.randint(10, 5000)
            affected = int((intensity ** 2) * pop_density * 0.1)
            
            # GeoJSON polygon for this cell
            poly = [
                [clon - grid_size/2, clat - grid_size/2],
                [clon + grid_size/2, clat - grid_size/2],
                [clon + grid_size/2, clat + grid_size/2],
                [clon - grid_size/2, clat + grid_size/2],
                [clon - grid_size/2, clat - grid_size/2]
            ]
            
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [poly]
                },
                "properties": {
                    "intensity": intensity,
                    "population_affected": affected
                }
            })
            
    return {
        "type": "FeatureCollection",
        "features": features
    }

@app.post("/api/impact/{event_id}", response_model=ImpactAssessmentResponse)
async def api_impact(event_id: str) -> ImpactAssessmentResponse:
    async with state.catalog_lock:
        df = state.usgs_catalog.copy()

    row = df[df["id"] == event_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    ev = {
        "id": event_id,
        "mag": float(row.iloc[0]["mag"]),
        "latitude": float(row.iloc[0]["latitude"]),
        "longitude": float(row.iloc[0]["longitude"]),
    }
    polys = synthetic_shakemap_polygons(ev)
    return estimate_impact(event_id=event_id, polygons=polys)


# ---------------------------------------------------------------------------
# 5) Multimodal Damage Assessment (Computer Vision)
# ---------------------------------------------------------------------------

@app.post("/api/damage", response_model=DamageResponse)
async def api_damage(
    image: UploadFile = File(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    fast_mode: bool | None = Form(default=None),
) -> DamageResponse:
    raw = await image.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    demo_fast = DAMAGE_DEMO_FAST_DEFAULT if fast_mode is None else bool(fast_mode)
    img = downscale_for_realtime(parse_image_bytes(image, raw))
    if (not demo_fast) and state.image_enhancer is None:
        enhancer, enhancer_source = load_image_enhancer()
        state.image_enhancer = enhancer
        state.image_enhancer_source = enhancer_source

    if (not demo_fast) and state.image_enhancer is not None:
        try:
            enhanced = esrgan_upscale(state.image_enhancer, img)
        except Exception as exc:
            logger.exception("ESRGAN enhancement failed, switching to stub: %s", exc)
            enhanced = esrgan_upscale_stub(img)
    else:
        enhanced = esrgan_upscale_stub(img)
    if state.damage_detector is not None:
        try:
            boxes = yolo_damage_inference_fast(state.damage_detector, enhanced) if demo_fast else yolo_damage_inference(state.damage_detector, enhanced)
        except Exception as exc:
            logger.exception("YOLO inference failed, switching to stub: %s", exc)
            boxes = yolo_damage_inference_stub(enhanced)
    else:
        boxes = yolo_damage_inference_stub(enhanced)

    counts = {"no-damage": 0, "minor-damage": 0, "major-damage": 0, "destroyed": 0}
    for b in boxes:
        counts[b.damage_label] += 1

    max_damage_class = max((b.damage_class for b in boxes), default=0)
    overlay_img = draw_damage_overlay(enhanced, boxes)

    async with state.catalog_lock:
        ev_id, mag, depth = nearest_event_context(state.usgs_catalog, latitude, longitude)

    resp = DamageResponse(
        image_id=str(uuid.uuid4()),
        image_width=int(enhanced.shape[1]),
        image_height=int(enhanced.shape[0]),
        damage_boxes=boxes,
        aggregated_counts=counts,
        max_damage_class=max_damage_class,
        causative_event_id=ev_id,
        causative_magnitude=mag,
        causative_depth_km=depth,
        enhanced_image_b64=image_to_jpeg_b64(enhanced),
        overlay_image_b64=image_to_jpeg_b64(overlay_img),
        notes=(
            f"fast_mode={demo_fast}; "
            f"Enhancer source={state.image_enhancer_source}; "
            f"damage detector source={state.damage_detector_source}."
        ),
    )

    await state.connections.broadcast(
        {
            "type": "damage_assessment",
            "payload": {
                "image_id": resp.image_id,
                "aggregated_counts": resp.aggregated_counts,
                "max_damage_class": resp.max_damage_class,
                "causative_event_id": resp.causative_event_id,
            },
        }
    )
    return resp


@app.post("/api/damage/video", response_model=VideoDamageResponse)
async def api_damage_video(
    video: UploadFile = File(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    fast_mode: bool | None = Form(default=None),
) -> VideoDamageResponse:
    """
    Process a video file for damage assessment.
    Extracts frames at ~1 fps, runs damage pipeline on each,
    and returns worst-case damage assessment.
    
    Supported formats: MP4, AVI, MOV
    """
    raw = await video.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    
    # Validate video MIME type
    content_type = video.content_type or ""
    valid_types = {"video/mp4", "video/x-msvideo", "video/quicktime", "video/avi"}
    if not any(vt in content_type.lower() for vt in valid_types):
        logger.warning("Video uploaded with content-type: %s", content_type)
    
    demo_fast = DAMAGE_DEMO_FAST_DEFAULT if fast_mode is None else bool(fast_mode)
    
    # Extract frames from video bytes
    frames, (frame_h, frame_w) = extract_frames_from_video(
        raw,
        sample_interval_sec=1.0,
        max_frames=100,
        is_file=False
    )
    
    logger.info("Extracted %d frames from video", len(frames))
    
    # Process all frames through damage pipeline
    all_boxes, counts, max_damage_class, representative_frame = process_video_frames(
        frames,
        demo_fast=demo_fast,
        latitude=latitude,
        longitude=longitude,
    )
    
    # Get event context from catalog
    async with state.catalog_lock:
        ev_id, mag, depth = nearest_event_context(state.usgs_catalog, latitude, longitude)
    
    # Prepare response images
    enhanced_rep = downscale_for_realtime(representative_frame)
    overlay_img = draw_damage_overlay(enhanced_rep, all_boxes)
    
    resp = VideoDamageResponse(
        video_id=str(uuid.uuid4()),
        frames_analyzed=len(frames),
        frame_dimensions=(frame_h, frame_w),
        damage_boxes=all_boxes,
        aggregated_counts=counts,
        max_damage_class=max_damage_class,
        causative_event_id=ev_id,
        causative_magnitude=mag,
        causative_depth_km=depth,
        representative_frame_b64=image_to_jpeg_b64(enhanced_rep),
        overlay_image_b64=image_to_jpeg_b64(overlay_img),
        notes=(
            f"fast_mode={demo_fast}; "
            f"frames_analyzed={len(frames)}; "
            f"Enhancer source={state.image_enhancer_source}; "
            f"damage detector source={state.damage_detector_source}."
        ),
    )
    
    await state.connections.broadcast(
        {
            "type": "video_damage_assessment",
            "payload": {
                "video_id": resp.video_id,
                "frames_analyzed": resp.frames_analyzed,
                "aggregated_counts": resp.aggregated_counts,
                "max_damage_class": resp.max_damage_class,
                "causative_event_id": resp.causative_event_id,
            },
        }
    )
    return resp


@app.post("/api/damage/stream", response_model=VideoDamageResponse)
async def api_damage_stream(
    stream_url: str = Form(..., min_length=10),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    fast_mode: bool | None = Form(default=None),
    frame_limit: int | None = Form(default=30),
) -> VideoDamageResponse:
    """
    Process a live RTSP/HTTP stream URL for damage assessment.
    Captures up to frame_limit frames at ~1 fps and runs damage pipeline.
    
    Supported stream types:
    - RTSP: rtsp://192.168.x.x/stream
    - HTTP MJPEG: http://192.168.x.x:8080/video.mjpeg
    """
    # Validate URL format
    if not (stream_url.startswith("rtsp://") or stream_url.startswith("http://") or stream_url.startswith("https://")):
        raise HTTPException(
            status_code=400,
            detail="Stream URL must start with rtsp://, http://, or https://"
        )
    
    demo_fast = DAMAGE_DEMO_FAST_DEFAULT if fast_mode is None else bool(fast_mode)
    max_frames = frame_limit or 30
    
    logger.info("Connecting to stream URL: %s", stream_url)
    
    # Extract frames from stream URL
    try:
        import cv2
        cap = cv2.VideoCapture(stream_url)
        
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Failed to connect to stream URL")
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        
        if frame_height <= 0 or frame_width <= 0:
            raise HTTPException(status_code=400, detail="Invalid stream dimensions")
        
        frames: list[np.ndarray] = []
        frame_count = 0
        sample_frame_count = max(1, int(1.0 * fps))  # 1 fps sampling
        target_frame_idx = 0
        
        logger.info("Stream resolution: %dx%d, FPS: %.1f", frame_width, frame_height, fps)
        
        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                logger.info("End of stream reached after %d frames", len(frames))
                break
            
            # Sample at specified interval
            if frame_count == target_frame_idx:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                target_frame_idx += sample_frame_count
                logger.debug("Captured frame %d from stream", len(frames))
            
            frame_count += 1
        
        cap.release()
        
        if not frames:
            raise HTTPException(status_code=400, detail="No frames captured from stream")
        
        logger.info("Captured %d frames from stream", len(frames))
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Stream capture failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Stream capture error: {exc}")
    
    # Process all frames through damage pipeline
    all_boxes, counts, max_damage_class, representative_frame = process_video_frames(
        frames,
        demo_fast=demo_fast,
        latitude=latitude,
        longitude=longitude,
    )
    
    # Get event context from catalog
    async with state.catalog_lock:
        ev_id, mag, depth = nearest_event_context(state.usgs_catalog, latitude, longitude)
    
    # Prepare response images
    enhanced_rep = downscale_for_realtime(representative_frame)
    overlay_img = draw_damage_overlay(enhanced_rep, all_boxes)
    
    resp = VideoDamageResponse(
        video_id=str(uuid.uuid4()),
        frames_analyzed=len(frames),
        frame_dimensions=(frame_height, frame_width),
        damage_boxes=all_boxes,
        aggregated_counts=counts,
        max_damage_class=max_damage_class,
        causative_event_id=ev_id,
        causative_magnitude=mag,
        causative_depth_km=depth,
        representative_frame_b64=image_to_jpeg_b64(enhanced_rep),
        overlay_image_b64=image_to_jpeg_b64(overlay_img),
        notes=(
            f"fast_mode={demo_fast}; "
            f"stream_url={stream_url}; "
            f"frames_analyzed={len(frames)}; "
            f"Enhancer source={state.image_enhancer_source}; "
            f"damage detector source={state.damage_detector_source}."
        ),
    )
    
    await state.connections.broadcast(
        {
            "type": "stream_damage_assessment",
            "payload": {
                "video_id": resp.video_id,
                "frames_analyzed": resp.frames_analyzed,
                "aggregated_counts": resp.aggregated_counts,
                "max_damage_class": resp.max_damage_class,
                "causative_event_id": resp.causative_event_id,
            },
        }
    )
    return resp


# ---------------------------------------------------------------------------
# 6) IoT, Crowdsourcing, & Real-Time Infrastructure
# ---------------------------------------------------------------------------

@app.post("/api/sensor", response_model=SensorAck)
async def api_sensor(reading: SensorReading) -> SensorAck:
    resultant = compute_resultant_g(reading.accel_x_g, reading.accel_y_g, reading.accel_z_g)
    trigger = sensor_trigger_level(resultant)

    event = {
        "sensor_id": reading.sensor_id,
        "timestamp_utc": reading.timestamp_utc.isoformat(),
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "battery_pct": reading.battery_pct,
        "acceleration_resultant_g": resultant,
        "trigger_level": trigger,
    }
    state.sensor_events.append(event)

    if trigger in {"elevated", "critical"}:
        await state.connections.broadcast({"type": "sensor_trigger", "payload": event})

    return SensorAck(
        accepted=True,
        trigger_level=trigger,
        acceleration_resultant_g=resultant,
    )


@app.post("/api/report", response_model=ReportResponse)
async def api_report(
    description: str = Form(..., min_length=1, max_length=5000),
    latitude: float = Form(..., ge=-90.0, le=90.0),
    longitude: float = Form(..., ge=-180.0, le=180.0),
    photo: UploadFile | None = File(default=None),
) -> ReportResponse:
    logger.info("Report POST: desc=%s, lat=%s, lon=%s", description[:20], latitude, longitude)
    report_id = str(uuid.uuid4())
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    photo_path: str | None = None
    if photo is not None:
        raw = await photo.read()
        if raw:
            ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
            target = reports_dir / f"{report_id}{ext}"
            target.write_bytes(raw)
            photo_path = str(target)

    async with state.catalog_lock:
        ev_id, _, _ = nearest_event_context(state.usgs_catalog, latitude, longitude)

    meta = {
        "report_id": report_id,
        "timestamp_utc": datetime.now(tz=UTC).isoformat(),
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "photo_path": photo_path,
        "causative_event_id": ev_id,
    }

    meta_path = reports_dir / f"{report_id}.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    await state.connections.broadcast({"type": "crowd_report", "payload": meta})

    return ReportResponse(
        report_id=report_id,
        stored_photo_path=photo_path,
        causative_event_id=ev_id,
        status="received",
    )


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await state.connections.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "welcome",
                "payload": {
                    "server_time_utc": datetime.now(tz=UTC).isoformat(),
                    "message": "Connected to TerraWatch live stream",
                },
            }
        )

        while True:
            # Keep connection open and accept optional pings from frontend.
            msg = await websocket.receive_text()
            if msg.lower() == "ping":
                await websocket.send_json({"type": "pong", "payload": {"t": time.time()}})
    except WebSocketDisconnect:
        await state.connections.disconnect(websocket)
    except Exception:
        await state.connections.disconnect(websocket)


# ---------------------------------------------------------------------------
# 7) LLM Layman Translation Engine
# ---------------------------------------------------------------------------

@app.post("/api/layman_summary", response_model=LaymanSummaryResponse)
async def api_layman_summary(req: LaymanSummaryRequest) -> LaymanSummaryResponse:
    try:
        response = llm_layman_translation_stub(req)
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Layman summary schema violation: {exc}")

    return response


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error("422 Validation Error: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc)},
    )

# ---------------------------------------------------------------------------
# Frontend Hosting (React build served by FastAPI)
# ---------------------------------------------------------------------------

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")


@app.get("/", response_model=None)
async def frontend_index() -> FileResponse | JSONResponse:
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        status_code=200,
        content={
            "message": "Frontend build not found. Build React app in ./frontend with `npm run build`."
        },
    )


@app.get("/{full_path:path}", response_model=None)
async def frontend_spa_fallback(full_path: str) -> FileResponse | JSONResponse:
    # 1. Check if the file actually exists in the frontend dist directory 
    # (manifest.webmanifest, sw.js, workbox-*.js, icons, etc.)
    target_file = FRONTEND_DIST_DIR / full_path
    if target_file.exists() and target_file.is_file():
        # Prevent accidentaly serving index.html twice here
        if full_path != "index.html":
            return FileResponse(target_file)

    # 2. Block direct API/WS/Assets 404s
    if full_path.startswith("api/") or full_path.startswith("ws/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not Found")

    # 3. Handle SPA routing: all other non-file paths return index.html
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    
    return JSONResponse(
        status_code=404,
        content={
            "message": "Frontend route requested but build is missing.",
            "path": full_path,
        },
    )


# ---------------------------------------------------------------------------
# Local dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True)
