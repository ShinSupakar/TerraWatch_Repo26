from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "aftershock_transformer_scripted.pt",
    ROOT / "terrawatch" / "RealESRGAN_x4plus.pth",
    ROOT / "terrawatch" / "models" / "enhanced_yolov8n" / "weights" / "best.pt",
    ROOT / "terrawatch" / "models" / "baseline_yolov8n" / "weights" / "best.pt",
]

optional = [
    ROOT / "aftershock_transformer.pt",
    ROOT / "best_transformer.pt",
    ROOT / "terrawatch" / "damage_model_best.pt",
    ROOT / "terrawatch" / "model_metadata.json",
    ROOT / "terrawatch" / "data" / "xbd_yolo" / "damage.yaml",
    ROOT / "terrawatch" / "data" / "xbd_enhanced" / "damage.yaml",
]

missing_required = [p for p in required if not p.exists()]

print("Asset check")
print("===========")
for p in required:
    status = "OK" if p.exists() else "MISSING"
    print(f"[{status}] {p}")

for p in optional:
    status = "OK" if p.exists() else "SKIP"
    print(f"[{status}] {p}")

if missing_required:
    raise SystemExit("\nMissing required model assets. See lines marked [MISSING].")

print("\nAll required assets are in place.")
