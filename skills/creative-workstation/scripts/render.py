#!/usr/bin/env python3
"""Render a compiled timeline to a verified master: chunked Remotion video + streamed audio mix + loudnorm + mux.

    render.py PROJECT_DIR [--timeline timeline.json] [--out renders/final.mp4] [--chunk-seconds 60]
              [--scale 1.0] [--width 3840 --height 2160] [--crf 18] [--concurrency 4] [--audio-only]

* Video renders in chunks (`--frames=a-b`, muted) that are reused if already complete, so long renders
  (10, 30, 60+ minutes) are resumable and memory-flat; chunks are joined with the concat demuxer (-c copy).
* Audio is mixed in Python from the timeline's absolute cue sheet (music + SFX) in 10 s blocks, then mastered by a
  measured loop (gain → 4x-oversampled limiter → AAC → re-measure) to −16 LUFS / ≤ −1.5 dBTP and muxed.
* --remaster MASTER.mp4 re-does only the audio of an existing master (video stream-copied) and re-verifies.
* Writes PROJECT/renders/<name>.render.json with timings and the verification report.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine"
DEFAULT_BROWSER = "/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
SR = 48000


def run(cmd, **kw):
    print("$", " ".join(str(c) for c in cmd)[:400], flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-count_packets", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def video_frames(path: Path) -> int:
    for s in probe(path)["streams"]:
        if s["codec_type"] == "video":
            return int(s.get("nb_read_packets") or s.get("nb_frames") or 0)
    return 0


# ------------------------------------------------------------------ audio


def ensure_music(project: Path, tl: dict) -> Path | None:
    music = tl.get("audio", {}).get("music")
    if not music:
        return None
    if isinstance(music, dict) and "generate" in music:
        g = music["generate"]
        dur = tl["meta"]["durationFrames"] / tl["meta"]["fps"] if "durationFrames" in tl["meta"] else tl["meta"]["durationInFrames"] / tl["meta"]["fps"]
        out = project / "work" / f"music-{g.get('style', 'noir')}-{int(tl['meta']['bpm'])}bpm-{dur:.3f}s.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            run([sys.executable, HERE / "audio_synth.py", "music", out, "--duration", f"{dur:.3f}",
                 "--bpm", str(tl["meta"]["bpm"]), "--seed", str(g.get("seed", 7)), "--style", g.get("style", "noir")])
        return out
    return project / "public" / music


def load_clip(path: Path) -> np.ndarray:
    import soundfile as sf
    try:
        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        x, sr = None, None
    if x is None or sr != SR:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                             capture_output=True, check=True).stdout
        x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2]


def mix_audio(project: Path, tl: dict, out_wav: Path) -> dict:
    import soundfile as sf
    fps = tl["meta"]["fps"]
    total = int(round(tl["meta"]["durationInFrames"] / fps * SR))
    music_path = ensure_music(project, tl)
    mvol = float(tl.get("audio", {}).get("musicVolume", 0.9))
    cues = tl.get("audio", {}).get("cues", [])
    cache: dict[str, np.ndarray] = {}
    placed = []
    for c in cues:
        src = project / "public" / c["src"]
        if c["src"] not in cache:
            cache[c["src"]] = load_clip(src)
        start = int(round(c["at"] * SR))
        placed.append((start, cache[c["src"]], float(c.get("volume", 0.6))))
    mus = sf.SoundFile(str(music_path)) if music_path else None
    if mus is not None and mus.samplerate != SR:
        raise SystemExit(f"music must be {SR} Hz WAV (got {mus.samplerate}); convert it first")
    block = SR * 10
    peak = 0.0
    with sf.SoundFile(str(out_wav), "w", SR, 2, subtype="PCM_24") as fh:
        for b0 in range(0, total, block):
            n = min(block, total - b0)
            buf = np.zeros((n, 2), dtype=np.float32)
            if mus is not None:
                m = mus.read(n, dtype="float32", always_2d=True)
                if m.shape[1] == 1:
                    m = np.repeat(m, 2, axis=1)
                buf[:len(m)] += m[:, :2] * mvol
            for start, clip, vol in placed:
                a, z = max(start, b0), min(start + len(clip), b0 + n)
                if a < z:
                    buf[a - b0:z - b0] += clip[a - start:z - start] * vol
            peak = max(peak, float(np.abs(buf).max()) if len(buf) else 0)
            fh.write(np.tanh(buf))  # soft clip safety; loudnorm sets the final level
    return {"music": str(music_path) if music_path else None, "cues": len(cues), "samples": total, "pre_peak": round(peak, 3)}


def measure_loudness(path: Path) -> dict:
    """EBU R128 integrated loudness + true peak (4x oversampled) of a file, as ffmpeg's ebur128 reports them."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    I = float(summ.split("I:")[1].split("LUFS")[0])
    TP = float(summ.split("Peak:")[1].split("dBFS")[0])
    LRA = float(summ.split("LRA:")[1].split("LU")[0])
    return {"I": I, "TP": TP, "LRA": LRA}


