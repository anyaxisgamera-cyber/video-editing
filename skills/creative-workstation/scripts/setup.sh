#!/bin/bash
# Reproduce the creative workstation on Ubuntu 24.04 (x86_64). Idempotent. Run as root (or with sudo).
# Needs network access to: Ubuntu archive, PyPI, npm, download.pytorch.org + download-r2.pytorch.org (CPU torch),
# download.blender.org, github.com release assets (rembg models), openaipublic.azureedge.net (Whisper weights).
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV=${CWS_VENV:-/opt/cws-venv}
BLENDER_VER=${BLENDER_VER:-4.5.16}

echo "== apt: ffmpeg, ImageMagick, librsvg, sox, OFL fonts, OCR, Blender runtime libs"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg imagemagick librsvg2-bin sox libsox-fmt-all \
  fonts-ebgaramond fonts-ebgaramond-extra fonts-urw-base35 fonts-inter fonts-montserrat tesseract-ocr \
  libgl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libice6

echo "== Python venv ($VENV): OpenCV, Whisper (CPU torch), rembg, librosa, scenedetect, pillow-heif, uv"
[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q uv opencv-python-headless pillow-heif scenedetect librosa soundfile scipy numpy pillow
"$VENV/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
"$VENV/bin/pip" install -q openai-whisper "rembg[cpu,cli]"
for b in whisper rembg uv uvx scenedetect; do ln -sf "$VENV/bin/$b" /usr/local/bin/$b; done

echo "== Blender $BLENDER_VER LTS (official build, checksum-verified)"
if ! command -v blender >/dev/null || ! blender --version 2>/dev/null | grep -q "$BLENDER_VER"; then
  MAJ=${BLENDER_VER%.*}
  cd /opt
  curl -fsSL -o blender.tar.xz "https://download.blender.org/release/Blender$MAJ/blender-$BLENDER_VER-linux-x64.tar.xz"
  curl -fsSL "https://download.blender.org/release/Blender$MAJ/blender-$BLENDER_VER.sha256" | grep linux-x64 \
    | awk '{print $1"  blender.tar.xz"}' | sha256sum -c -
  tar -xJf blender.tar.xz && rm blender.tar.xz
  ln -sf "/opt/blender-$BLENDER_VER-linux-x64/blender" /usr/local/bin/blender
fi

echo "== Remotion engine (npm ci)"
(cd "$SKILL_DIR/engine" && npm ci --no-audit --no-fund)

echo "== Fonts for rsvg/Pillow (OFL, from the media library if present)"
if [ -d /home/user/creative-studio/media-library/fonts ]; then
  mkdir -p /usr/local/share/fonts/cws && cp /home/user/creative-studio/media-library/fonts/*.ttf /usr/local/share/fonts/cws/ && fc-cache -f >/dev/null
fi
"$SKILL_DIR/scripts/doctor.sh"
