# TerraWatch Testbench: Inference and Feature Checks

Run these checks after starting services.

## 0) Recommended Validation Flow (Same as Author-Tested)

Please validate APIs exactly with terminal `curl` commands (not browser URL bar, since browser does `GET` and these are `POST` routes).

```bash
BASE=http://127.0.0.1:8000
```

If your backend is running on another port, update `BASE` accordingly and use it consistently for all commands.

## A) Health Check

```bash
curl -v --max-time 5 $BASE/health
```

Expected keys:
- `status`
- `aftershock_model_source`
- `enhancer_model_source`
- `damage_model_source`

## B) Damage Assessment API

Use any local image.

```bash
curl -v -X POST $BASE/api/damage \
  -F "image=@terrawatch/data/xbd_yolo/test/images/guatemala-volcano_00000023_post_disaster.png" \
  -F "latitude=37.17" \
  -F "longitude=37.03"
```

Expected:
- `damage_boxes` array
- `aggregated_counts`
- `max_damage_class`

## C) Aftershock Forecast API

```bash
curl -v -X POST $BASE/api/aftershock \
  -H "Content-Type: application/json" \
  -d '{
    "mainshock": {
      "magnitude": 7.8,
      "depth_km": 17.9,
      "latitude": 37.17,
      "longitude": 37.03,
      "hour_utc": 12,
      "day_of_year": 60
    },
    "historical_seismicity_48h": [0,1,0,2,1,0,0,1,1,0,0,0,1,2,1,0,0,0,1,1,0,0,2,1,0,0,1,0,1,1,0,0,0,1,0,0,1,0,2,1,0,0,0,1,1,0,0,1]
  }'
```

Expected:
- `forecast_horizon_hours = 24`
- `probabilities_m4_plus` length 24

## D) Frontend UX Check

Open http://127.0.0.1:8000 and verify:
- Incident cards load
- Upload + `ANALYSE` works
- Pipeline progress updates
- Detection overlays appear quickly (fast pass)
- Status line shows refinement is running, then updates when ESRGAN-refined overlay is applied
- `Real-Time ShakeMap` panel appears in right column and updates from live feed
- `Public Safety Brief` appears

## D.1) Two-Pass Overlay Behavior (Fast + ESRGAN)

Expected sequence after clicking `ANALYSE` with an uploaded image:

1. Fast triage overlay appears first (seconds).
2. Status line shows ESRGAN refinement in background.
3. Overlay updates again when ESRGAN-refined output returns.

If refinement fails/slow, fast overlay must still remain visible and usable.

## E) Live WebSocket Check

In browser devtools console:

```js
const ws = new WebSocket('ws://127.0.0.1:8000/ws/live');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

Expected event types include:
- `welcome`
- `usgs_event`
- `shakemap`
- `impact_assessment`
- `aftershock_forecast`
- `damage_assessment`

## F) Layman Translation Endpoint Check

```bash
curl -v -X POST $BASE/api/layman_summary \
  -H "Content-Type: application/json" \
  -d '{
    "magnitude": 6.8,
    "focal_depth_km": 12.0,
    "pga_percent_g": 42.5,
    "aftershock_probability_24h": 0.61
  }'
```

Expected rigid JSON keys:
- `threat_level`
- `summary`
- `safety_steps` (exactly 3 items)

## G) Author-Validated Outcomes

When working correctly, these were observed during validation:
- `/api/aftershock` returns `200` with 24 values in `probabilities_m4_plus` and `model_source="torchscript"`.
- `/api/layman_summary` returns `200` with strict schema keys: `threat_level`, `summary`, `safety_steps`.
- `/api/damage` returns `200` with `damage_boxes`, `aggregated_counts`, `max_damage_class`.
