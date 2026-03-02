from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "aftershock_transformer_scripted.pt",
    # Real-ESRGAN weights are large (>25 MB) and can be downloaded separately.
    # If missing the server will use a stub enhancer. See README for link.
    #ROOT / "terrawatch" / "RealESRGAN_x4plus.pth",
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
    ROOT / "terrawatch" / "RealESRGAN_x4plus.pth",  # large, treated separately
]

missing_required = [p for p in required if not p.exists()]

# if ESRGAN weights are missing and fetch script exists, try to download
esrgan_path = ROOT / "terrawatch" / "RealESRGAN_x4plus.pth"
if (not esrgan_path.exists()) and Path("scripts/fetch_weights.sh").exists():
    print("[check_assets] ESRGAN weights missing; attempting to fetch via script")
    import subprocess
    try:
        subprocess.run(["bash", "scripts/fetch_weights.sh"], check=True)
    except Exception:  # ignore failures, user will see missing notice below
        print("[check_assets] fetch_weights.sh failed; you may download manually")


print("Asset check")
print("===========")
for p in required:
    status = "OK" if p.exists() else "MISSING"
    print(f"[{status}] {p}")

for p in optional:
    status = "OK" if p.exists() else "SKIP"
    print(f"[{status}] {p}")

# hint about large ESRGAN model
esrgan_path = ROOT / "terrawatch" / "RealESRGAN_x4plus.pth"
if not esrgan_path.exists():
    script = ROOT / "scripts" / "fetch_weights.sh"
    if script.exists():
        print("\n[hint] ESRGAN weights missing; attempting automatic download via fetch_weights.sh")
        os.system(f"bash {script}")
    else:
        print(f"\n[hint] ESRGAN weights missing: run `bash scripts/fetch_weights.sh` or\
  download manually and set ESRGAN_WEIGHTS_PATH to point at {esrgan_path}")

if missing_required:
    raise SystemExit("\nMissing required model assets. See lines marked [MISSING].")

print("\nAll required assets are in place.")
