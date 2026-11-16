#!/bin/bash
# Report every engine the workstation uses: PASS / FAIL with versions. Exit 1 if a required one is missing.
VENV=${CWS_VENV:-/opt/cws-venv}
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
row() { printf "%-6s %-22s %s\n" "$1" "$2" "$3"; }
need() { # name, version-command
  if out=$(eval "$2" 2>/dev/null | head -1) && [ -n "$out" ]; then row PASS "$1" "$out"; else row FAIL "$1" "missing"; fail=1; fi
}
opt() {
  if out=$(eval "$2" 2>/dev/null | head -1) && [ -n "$out" ]; then row PASS "$1" "$out"; else row WARN "$1" "missing (optional)"; fi
}
need ffmpeg       "ffmpeg -version | awk '{print \$3}'"
need ffprobe      "ffprobe -version | awk '{print \$3}'"
need node         "node --version"
need npx          "npx --version"
need python-venv  "$VENV/bin/python --version"
need Pillow       "$VENV/bin/python -c 'import PIL; print(PIL.__version__)'"
need pillow-heif  "$VENV/bin/python -c 'import pillow_heif; print(pillow_heif.__version__)'"
need OpenCV       "$VENV/bin/python -c 'import cv2; print(cv2.__version__)'"
need numpy/scipy  "$VENV/bin/python -c 'import numpy,scipy; print(numpy.__version__, scipy.__version__)'"
need rembg        "$VENV/bin/python -c 'import rembg, onnxruntime; print(\"onnxruntime\", onnxruntime.__version__)'"
need whisper      "$VENV/bin/python -c 'import whisper, torch; print(\"torch\", torch.__version__)'"
need librosa      "$VENV/bin/python -c 'import librosa; print(librosa.__version__)'"
need scenedetect  "$VENV/bin/python -c 'import scenedetect; print(scenedetect.__version__)'"
need uv           "uv --version"
need ImageMagick  "convert -version | head -1 | awk '{print \$3}'"
need rsvg-convert "rsvg-convert --version"
need blender      "blender --version | head -1"
need remotion     "cd '$SKILL_DIR/engine' && node -p \"require('remotion/package.json').version\""
opt  sox          "sox --version"
opt  tesseract    "tesseract --version | head -1"
opt  chromium     "ls /opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
for f in lut3d loudnorm silencedetect xstack drawtext; do
  if ffmpeg -hide_banner -filters 2>/dev/null | grep -qw "$f"; then row PASS "ffmpeg:$f" ""; else row FAIL "ffmpeg:$f" ""; fail=1; fi
done
row INFO cpu "$(nproc) cores, $(free -g | awk '/Mem/{print $2}') GB RAM, GPU: $(command -v nvidia-smi >/dev/null && nvidia-smi -L | head -1 || echo none)"
exit $fail
