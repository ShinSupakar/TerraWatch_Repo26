#!/usr/bin/env bash
set -euo pipefail

# Downloads large pretrained model weights used by the TerraWatch backend.
# Currently only Real-ESRGAN is managed; add more targets here as needed.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# default ESRGAN download URL (adjust version as needed)
ESRGAN_URL="${ESRGAN_URL:-https://github.com/xinntao/Real-ESRGAN/releases/download/v0.3.0/RealESRGAN_x4plus.pth}"
DEST="$ROOT_DIR/terrawatch/RealESRGAN_x4plus.pth"

echo "[fetch_weights] ensuring model directory exists"
mkdir -p "$(dirname "$DEST")"

if [[ -f "$DEST" ]]; then
    echo "[fetch_weights] already have ESRGAN weights at $DEST"
    exit 0
fi

# download

echo "[fetch_weights] downloading Real-ESRGAN weights from $ESRGAN_URL"
if command -v curl >/dev/null 2>&1; then
    curl -L "$ESRGAN_URL" -o "$DEST"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$DEST" "$ESRGAN_URL"
else
    echo "Error: neither curl nor wget available to fetch weights" >&2
    exit 1
fi

echo "[fetch_weights] download complete"