def master_audio(wav: Path, out_m4a: Path, target: dict, max_passes: int = 4) -> dict:
    """Measured mastering loop: gain to the loudness target, then a true-peak-safe limiter, encode AAC, re-measure the
    ENCODED file and correct gain/ceiling until integrated loudness is within ±0.5 LU and true peak <= target.

    Why not ffmpeg loudnorm: with the beds this workstation produces (≈ −19…−21 LUFS, peaks ≈ −1.5…−2 dBTP) the
    +3…5 dB needed makes loudnorm's linear mode impossible, so it silently falls back to dynamic mode, and AAC
    encoding then overshoots its true-peak target (measured −0.7 dBTP on a 10-minute master with TP=−1.5)."""
    I_t, TP_t = float(target.get("I", -16)), float(target.get("TP", -1.5))
    src = measure_loudness(wav)
    gain = I_t - src["I"]
    ceiling = TP_t - 2.0  # dBFS on the 4x-oversampled signal; measured: −2.5 still gave −0.7 dBTP after AAC, −3.5 gave −2.6
    passes = []
    for k in range(max_passes):
        lim = max(0.0625, 10 ** (ceiling / 20))
        # latency=true: compensate the limiter's look-ahead so picture/sound sync stays sample-accurate.
        # level=false: no auto make-up gain (the volume stage sets loudness).
        af = (f"volume={gain:.3f}dB,aresample={SR * 4},"
              f"alimiter=limit={lim:.5f}:attack=2:release=80:level=false:latency=true,aresample={SR}")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav, "-af", af, "-ar", str(SR),
             "-c:a", "aac", "-b:a", "256k", out_m4a])
        out = measure_loudness(out_m4a)
        ok = abs(out["I"] - I_t) <= 0.5 and out["TP"] <= TP_t
        passes.append({"pass": k + 1, "gain_db": round(gain, 3), "ceiling_dbfs": round(ceiling, 2), "out": out, "ok": ok})
        if ok:
            break
        if out["TP"] > TP_t:
            ceiling -= (out["TP"] - TP_t) + 0.2
        gain += I_t - out["I"]
    return {"method": "gain + 4x-oversampled limiter + AAC, re-measured (ebur128)", "source": src,
            "target": {"I": I_t, "TP": TP_t}, "passes": passes, "result": passes[-1]["out"], "compliant": passes[-1]["ok"]}


# ------------------------------------------------------------------ video


def bundle(cache_dir: Path) -> Path:
    """Bundle the engine once; reuse for every chunk (re-bundling per chunk costs ~10-20 s each)."""
    out = cache_dir / "bundle"
    stamp = max(p.stat().st_mtime for p in (ENGINE / "src").rglob("*") if p.is_file())
    if out.exists() and (out / ".stamp").exists() and float((out / ".stamp").read_text()) >= stamp:
        return out
    shutil.rmtree(out, ignore_errors=True)
    empty_public = cache_dir / "empty-public"
    empty_public.mkdir(parents=True, exist_ok=True)
    run(["npx", "remotion", "bundle", "src/index.ts", "--out-dir", out, "--public-dir", empty_public], cwd=ENGINE)
    (out / ".stamp").write_text(str(stamp))
    return out


