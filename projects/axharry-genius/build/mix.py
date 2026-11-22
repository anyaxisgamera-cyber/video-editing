"""Premix narration + music, measure it, and write the workbench render plan.

Usage: python build/mix.py LANG [--work work/LANG] [--props motion/props/LANG.json]
                              [--picture output/LANG/picture.mp4] [--output NAME.mp4] [--tag LANG]

If WORK/sfx.wav exists it is mixed in as an effects track (not ducked).

Reads   work/LANG/narration.wav, work/LANG/music.wav, work/LANG/timeline.json,
        content/LANG.json, output/LANG/picture.mp4 (silent Remotion render)
Writes  work/LANG/premix.wav, filtergraphs/LANG.ffgraph, work/LANG/render-plan.json

Audio design:
  * narration is cleaned (high-pass, gentle compression) and normalized to -16 LUFS;
  * music sits at roughly -27 LUFS and is side-chain ducked further under speech,
    then breathes back up for the closing card;
  * the final graph applies a measured (two-pass, linear) loudnorm to -14 LUFS,
    -1.5 dBTP, suitable for YouTube Shorts and Instagram Reels.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


def measure(path: Path, extra: str = "") -> dict:
    graph = f"{extra}loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", graph, "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    return json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S).group(0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("--work")
    ap.add_argument("--props")
    ap.add_argument("--picture")
    ap.add_argument("--output")
    ap.add_argument("--tag", help="name for the filtergraph / render dir (default LANG)")
    ap.add_argument("--uhd", action="store_true", help="deliver 2160x3840 (4K UHD vertical) instead of 1080x1920")
    ap.add_argument("--size", help="delivery WxH, e.g. 1920x1080 or 3840x2160 (overrides --uhd)")
    args = ap.parse_args()
    lang = args.lang
    tag = args.tag or lang
    work = ROOT / (args.work or f"work/{lang}")
    props_path = ROOT / (args.props or f"motion/props/{lang}.json")
    content = json.loads((ROOT / "content" / f"{lang}.json").read_text(encoding="utf-8"))
    canvas = json.loads(props_path.read_text(encoding="utf-8"))["canvas"]
    if args.size:
        out_w, out_h = (int(v) for v in args.size.lower().split("x"))
    else:
        out_w, out_h = (2160, 3840) if args.uhd else (1080, 1920)
    big = out_w * out_h > 1920 * 1080
    duration = canvas["durationInFrames"] / canvas["fps"]
    has_sfx = (work / "sfx.wav").exists()

    voice = measure(work / "narration.wav")
    music = measure(work / "music.wav")
    voice_gain = -16.0 - float(voice["input_i"])
    music_gain = -27.0 - float(music["input_i"])
    sfx_gain = (-29.0 - float(measure(work / "sfx.wav")["input_i"])) if has_sfx else 0.0

    premix = work / "premix.wav"
    graph = (
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=75,"
        f"acompressor=threshold=-20dB:ratio=2.5:attack=15:release=180:makeup=1,"
        f"volume={voice_gain:.2f}dB,asplit=2[voice][key];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_gain:.2f}dB[bed];"
        f"[bed][key]sidechaincompress=threshold=0.03:ratio=4:attack=120:release=900:makeup=1[ducked];"
        + (f"[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={sfx_gain:.2f}dB[fx];"
           f"[voice][ducked][fx]amix=inputs=3:normalize=0:duration=longest,atrim=0:{duration:.3f}[out]"
           if has_sfx else
           f"[voice][ducked]amix=inputs=2:normalize=0:duration=longest,atrim=0:{duration:.3f}[out]")
    )
    inputs = ["-i", str(work / "narration.wav"), "-i", str(work / "music.wav")]
    if has_sfx:
        inputs += ["-i", str(work / "sfx.wav")]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs,
                    "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s24le", str(premix)], check=True)

    m = measure(premix)
    (ROOT / "filtergraphs").mkdir(exist_ok=True)
    ffgraph = ROOT / "filtergraphs" / f"{tag}.ffgraph"
    ffgraph.write_text(
        "[0:v]setsar=1,format=yuv420p[vout];\n"
        f"[1:a]loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
        f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
        f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
        # Safety limiter at -2 dBFS: dynamic-mode loudnorm plus AAC encoding can overshoot
        # the -1.5 dBTP target by a few tenths of a dB.
        "alimiter=limit=0.794:attack=1:release=60:level=false,"
        f"aresample=48000,atrim=start=0:end={duration:.3f},asetpts=PTS-STARTPTS[aout]\n",
        encoding="utf-8",
    )
    frames = canvas["durationInFrames"]
    rel = lambda p: "../" * len(work.relative_to(ROOT).parts) + p  # noqa: E731
    plan = {
        "version": 1,
        "inputs": [rel(args.picture or f"output/{lang}/picture.mp4"), "premix.wav"],
        "filtergraph": rel(f"filtergraphs/{tag}.ffgraph"),
        "output": rel(f"output/{args.output or content['output']}"),
        "work_dir": rel(f"output/{tag}/render"),
        "video_map": "[vout]",
        "audio_map": "[aout]",
        "video": {
            "codec": "libx264",
            "args": ["-preset", "slow", "-crf", "17", "-profile:v", "high", "-level:v", "5.2" if big else "4.2",
                     "-movflags", "+faststart", "-tag:v", "avc1"],
            "pixel_format": "yuv420p",
            "fps": "30",
            "width": out_w,
            "height": out_h,
        },
        "audio": {"codec": "aac", "args": ["-b:a", "192k"], "sample_rate": 48000},
        "validation": {
            "duration": round(frames / 30, 3),
            "duration_tolerance": 0.12,
            "codec": "h264",
            "pixel_formats": ["yuv420p"],
            "lufs": TARGET_I,
            "true_peak": TARGET_TP,
            "loudness_range": TARGET_LRA,
        },
    }
    (work / "render-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({"voice_in": voice["input_i"], "music_in": music["input_i"], "premix_i": m["input_i"],
                      "premix_tp": m["input_tp"]}))


if __name__ == "__main__":
    main()
