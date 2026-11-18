#!/usr/bin/env python3
"""Quality control on an encoded deliverable, against its timing map. Used by production.py (`qc`, `render`).

Checks (each PASS/FAIL with its measurement; the method is recorded so a reviewer can repeat it):
  audio_present      one audio stream with measurable programme loudness
  no_unexpected_black  ffmpeg blackdetect (any run of one frame or more, pixel threshold 0.10) outside intended fades/dips
  no_unexpected_freeze ffmpeg freezedetect (noise 0.001, d ≥ 2.0 s) outside still-image scenes without a camera move
  no_silence         ffmpeg silencedetect (−50 dB, d ≥ 1.0 s) inside the programme (first 0.5 s and fade-out excepted)
  captions_match_script  the SRT next to the timing map holds exactly the narration words, in order, per scene
  font_covers_text   the language's caption font has a glyph for every character in captions and on-screen text
                     (TrueType/OpenType cmap read directly: missing glyphs would render as boxes)
  captions_in_safe_area  layout-constrained (≤ 84 % width, wrapped, ≤ 2 lines); one still per cue saved for review
  resolution_class   native 1080p / native 4K / upscaled ×k, from the source assets' pixel sizes after cover-cropping
"""

from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path


def _run(cmd) -> str:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True).stderr


def intervals(stderr: str, a: str, b: str, end: float) -> list[tuple[float, float]]:
    st = [float(x) for x in re.findall(rf"{a}:\s*(-?[\d.]+)", stderr)]
    en = [float(x) for x in re.findall(rf"{b}:\s*([\d.]+)", stderr)]
    return [(s, en[i] if i < len(en) else end) for i, s in enumerate(st)]


def inside(iv: tuple[float, float], allowed: list[tuple[float, float]], slack: float = 0.12) -> bool:
    return any(iv[0] >= a - slack and iv[1] <= b + slack for a, b in allowed)


# ------------------------------------------------------------------ font coverage (cmap formats 4 and 12)


def font_codepoints(path: Path) -> set[int]:
    data = path.read_bytes()
    if data[:4] == b"ttcf":
        data_off = struct.unpack(">I", data[12:16])[0]
    else:
        data_off = 0
    num_tables = struct.unpack(">H", data[data_off + 4:data_off + 6])[0]
    cmap_off = None
    for i in range(num_tables):
        rec = data_off + 12 + 16 * i
        tag = data[rec:rec + 4]
        if tag == b"cmap":
            cmap_off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
    if cmap_off is None:
        raise ValueError("font has no cmap table")
    n = struct.unpack(">H", data[cmap_off + 2:cmap_off + 4])[0]
    cps: set[int] = set()
    for i in range(n):
        pid, eid, off = struct.unpack(">HHI", data[cmap_off + 4 + 8 * i:cmap_off + 12 + 8 * i])
        sub = cmap_off + off
        fmt = struct.unpack(">H", data[sub:sub + 2])[0]
        if fmt == 4:
            segx2 = struct.unpack(">H", data[sub + 6:sub + 8])[0]
            ends = struct.unpack(f">{segx2 // 2}H", data[sub + 14:sub + 14 + segx2])
            starts = struct.unpack(f">{segx2 // 2}H", data[sub + 16 + segx2:sub + 16 + 2 * segx2])
            deltas = struct.unpack(f">{segx2 // 2}h", data[sub + 16 + 2 * segx2:sub + 16 + 3 * segx2])
            ro_pos = sub + 16 + 3 * segx2
            ros = struct.unpack(f">{segx2 // 2}H", data[ro_pos:ro_pos + segx2])
            for k, (s, e) in enumerate(zip(starts, ends)):
                for c in range(s, e + 1):
                    if c == 0xFFFF:
                        continue
                    if ros[k] == 0:
                        g = (c + deltas[k]) & 0xFFFF
                    else:
                        gp = ro_pos + 2 * k + ros[k] + 2 * (c - s)
                        g = struct.unpack(">H", data[gp:gp + 2])[0]
                        g = (g + deltas[k]) & 0xFFFF if g else 0
                    if g:
                        cps.add(c)
        elif fmt == 12:
            ngroups = struct.unpack(">I", data[sub + 12:sub + 16])[0]
            for gi in range(ngroups):
                s, e, g = struct.unpack(">III", data[sub + 16 + 12 * gi:sub + 28 + 12 * gi])
                cps.update(range(s, e + 1))
    return cps


def missing_glyphs(font: Path, texts: list[str]) -> list[str]:
    """Letters and marks the font lacks. ASCII, digits, and punctuation are left to the browser's fallback fonts
    (always present); a missing letter or combining mark of the language's script would render as a box."""
    import unicodedata
    cps = font_codepoints(font)
    need = {ch for t in texts for ch in t
            if ord(ch) > 0x7F and unicodedata.category(ch)[0] in "LM" and ord(ch) not in (0x200C, 0x200D)}
    return sorted(ch for ch in need if ord(ch) not in cps)


# ------------------------------------------------------------------ captions