def render_video(project: Path, props: Path, tl: dict, out: Path, chunk_s: float, crf: int, conc: int, scale: float) -> dict:
    fps = tl["meta"]["fps"]
    total = tl["meta"]["durationInFrames"]
    chunk = max(1, int(round(chunk_s * fps)))
    env = {**os.environ, "REMOTION_BROWSER": os.environ.get("REMOTION_BROWSER", DEFAULT_BROWSER)}
    bdir = bundle(project / "work")
    # Chunks are only reusable for the same timeline + engine build + settings: key the folder by a hash of them,
    # so editing the storyboard or the engine never silently re-uses stale chunks.
    import hashlib
    key = hashlib.sha1(props.read_bytes() + (bdir / ".stamp").read_bytes() + f"{chunk}|{crf}|{scale}|bt709-tv".encode()).hexdigest()[:10]
    work = project / "work" / f"chunks-{out.stem}-{key}"
    work.mkdir(parents=True, exist_ok=True)
    # Serve the project's public folder (symlink to the media library) next to the bundle.
    pub = bdir / "public"
    if pub.is_symlink() or pub.exists():
        if pub.is_symlink() or pub.is_file():
            pub.unlink()
        else:
            shutil.rmtree(pub)
    pub.symlink_to((project / "public").resolve())
    parts, timings = [], []
    for k, a in enumerate(range(0, total, chunk)):
        b = min(total, a + chunk) - 1
        part = work / f"part-{k:04d}.mp4"
        if part.exists() and video_frames(part) == b - a + 1:
            parts.append(part)
            continue
        t0 = time.time()
        cmd = ["npx", "remotion", "render", bdir, "Promo", part, f"--props={props}", f"--frames={a}-{b}", "--muted",
               "--codec=h264", f"--crf={crf}", "--pixel-format=yuv420p", "--color-space=bt709", f"--concurrency={conc}",
               f"--browser-executable={env['REMOTION_BROWSER']}", "--log=error", f"--scale={scale}"]
        run(cmd, cwd=ENGINE, env=env)
        n = video_frames(part)
        if n != b - a + 1:
            raise SystemExit(f"chunk {k} has {n} frames, expected {b - a + 1}")
        dt = time.time() - t0
        timings.append({"chunk": k, "frames": n, "seconds": round(dt, 1), "fps": round(n / dt, 2)})
        print(f"[render] chunk {k}: frames {a}-{b} in {dt:.1f}s ({n / dt:.2f} fps)", flush=True)
        parts.append(part)
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    joined = work / "video.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    return {"video": str(joined), "chunks": len(parts), "chunk_frames": chunk, "timings": timings}


# ------------------------------------------------------------------ verify


