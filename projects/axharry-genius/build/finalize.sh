#!/usr/bin/env bash
# Mix and encode one FINAL deliverable with the narration, music and effects of an approved voice.
# Usage: build/finalize.sh LANG WORK PROPS PICTURE OUTPUT_NAME TAG SIZE
#   e.g. build/finalize.sh en work/en-ref motion/props/en-footage.json output/en-footage/picture-1080.mp4 \
#        AXHARRY_ENGLISH_FINAL_9x16_1080p.mp4 en-final-916-1080 1080x1920
set -euo pipefail
cd "$(dirname "$0")/.."
lang=$1 work=$2 props=$3 picture=$4 out=$5 tag=$6 size=$7
python3 build/mix.py "$lang" --work "$work" --props "$props" --picture "$picture" --output "$out" --tag "$tag" --size "$size"
mv "$work/render-plan.json" "$work/render-plan-$tag.json"
python3 ../../skills/video-editing/scripts/video_workbench.py render-ffmpeg "$work/render-plan-$tag.json"