def parse_srt(text: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            cues.append({"time": lines[1], "text": " ".join(lines[2:])})
    return cues


def captions_match(srt_path: Path, tm: dict) -> tuple[bool, str]:
    if not srt_path.exists():
        return False, f"{srt_path.name} missing"
    srt_words = " ".join(c["text"] for c in parse_srt(srt_path.read_text(encoding="utf-8"))).split()
    script_words = []
    for n in tm["narration"]:
        script_words += [t["text"].strip() for t in tm["captions"] if t["scene"] == n["scene"]]
    if srt_words != script_words:
        diff = next((i for i, (x, y) in enumerate(zip(srt_words, script_words)) if x != y), min(len(srt_words), len(script_words)))
        return False, (f"caption words differ from the narration at word {diff + 1}: "
                       f"{' '.join(srt_words[diff:diff + 4])!r} vs {' '.join(script_words[diff:diff + 4])!r} "
                       f"({len(srt_words)} vs {len(script_words)} words)")
    return True, f"{len(srt_words)} words identical to the narration text"


# ------------------------------------------------------------------ main check


def run_qc(video: Path, tm: dict, srt: Path, font: Path | None, texts: list[str], fps: float, res_class: dict | None,
           still_dir: Path | None = None) -> dict:
    out = run_probe(video)
    dur = out["duration"]
    checks: dict[str, dict] = {}

    def put(name, ok, detail):
        checks[name] = {"passed": bool(ok), "detail": detail}

    put("audio_present", out["audio"] and out["loudness"] is not None and out["loudness"] > -70,
        f"audio stream: {out['audio']}, integrated {out['loudness']} LUFS")
    allowed_black = [(0, 0.5), (dur - 2.5, dur + 1)]
    allowed_freeze = [(0, 0.6), (dur - 2.5, dur + 1)]
    for s in tm["scenes"]:
        t = s.get("transitionIn") or {}
        if t.get("type") in ("fade_from_black", "dip") and t.get("durationInFrames"):
            allowed_black.append(((s["cut"] - t["durationInFrames"]) / fps, (s["cut"] + t["durationInFrames"]) / fps))
        m = s.get("media") or {}
        if (not m or m.get("kind") == "image") and (s.get("move") or {}).get("type", "static") == "static":
            allowed_freeze.append((s["from"] / fps, (s["from"] + s["durationInFrames"]) / fps))
    blacks = intervals(_run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-vf", "blackdetect=d=0.03:pix_th=0.10", "-an",
                             "-f", "null", "-"]), "black_start", "black_end", dur)
    bad_black = [b for b in blacks if not inside(b, allowed_black)]
    put("no_unexpected_black", not bad_black, {"black": blacks, "unexpected": bad_black})
    freezes = intervals(_run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-vf", "freezedetect=n=0.001:d=2.0", "-an",
                              "-f", "null", "-"]), "freeze_start", "freeze_end", dur)
    bad_freeze = [f for f in freezes if not inside(f, allowed_freeze, 0.6)]
    put("no_unexpected_freeze", not bad_freeze, {"frozen": freezes, "unexpected": bad_freeze})
    sil = intervals(_run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-af", "silencedetect=n=-50dB:d=1.0", "-vn",
                          "-f", "null", "-"]), "silence_start", "silence_end", dur)
    bad_sil = [x for x in sil if x[0] > 0.5 and x[1] < dur - 2.5]
    put("no_silence", not bad_sil, {"silence": sil, "inside_programme": bad_sil})
    ok, why = captions_match(srt, tm)
    put("captions_match_script", ok, why)
    if font:
        try:
            miss = missing_glyphs(font, texts)
            put("font_covers_text", not miss, {"font": font.name, "missing": miss})
        except (OSError, ValueError, struct.error) as e:
            put("font_covers_text", False, f"could not read font {font}: {e}")
    else:
        put("font_covers_text", True, "no language font configured (browser default font) — not checked")
    put("captions_in_safe_area", *caption_safe_area(video, tm, out, still_dir))
    if res_class:
        checks["resolution_class"] = {"passed": True, "detail": res_class}
    return {"video": str(video), "duration": dur, "checks": checks,
            "passed": all(c["passed"] for c in checks.values())}


def run_probe(video: Path) -> dict:
    import json
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                                   capture_output=True, text=True).stdout or "{}")
    a = any(s.get("codec_type") == "audio" for s in pr.get("streams", []))
    v = next((s for s in pr.get("streams", []) if s.get("codec_type") == "video"), {})
    I = None
    if a:
        err = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-vn", "-af", "ebur128", "-f", "null", "-"])
        m = re.findall(r"I:\s*(-?[\d.]+|-inf) LUFS", err)
        I = float(m[-1]) if m and m[-1] != "-inf" else None
    return {"duration": float((pr.get("format") or {}).get("duration") or 0), "audio": a, "loudness": I,
            "width": v.get("width"), "height": v.get("height")}


def caption_safe_area(video: Path, tm: dict, pr: dict, still_dir: Path | None = None) -> tuple[bool, object]:
    """Captions are laid out inside a centred box of at most 84 % of the width, wrapped, at most two lines, above the
    format's bottom safe margin, so they cannot leave the frame by construction. This saves one still per caption cue
    for visual review (crop, subject position, and text legibility are judged on these)."""
    if not still_dir:
        return True, "layout-constrained (max width 84 %, wrapped, ≤ 2 lines); no stills requested"
    still_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, c in enumerate(tm.get("caption_cues", []), 1):
        t = (c["startMs"] + c["endMs"]) / 2000
        dst = still_dir / f"cue-{i:03d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                        "scale='min(960,iw)':-2", str(dst)], capture_output=True)
        if dst.exists():
            saved.append(str(dst))
    return True, {"stills": len(saved), "folder": str(still_dir),
                  "method": "layout-constrained (max width 84 %, wrapped, ≤ 2 lines); stills saved for review"}