def verify(final: Path, tl: dict, review: Path) -> dict:
    review.mkdir(parents=True, exist_ok=True)
    fps = tl["meta"]["fps"]
    pr = probe(final)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    a = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    num, den = v["r_frame_rate"].split("/")
    expected = tl["meta"]["durationInFrames"]
    frames = int(v.get("nb_read_packets") or 0)
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"], capture_output=True, text=True)
    try:
        lm = measure_loudness(final)
        I, TP = lm["I"], lm["TP"]
    except Exception:
        I = TP = None
    rep = {
        "file": str(final), "bytes": final.stat().st_size,
        "width": v["width"], "height": v["height"], "fps": round(float(num) / float(den), 3),
        "video_codec": v["codec_name"], "pix_fmt": v.get("pix_fmt"), "color_range": v.get("color_range"),
        "color_space": v.get("color_space"), "color_transfer": v.get("color_transfer"), "color_primaries": v.get("color_primaries"),
        "frames": frames, "expected_frames": expected, "frames_match": frames == expected,
        "duration": round(float(pr["format"]["duration"]), 3), "expected_duration": round(expected / fps, 3),
        "audio": bool(a), "audio_codec": a and a["codec_name"], "audio_rate": a and int(a["sample_rate"]),
        "audio_duration": a and round(float(a.get("duration", 0)), 3),
        "integrated_lufs": I, "true_peak_dbfs": TP, "full_decode_errors": dec.stderr.strip()[:500] or None,
    }
    # review artefacts: contact sheet + stills at slot boundaries (+0.5 s)
    n = max(12, min(48, len(tl["scenes"]) * 2))
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", final, "-vf",
         f"fps={n}/{max(1, rep['duration'])},scale=480:-2,tile=6x{math.ceil(n / 6)}", "-frames:v", "1", review / "contact-sheet.jpg"])
    stills = []
    for s in tl["scenes"][:40]:
        t = s["slot"]["start"] / fps + min(2.0, (s["slot"]["end"] - s["slot"]["start"]) / fps / 2)
        p = review / f"still-{s['id']}.jpg"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(final),
                        "-frames:v", "1", "-vf", "scale=960:-2", str(p)], check=True)
        stills.append(str(p))
    rep["stills"] = stills
    rep["contact_sheet"] = str(review / "contact-sheet.jpg")
    tgt = tl.get("audio", {}).get("loudness", {})
    rep["loudness_compliant"] = bool(I is not None and TP is not None and abs(I - tgt.get("I", -16)) <= 0.5
                                     and TP <= tgt.get("TP", -1.5))
    rep["passed"] = bool(rep["frames_match"] and rep["audio"] and not rep["full_decode_errors"]
                         and abs(rep["duration"] - rep["expected_duration"]) < 0.1 and rep["loudness_compliant"])
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path)
    ap.add_argument("--timeline", default="timeline.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--chunk-seconds", type=float, default=60)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--scale", type=float, default=1.0, help="render scale (0.5 = draft at half resolution)")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--remaster", type=Path, help="existing master: re-mix + re-master its audio, stream-copy its video, re-verify")
    a = ap.parse_args(argv)
    project = a.project.resolve()
    tl_path = project / a.timeline
    tl = json.loads(tl_path.read_text())
    out = (a.out or project / "renders" / f"{tl_path.stem}.mp4").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    props = project / "work" / f"{tl_path.stem}.props.json"
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text(json.dumps({"timeline": tl}))
    t0 = time.time()
    report = {"timeline": str(tl_path), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    wav = project / "work" / f"{tl_path.stem}.mix.wav"
    report["mix"] = mix_audio(project, tl, wav)
    m4a = project / "work" / f"{out.stem}.m4a"
    report["loudness"] = master_audio(wav, m4a, tl.get("audio", {}).get("loudness", {}))
    if a.audio_only:
        print(json.dumps(report, indent=2))
        return 0
    if a.remaster:
        src = a.remaster.resolve()
        tmp = out.with_name(out.stem + ".remaster.tmp.mp4")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-i", m4a, "-map", "0:v", "-map", "1:a",
             "-c", "copy", "-shortest", "-movflags", "+faststart", tmp])
        tmp.replace(src)
        report["remastered"] = str(src)
        report["render_seconds"] = round(time.time() - t0, 1)
        report["verify"] = verify(src, tl, project / "review" / src.stem)
        src.with_suffix(".render.json").write_text(json.dumps(report, indent=2))
        v = report["verify"]
        print(json.dumps({k: v[k] for k in ("file", "frames", "expected_frames", "duration", "integrated_lufs",
                                            "true_peak_dbfs", "loudness_compliant", "passed")}, indent=2))
        return 0 if v["passed"] else 1
    report["video"] = render_video(project, props, tl, out, a.chunk_seconds, a.crf, a.concurrency, a.scale)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", report["video"]["video"], "-i", m4a,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", out])
    report["render_seconds"] = round(time.time() - t0, 1)
    report["verify"] = verify(out, tl, project / "review" / out.stem)
    (out.with_suffix(".render.json")).write_text(json.dumps(report, indent=2))
    v = report["verify"]
    print(json.dumps({k: v[k] for k in ("file", "width", "height", "fps", "frames", "expected_frames", "duration",
                                        "audio_codec", "audio_rate", "integrated_lufs", "true_peak_dbfs",
                                        "loudness_compliant", "passed")}, indent=2))
    print(f"[render] total {report['render_seconds']}s")
    return 0 if v["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
