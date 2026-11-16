#!/usr/bin/env python3
"""Scene-by-scene breakdown of a reference video — measured evidence for recreating its edit.

    /opt/cws-venv/bin/python reference_breakdown.py REFERENCE.mp4 OUT_DIR [--ocr-step 0.5] [--ocr-lang eng+tel]
        [--asr small|base|none] [--asr-lang en] [--no-ocr]

What is measured (per frame at the source frame rate, on a 320-px analysis copy):
  shots & transitions  hard cut (histogram jump), dissolve (cross-fade verified by a linear-blend fit of the frames
                       between the two shots), dip to black / white and fade in/out (luma runs + ramps), flash
                       (short white peak); each with start frame, duration and whether it is blurred.
  camera               per-frame similarity transform between consecutive frames (ORB + RANSAC,
                       cv2.estimateAffinePartial2D) accumulated per shot → push-in / pull-out (zoom %), pan
                       left/right, tilt up/down, roll, handheld jitter, static; speed per second.
  grade & lighting     mean luma (key), contrast, black/white points, saturation, warmth (R−B), tint, split-tone
                       (shadow vs highlight warmth), dominant palette, letterbox bars.
  text                 Tesseract OCR (eng+tel) every --ocr-step s: on-screen text events with start/end, position
                       (top / centre / lower-third / bottom), size, script (Latin/Telugu) and entrance style
                       (cut-in vs fade/blur-in, from the text region's edge-density ramp).
  audio                EBU R128 loudness, speech transcript with word times (Whisper), tempo + beat grid
                       (librosa), cut-on-beat ratio, hits/whooshes at transitions, silences, music-under-speech level.
  atmosphere           derived labels (pacing, key, temperature, motion style) — marked "derived", not observed.

Outputs OUT_DIR/breakdown.json, BREAKDOWN.md (scene table), contact.jpg, shots/NNN.jpg.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

AW = 320  # analysis width
STRIDE = 3  # camera motion is measured between frames t-3 and t


# ------------------------------------------------------------------ io


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    num, den = v["r_frame_rate"].split("/")
    return {"width": v["width"], "height": v["height"], "fps": float(num) / float(den),
            "duration": float(d["format"]["duration"]), "has_audio": a is not None, "video_codec": v["codec_name"]}


def frames(path: Path, w: int, h: int):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=area", "-pix_fmt", "rgb24",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


# ------------------------------------------------------------------ per-frame features


def analyse_frames(path: Path, info: dict) -> dict:
    import cv2
    w = AW
    h = int(round(info["height"] * w / info["width"] / 2)) * 2
    orb = cv2.ORB_create(nfeatures=500, fastThreshold=12)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    F = {k: [] for k in ("luma", "lstd", "sat", "warm", "tint", "p2", "p98", "sharp", "hist", "thumb", "motion",
                         "bars_top", "bars_bot", "edge")}
    ring: list = []   # (kp, des) of the last STRIDE frames
    for rgb in frames(path, w, h):
        f = rgb.astype(np.float32) / 255
        y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 4, 4], [0, 180, 0, 256, 0, 256]).ravel()
        hist /= hist.sum() + 1e-9
        gray = (y * 255).astype(np.uint8)
        rows = y.mean(axis=1)
        top = int(np.argmax(rows > 0.05)) if (rows > 0.05).any() else h
        bot = int(np.argmax(rows[::-1] > 0.05)) if (rows > 0.05).any() else h
        F["luma"].append(float(y.mean())); F["lstd"].append(float(y.std()))
        F["sat"].append(float(hsv[..., 1].mean() / 255))
        F["warm"].append(float((f[..., 0] - f[..., 2]).mean()))
        F["tint"].append(float((f[..., 1] - (f[..., 0] + f[..., 2]) / 2).mean()))
        F["p2"].append(float(np.percentile(y, 2))); F["p98"].append(float(np.percentile(y, 98)))
        F["sharp"].append(float(cv2.Laplacian(gray, cv2.CV_32F).var()))
        F["hist"].append(hist.astype(np.float32))
        F["thumb"].append(cv2.resize(rgb, (64, 36), interpolation=cv2.INTER_AREA))
        F["bars_top"].append(top / h); F["bars_bot"].append(bot / h)
        F["edge"].append(cv2.resize(cv2.Canny(gray, 80, 160), (32, 18), interpolation=cv2.INTER_AREA))
        kp, des = orb.detectAndCompute(gray, None)
        mot = None
        prev_kp, prev_des = ring[0] if len(ring) == STRIDE else (None, None)
        if prev_des is not None and des is not None and len(kp) >= 12 and len(prev_kp) >= 12:
            m = bf.match(prev_des, des)
            if len(m) >= 12:
                a = np.float32([prev_kp[x.queryIdx].pt for x in m])
                b = np.float32([kp[x.trainIdx].pt for x in m])
                M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                if M is not None and inl is not None and inl.sum() >= 10:
                    s = math.hypot(M[0, 0], M[1, 0])
                    # translation of the frame centre (so zoom about the centre is not read as a pan)
                    cx, cy = w / 2, h / 2
                    tx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2] - cx
                    ty = M[1, 0] * cx + M[1, 1] * cy + M[1, 2] - cy
                    mot = (s, tx / w, ty / h, math.degrees(math.atan2(M[1, 0], M[0, 0])), float(inl.mean()))
        F["motion"].append(mot)   # transform from frame t-STRIDE to t
        ring.append((kp, des))
        if len(ring) > STRIDE:
            ring.pop(0)
    out = {k: np.array(v) for k, v in F.items() if k != "motion"}
    out["motion"] = F["motion"]
    out["size"] = (w, h)
    return out


def hdist(a: np.ndarray, b: np.ndarray) -> float:
    """Bhattacharyya distance between two normalised histograms (0 same … 1 disjoint)."""
    return float(np.sqrt(max(0.0, 1 - np.sum(np.sqrt(a * b)))))


# ------------------------------------------------------------------ transitions


def detect_transitions(F: dict, fps: float) -> list[dict]:
    n = len(F["luma"])
    H = F["hist"]
    d1 = np.zeros(n)
    for t in range(1, n):
        d1[t] = hdist(H[t - 1], H[t])
    lum_raw = F["luma"]
    lum = np.convolve(np.pad(lum_raw, 2, mode="edge"), np.ones(5) / 5, mode="valid")  # flicker-robust ramps
    used = np.zeros(n, bool)
    events: list[dict] = []

    # 1) black / white runs → fade in/out, dip, flash
    for kind, mask in (("black", (lum_raw < 0.035) & (F["lstd"] < 0.03)), ("white", (lum_raw > 0.93) & (F["lstd"] < 0.05))):
        t = 0
        while t < n:
            if not mask[t]:
                t += 1
                continue
            a = t
            while t < n and mask[t]:
                t += 1
            b = t - 1  # run [a, b]
            core = lum_raw[a:b + 1]
            ext = float(core.min()) if kind == "black" else float(core.max())
            inner = np.where(np.abs(core - ext) <= 0.012)[0]   # the fully black/white core inside the run
            ra, rb = a + int(inner[0]), a + int(inner[-1])
            short = (b - a + 1) <= max(4, int(0.15 * fps))
            L = lum_raw if short else lum
            hold = float(np.median(lum_raw[ra:rb + 1]))
            sign = 1 if kind == "black" else -1
            lo_i = max(0, a - int(1.5 * fps)); hi_i = min(n, b + 1 + int(1.5 * fps))
            pre_lvl = float(np.median(lum[lo_i:max(lo_i + 1, a - int(0.5 * fps))])) if a > int(0.5 * fps) else hold
            post_lvl = float(np.median(lum[min(n - 1, b + 1 + int(0.5 * fps)):hi_i])) if b + 1 + int(0.5 * fps) < n else hold
            s = ra
            while s > 0 and ra - s < fps * 3 and sign * (L[s - 1] - L[s]) > -0.001 and \
                    sign * (pre_lvl - L[s - 1]) > 0 and abs(L[s - 1] - hold) < 0.95 * abs(pre_lvl - hold):
                s -= 1
            e = rb
            while e < n - 1 and e - rb < fps * 3 and sign * (L[e + 1] - L[e]) > -0.001 and \
                    sign * (post_lvl - L[e + 1]) > 0 and abs(L[e + 1] - hold) < 0.95 * abs(post_lvl - hold):
                e += 1
            if s == 0 and a == 0:
                typ = "fade_in" if kind == "black" else "fade_in_white"
            elif e >= n - 1:
                typ = "fade_out" if kind == "black" else "fade_out_white"
            elif kind == "white" and (e - s + 1) <= max(8, int(0.3 * fps)):
                typ = "flash"
            else:
                typ = "dip_to_black" if kind == "black" else "dip_to_white"
            before, after = max(0, s - 2), min(n - 1, e + 2)
            events.append({"type": typ, "start": s, "end": e, "hold": [ra, rb],
                           "changes_shot": hdist(H[before], H[after]) > 0.3 if 0 < s and e < n - 1 else True})
            used[max(0, s - 2):min(n, e + 3)] = True

    # 2) hard cuts: histogram jump that stands out from its neighbourhood
    for t in range(1, n):
        if used[t]:
            continue
        win = d1[max(1, t - 8):min(n, t + 9)]
        base = np.median(np.delete(win, np.argmax(win))) if len(win) > 2 else 0
        if d1[t] > max(0.28, 4 * base + 0.08) and d1[t] == win.max():
            # reject single-frame flashes of light: content before and after must differ
            if t + 3 < n and hdist(H[t - 1], H[min(n - 1, t + 3)]) < 0.2:
                continue
            events.append({"type": "cut", "start": t, "end": t})
            used[max(0, t - 1):t + 2] = True

    # 3) dissolves: long-range change without a single big jump, confirmed by a linear-blend fit
    k = max(3, int(round(fps * 0.2)))
    D = np.zeros(n)
    for t in range(k, n - k):
        D[t] = hdist(H[t - k], H[t + k])
    th = F["thumb"].astype(np.float32)
    t = k
    while t < n - k:
        if used[t] or D[t] < 0.3 or D[t] < D[max(0, t - 1)] or D[t] < D[min(n - 1, t + 1)]:
            t += 1
            continue
        res = blend_fit(th, D, used, t, fps)
        if res:
            pa, pb = max(0, res["start"] - 3), min(n - 1, res["end"] + 3)
            if hdist(H[pa], H[pb]) < 0.25:   # same scene on both sides (zoom, light change) — not a dissolve
                res = None
        if res:
            events.append(res)
            used[res["start"]:res["end"] + 1] = True
            t = res["end"] + 1
        else:
            t += 1

    events.sort(key=lambda e: e["start"])
    for e in events:
        e["frames"] = e["end"] - e["start"] + 1 if e["type"] != "cut" else 0
        e["time"] = round(e["start"] / fps, 3)
        e["duration"] = round(e["frames"] / fps, 3)
        mid = (e["start"] + e["end"]) // 2
        lo, hi = max(0, mid - int(fps)), min(n, mid + int(fps))
        ref = np.median(F["sharp"][lo:hi])
        e["blurred"] = bool(e["type"] == "dissolve" and F["sharp"][e["start"]:e["end"] + 1].min() < 0.35 * ref)
    return events


def blend_fit(th: np.ndarray, D: np.ndarray, used: np.ndarray, c: int, fps: float) -> dict | None:
    n = len(th)
    Hh = int(fps * 1.2)
    a, b = c, c
    while a > 0 and c - a < Hh and not used[a - 1]:
        a -= 1
    while b < n - 1 and b - c < Hh and not used[b + 1]:
        b += 1
    A, B = th[a].ravel(), th[b].ravel()
    AB = A - B
    nn = float(AB @ AB)
    if nn < 1e3:
        return None
    alpha = np.array([float((th[t].ravel() - B) @ AB) / nn for t in range(a, b + 1)])
    resid = np.array([np.linalg.norm(th[t].ravel() - B - al * AB) / math.sqrt(nn) for t, al in zip(range(a, b + 1), alpha)])
    inside = np.where((alpha < 0.94) & (alpha > 0.06))[0]
    if len(inside) < 3:
        return None
    # the contiguous run of in-between frames that contains the centre
    ci = c - a
    if not (0.06 < alpha[ci] < 0.94):
        ci = int(inside[np.argmin(np.abs(inside - ci))])
    s = ci
    while s > 0 and 0.06 < alpha[s - 1] < 0.94:
        s -= 1
    e = ci
    while e < len(alpha) - 1 and 0.06 < alpha[e + 1] < 0.94:
        e += 1
    seg = alpha[s:e + 1]
    if len(seg) < 3:
        return None
    from scipy.stats import spearmanr
    rho = spearmanr(np.arange(len(seg)), seg).statistic
    r = float(np.median(resid[s:e + 1]))
    if rho > -0.85 or r > 0.25:
        return None
    return {"type": "dissolve", "start": a + s, "end": a + e, "fit": {"spearman": round(float(rho), 3),
                                                                      "median_residual": round(r, 3)}}


# ------------------------------------------------------------------ shots


def shots_from(events: list[dict], n: int, fps: float) -> list[dict]:
    cuts = []
    for e in events:
        if e["type"] in ("fade_in", "fade_in_white"):
            continue
        if e["type"] in ("fade_out", "fade_out_white"):
            continue
        if e["type"] == "flash" and not e.get("changes_shot", True):
            continue
        cuts.append(e)
    shots, start, tin = [], 0, None
    for e in cuts:
        boundary = e["start"] if e["type"] == "cut" else (e["start"] + e["end"] + 1) // 2
        if boundary - start >= 2:
            shots.append({"start": start, "end": boundary - 1, "in": tin, "out": e})
        start, tin = boundary, e
    shots.append({"start": start, "end": n - 1, "in": tin, "out": None})
    for i, s in enumerate(shots, 1):
        s["index"] = i
    return shots


def camera(F: dict, s: dict, fps: float) -> dict:
    a = s["start"] + (s["in"]["end"] - s["in"]["start"] + 1 if s["in"] and s["in"]["type"] != "cut" else 0) // 2 + 1
    b = s["end"] - ((s["out"]["end"] - s["out"]["start"] + 1) // 2 if s["out"] and s["out"]["type"] != "cut" else 0)
    # non-overlapping steps of STRIDE frames inside [a, b]
    ms = [F["motion"][t] for t in range(a + STRIDE, b + 1, STRIDE) if F["motion"][t] is not None]
    steps = len(range(a + STRIDE, b + 1, STRIDE))
    dur = max(1, steps * STRIDE) / fps
    if steps == 0 or len(ms) < max(2, 0.5 * steps):
        return {"move": "unknown", "reason": "too few tracked features", "tracked_frames": len(ms)}
    sc = np.array([m[0] for m in ms]); tx = np.array([m[1] for m in ms]); ty = np.array([m[2] for m in ms])
    rot = np.array([m[3] for m in ms])
    zoom = float(np.prod(sc)); panx = float(tx.sum()); pany = float(ty.sum()); roll = float(rot.sum())
    kz = max(1, min(9, len(tx) // 2 * 2 - 1))
    sm = lambda v: np.convolve(v, np.ones(kz) / kz, mode="same")  # noqa: E731
    jitter = float(np.std(tx - sm(tx)) + np.std(ty - sm(ty)))
    moves = []
    if zoom > 1.03:
        moves.append("push_in")
    elif zoom < 0.97:
        moves.append("pull_out")
    if panx < -0.08:
        moves.append("pan_right")   # content moves left → camera pans right
    elif panx > 0.08:
        moves.append("pan_left")
    if pany > 0.08:
        moves.append("tilt_up")     # content moves down → camera tilts up
    elif pany < -0.08:
        moves.append("tilt_down")
    if abs(roll) > 3:
        moves.append("roll")
    handheld = jitter > 0.006
    return {"move": "+".join(moves) if moves else ("handheld" if handheld else "static"), "handheld": handheld,
            "zoom_total": round(zoom, 4), "zoom_per_s": round(zoom ** (1 / dur), 4),
            "pan_x_frames": round(panx, 4), "pan_y_frames": round(pany, 4), "roll_deg": round(roll, 2),
            "jitter": round(jitter, 5), "tracked_frames": len(ms), "measured_seconds": round(dur, 2)}


def grade(F: dict, s: dict) -> dict:
    a, b = s["start"], s["end"]
    q = slice(a + (b - a) // 4, b - (b - a) // 4 + 1)
    th = F["thumb"][q].reshape(-1, 3).astype(np.float32) / 255
    y = th @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    dark, bright = th[y < np.percentile(y, 25)], th[y > np.percentile(y, 75)]
    split = float((bright[:, 0] - bright[:, 2]).mean() - (dark[:, 0] - dark[:, 2]).mean()) if len(dark) and len(bright) else 0
    from scipy.cluster.vq import kmeans2
    pal = []
    try:
        cent, lab = kmeans2(th[:: max(1, len(th) // 4000)], 4, seed=1, minit="++")
        cnt = np.bincount(lab, minlength=4)
        for i in np.argsort(-cnt):
            c = np.clip(cent[i] * 255, 0, 255).astype(int)
            pal.append({"hex": "#%02x%02x%02x" % tuple(c), "share": round(float(cnt[i] / cnt.sum()), 3)})
    except Exception:
        pass
    import cv2
    lab = cv2.cvtColor((F["thumb"][q].reshape(-1, 1, 3)).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    lab_stats = {"mean": [round(float(v), 2) for v in lab.mean(axis=0)], "std": [round(float(v), 2) for v in lab.std(axis=0)]}
    L = float(F["luma"][q].mean())
    g = {"lab": lab_stats, "luma": round(L, 3), "contrast": round(float(F["lstd"][q].mean()), 3), "black": round(float(F["p2"][q].mean()), 3),
         "white": round(float(F["p98"][q].mean()), 3), "saturation": round(float(F["sat"][q].mean()), 3),
         "warmth": round(float(F["warm"][q].mean()), 4), "tint": round(float(F["tint"][q].mean()), 4),
         "split_tone": round(split, 4), "palette": pal}
    labels = ["low-key" if L < 0.28 else ("high-key" if L > 0.6 else "mid-key")]
    if g["warmth"] > 0.04:
        labels.append("warm")
    elif g["warmth"] < -0.03:
        labels.append("cool")
    if g["saturation"] < 0.18:
        labels.append("desaturated")
    elif g["saturation"] > 0.5:
        labels.append("saturated")
    if split > 0.08:
        labels.append("split-tone (warm highlights / cool shadows)")
    if g["contrast"] > 0.27:
        labels.append("high-contrast")
    elif g["contrast"] < 0.12:
        labels.append("flat/soft")
    g["labels"] = labels
    return g


# ------------------------------------------------------------------ OCR


def _tess(img_path: str, lang: str) -> list[dict]:
    import os
    tsv = subprocess.run(["tesseract", img_path, "stdout", "-l", lang, "--psm", "11", "tsv"], capture_output=True, text=True,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout
    out = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        x, y, w, h = map(int, c[6:10])
        out.append({"text": c[11].strip(), "conf": float(c[10]), "box": [x, y, x + w, y + h]})
    return out


def _letters(t: str) -> int:
    return len(re.findall(r"[A-Za-z\u0C00-\u0C7F]", t))


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def ocr_frame(png: Path, langs: list[str], tmp: Path) -> list[dict]:
    """Words on one frame. Three passes, best reading per word box: the plain frame (all languages), and the bright
    pixels only (white titles/subtitles → black on white) once per language, so Latin and Telugu models don't compete."""
    import cv2
    g = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    bright = tmp / (png.stem + "-bright.png")
    mask = g > 200
    words = _tess(str(png), "+".join(langs))
    if 0.0005 < mask.mean() < 0.3:   # some bright (white-text-like) pixels, not a bright sky
        cv2.imwrite(str(bright), 255 - (mask.astype(np.uint8) * 255))
        for lg in langs:
            words += _tess(str(bright), lg)
    words = [w for w in words if w["conf"] >= 60 and _letters(w["text"]) >= 2 and _letters(w["text"]) >= 0.6 * len(w["text"])]
    best: list[dict] = []
    for w in sorted(words, key=lambda w: -w["conf"]):
        if all(_iou(w["box"], b["box"]) < 0.3 for b in best):
            best.append(w)
    # Tesseract's Telugu model reports lower confidences than its English one
    best = [w for w in best if w["conf"] >= (70 if re.search(r"[\u0C00-\u0C7F]", w["text"]) else 80)]
    # words → lines (similar vertical centre, small horizontal gap)
    lines: list[dict] = []
    for w in sorted(best, key=lambda w: (w["box"][1], w["box"][0])):
        h = w["box"][3] - w["box"][1]
        cy = (w["box"][1] + w["box"][3]) / 2
        for ln in lines:
            lh = ln["box"][3] - ln["box"][1]
            if abs(cy - (ln["box"][1] + ln["box"][3]) / 2) < 0.7 * max(h, lh) and w["box"][0] - ln["box"][2] < 5 * max(h, lh) \
                    and w["box"][2] > ln["box"][0]:
                ln["words"].append(w)
                ln["box"] = [min(ln["box"][0], w["box"][0]), min(ln["box"][1], w["box"][1]),
                             max(ln["box"][2], w["box"][2]), max(ln["box"][3], w["box"][3])]
                break
        else:
            lines.append({"words": [w], "box": list(w["box"])})
    for ln in lines:
        lg = "tel" if any(re.search(r"[\u0C00-\u0C7F]", w["text"]) for w in ln["words"]) else "eng"
        if lg in langs or len(langs) == 1:
            ln["words"] += _line_reocr(g, ln, lg if lg in langs else langs[0], tmp / (png.stem + "-line.png"))
        best_l: list[dict] = []
        for w in sorted(ln["words"], key=lambda w: -w["conf"]):
            if all(_iou(w["box"], b["box"]) < 0.3 for b in best_l):
                best_l.append(w)
        ln["words"] = sorted(best_l, key=lambda w: w["box"][0])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
        ln["conf"] = float(np.mean([w["conf"] for w in ln["words"]]))
    return lines


def _line_reocr(g: np.ndarray, ln: dict, lang: str, out_png: Path) -> list[dict]:
    """Re-read one text line: crop the band of bright pixels around it, upscale 2x, Tesseract single-line mode.
    Recovers words the sparse-text pass missed (e.g. the middle word of a title)."""
    import cv2
    H, W = g.shape
    x0, y0, x1, y1 = ln["box"]
    h = max(1, y1 - y0)
    a, b = max(0, int(y0 - 0.35 * h)), min(H, int(y1 + 0.35 * h))
    band = g[a:b] > 200
    cols = np.where(band.sum(axis=0) > 0)[0]
    xs = cols[(cols > x0 - 4 * h) & (cols < x1 + 4 * h)]
    if not len(xs):
        return []
    cx0, cx1 = max(0, int(xs.min() - 0.3 * h)), min(W, int(xs.max() + 0.3 * h))
    crop = 255 - (band[:, cx0:cx1].astype(np.uint8) * 255)
    crop = cv2.resize(cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255), None, fx=2, fy=2,
                      interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(out_png), crop)
    import os
    tsv = subprocess.run(["tesseract", str(out_png), "stdout", "-l", lang, "--psm", "7", "tsv"], capture_output=True, text=True,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout
    out = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        conf = float(c[10]); txt = c[11].strip().replace("\u200c", "")
        if conf < (70 if lang == "tel" else 80) or _letters(txt) < 2 or _letters(txt) < 0.6 * len(txt):
            continue
        x, y, w, hh = map(int, c[6:10])
        # back to frame coordinates (crop was padded by 20 px and scaled 2x)
        fx0 = cx0 + (x / 2 - 20); fy0 = a + (y / 2 - 20)
        out.append({"text": txt, "conf": conf, "box": [int(fx0), int(fy0), int(fx0 + w / 2), int(fy0 + hh / 2)]})
    return out


def ocr(path: Path, info: dict, step: float, lang: str, F: dict) -> list[dict]:
    import tempfile
    W = min(1600, info["width"])
    H = int(round(info["height"] * W / info["width"] / 2)) * 2
    samples = []
    langs = lang.split("+")
    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps=1/{step},scale={W}:{H}",
                        f"{td}/f%06d.png"], check=True)
        pngs = sorted(Path(td).glob("f*.png"))
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(lambda q: ocr_frame(q, langs, Path(td)), pngs))
        for i, lines in enumerate(results):
            t = (i + 0.5) * step  # ffmpeg's fps filter takes the frame nearest the middle of each interval
            for ln in lines:
                if _letters(ln["text"]) >= 3 or any(re.search(r"[\u0C00-\u0C7F]", w["text"]) for w in ln["words"]):
                    b = ln["box"]
                    samples.append({"t": round(t, 3), "text": ln["text"], "box": [b[0] / W, b[1] / H, b[2] / W, b[3] / H],
                                    "conf": round(ln["conf"], 1),
                                    "words": [{"text": w["text"], "conf": w["conf"], "cx": (w["box"][0] + w["box"][2]) / 2 / W,
                                               "h": (w["box"][3] - w["box"][1]) / H} for w in ln["words"]]})
    # group lines into text events by SCREEN REGION over time (OCR wording varies frame to frame), then vote each
    # word position's reading across all observations
    events: list[dict] = []
    for smp in samples:
        hit = None
        for ev in events:
            if smp["t"] - ev["last"] > step * 2.1:
                continue
            ey0, ey1, sy0, sy1 = ev["box"][1], ev["box"][3], smp["box"][1], smp["box"][3]
            yov = max(0.0, min(ey1, sy1) - max(ey0, sy0)) / max(1e-6, min(ey1 - ey0, sy1 - sy0))
            xov = min(ev["box"][2], smp["box"][2]) > max(ev["box"][0], smp["box"][0])
            if yov > 0.5 and xov:
                hit = ev
                break
        if hit:
            hit["last"] = smp["t"]; hit["n"] += 1
            hit["box"] = [min(hit["box"][0], smp["box"][0]), min(hit["box"][1], smp["box"][1]),
                          max(hit["box"][2], smp["box"][2]), max(hit["box"][3], smp["box"][3])]
            hit["obs"] += smp["words"]
        else:
            events.append({"first": smp["t"], "last": smp["t"], "n": 1, "box": list(smp["box"]), "obs": list(smp["words"])})
    for ev in events:
        # cluster word observations by horizontal centre; per cluster keep the reading with the highest summed confidence
        obs = sorted(ev["obs"], key=lambda w: w["cx"])
        clusters: list[list[dict]] = []
        for w in obs:
            if clusters and abs(w["cx"] - np.mean([o["cx"] for o in clusters[-1]])) < 0.6 * max(w["h"], 0.01) + 0.01:
                clusters[-1].append(w)
            else:
                clusters.append([w])
        words, confs = [], []
        for c in clusters:
            votes: dict = {}
            for o in c:
                votes[o["text"]] = votes.get(o["text"], 0) + o["conf"]
            best = max(votes, key=votes.get)
            if votes[best] >= 80 or len(c) >= 2:
                words.append(best); confs.append(max(o["conf"] for o in c if o["text"] == best))
        ev["text"] = " ".join(words)
        ev["conf"] = round(float(np.mean(confs)), 1) if confs else 0.0
    fps = info["fps"]
    out = []
    events = [ev for ev in events if ev["text"] and (ev["n"] >= 2 or ev["conf"] >= 92)]
    for k, ev in enumerate(events, 1):
        x0, y0, x1, y1 = ev["box"]
        cy, cx, hgt = (y0 + y1) / 2, (x0 + x1) / 2, y1 - y0
        pos = "top" if cy < 0.25 else ("centre" if cy < 0.62 else ("lower-third" if cy < 0.85 else "bottom"))
        start, end, anim = refine_text_times(F, ev, fps, step)
        script = "telugu" if re.search(r"[\u0C00-\u0C7F]", ev["text"]) else "latin"
        out.append({"id": f"text{k:02d}", "text": ev["text"], "start": start, "end": end, "position": pos,
                    "align": "left" if cx < 0.4 else ("right" if cx > 0.6 else "centre"),
                    "height_frac": round(hgt, 3), "box": [round(v, 3) for v in ev["box"]], "script": script,
                    "ocr_conf": ev["conf"], "samples": ev["n"], "entrance": anim,
                    "note": "OCR reading — confirm the wording on the still (text/<id>.jpg)"})
    return out


def refine_text_times(F: dict, ev: dict, fps: float, step: float) -> tuple[float, float, dict]:
    """Refine start/end to frames using the edge density inside the text box, and classify the entrance."""
    E = F["edge"].astype(np.float32)
    n = len(E)
    x0, y0, x1, y1 = ev["box"]
    gx0, gx1 = int(x0 * 32), max(int(x0 * 32) + 1, int(math.ceil(x1 * 32)))
    gy0, gy1 = int(y0 * 18), max(int(y0 * 18) + 1, int(math.ceil(y1 * 18)))
    dens = E[:, gy0:gy1, gx0:gx1].mean(axis=(1, 2))
    f0 = int(ev["first"] * fps)
    f1 = min(n - 1, int(ev["last"] * fps))
    on = float(np.median(dens[f0:f1 + 1])) if f1 >= f0 else float(dens[min(f0, n - 1)])
    lo = max(0, f0 - int(step * fps * 1.5))
    off_lvl = float(np.median(dens[lo:max(lo + 1, f0 - int(step * fps * 0.5))])) if f0 > lo else 0.0
    half = off_lvl + 0.5 * (on - off_lvl)
    s = f0
    while s > lo and dens[s - 1] > half:
        s -= 1
    e = f1
    hi = min(n - 1, f1 + int(step * fps * 1.5))
    while e < hi and dens[e + 1] > half:
        e += 1
    # entrance: frames from 10 % to 90 % of the on-level
    r10, r90 = off_lvl + 0.1 * (on - off_lvl), off_lvl + 0.9 * (on - off_lvl)
    a = s
    while a > lo and dens[a - 1] > r10:
        a -= 1
    b = s
    while b < f1 and dens[b] < r90:
        b += 1
    ramp = (b - a) / fps
    anim = {"style": "cut-in" if ramp <= 2.5 / fps else "fade/blur-in", "ramp_s": round(ramp, 3)}
    return round(a / fps, 3), round((e + 1) / fps, 3), anim


# ------------------------------------------------------------------ audio


def audio_analysis(path: Path, out: Path, transitions: list[dict], asr: str, asr_lang: str | None) -> dict:
    wav = out / "audio16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-ar", "22050", str(out / "audio22k.wav")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-ar", "16000", str(wav)], check=True)
    import librosa
    y, sr = librosa.load(str(out / "audio22k.wav"), sr=22050)
    res: dict = {}
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    try:
        res["loudness"] = {"integrated_lufs": float(summ.split("I:")[1].split("LUFS")[0]),
                           "lra": float(summ.split("LRA:")[1].split("LU")[0]),
                           "true_peak_dbfs": float(summ.split("Peak:")[1].split("dBFS")[0])}
    except Exception:
        res["loudness"] = None
    sil = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "silencedetect=n=-45dB:d=0.4", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", sil)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", sil)]
    res["silences"] = [{"start": round(a, 2), "end": round(b, 2)} for a, b in zip(st, en)]
    # speech
    speech = []
    if asr != "none":
        import whisper
        m = whisper.load_model(asr)
        r = m.transcribe(str(wav), language=asr_lang, word_timestamps=True, fp16=False, condition_on_previous_text=False)
        for sgm in r["segments"]:
            if sgm.get("no_speech_prob", 0) > 0.6 or sgm.get("avg_logprob", 0) < -1.2:
                continue
            speech.append({"start": round(sgm["start"], 2), "end": round(sgm["end"], 2), "text": sgm["text"].strip(),
                           "words": [{"w": w["word"].strip(), "s": round(w["start"], 2), "e": round(w["end"], 2)} for w in sgm.get("words", [])]})
        res["language"] = r.get("language")
    res["speech"] = speech
    sp_time = sum(s["end"] - s["start"] for s in speech)
    words = sum(len(s["words"]) for s in speech)
    res["speech_coverage"] = round(sp_time / max(0.1, len(y) / sr), 3)
    res["words_per_minute"] = round(words / (sp_time / 60), 1) if sp_time > 1 else None
    # music
    harm, perc = librosa.effects.hpss(y)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    res["tempo_bpm"] = round(tempo, 1)
    res["beats"] = [round(float(b), 3) for b in beats]
    cut_times = [e["time"] + (e["duration"] / 2 if e["type"] != "cut" else 0) for e in transitions]
    if len(beats) > 4 and cut_times:
        d = [min(abs(c - b) for b in beats) for c in cut_times]
        res["cuts_on_beat"] = round(sum(x <= 0.07 for x in d) / len(d), 3)
        res["cuts_on_beat_chance"] = round(min(1.0, 0.14 / (60 / max(tempo, 1))), 3)
    # level of music/ambience under speech vs in gaps
    hop = 512
    rms = librosa.feature.rms(y=harm, hop_length=hop)[0]
    tt = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    insp = np.zeros(len(rms), bool)
    for s in speech:
        insp |= (tt >= s["start"]) & (tt <= s["end"])
    if insp.any() and (~insp).any():
        res["bed_db_gaps"] = round(float(20 * np.log10(np.median(rms[~insp]) + 1e-9)), 1)
    # audio events at transitions: percussive hit or rising noise (whoosh) within ±0.25 s
    onset = librosa.onset.onset_strength(y=perc, sr=sr, hop_length=hop)
    ot = librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=hop)
    flat = librosa.feature.spectral_flatness(y=y, hop_length=hop)[0]
    rms_all = librosa.feature.rms(y=y, hop_length=hop)[0]
    thr = np.percentile(onset, 98)
    for e, c in zip(transitions, cut_times):
        w = (ot >= c - 0.25) & (ot <= c + 0.25)
        pre = (ot >= c - 0.6) & (ot <= c)
        ev = None
        if w.any() and onset[w].max() >= thr:
            tp = float(ot[w][np.argmax(onset[w])])
            if not len(beats) or min(abs(tp - b) for b in beats) > 0.05:   # not just a beat of the music
                ev = "hit"
        if pre.sum() > 4 and np.mean(flat[pre]) > 0.2 and rms_all[pre][-3:].mean() > 2 * rms_all[pre][:3].mean() + 1e-4:
            ev = "whoosh" if ev is None else "whoosh+hit"
        e["audio_event"] = ev
    return res


# ------------------------------------------------------------------ report


def atmosphere(shots: list[dict], trans: list[dict], audio: dict | None, dur: float) -> dict:
    asl = float(np.mean([s["duration"] for s in shots]))
    kinds = {}
    for t in trans:
        kinds[t["type"]] = kinds.get(t["type"], 0) + 1
    moving = sum(1 for s in shots if s["camera"]["move"] not in ("static", "unknown")) / len(shots)
    lum = float(np.mean([s["grade"]["luma"] for s in shots]))
    warm = float(np.mean([s["grade"]["warmth"] for s in shots]))
    labels = ["contemplative / slow" if asl > 4 else ("measured" if asl > 2 else "fast / energetic"),
              "dark, low-key" if lum < 0.3 else ("bright, airy" if lum > 0.55 else "natural exposure"),
              "warm" if warm > 0.03 else ("cool" if warm < -0.02 else "neutral colour"),
              "mostly moving camera" if moving > 0.6 else ("mixed camera" if moving > 0.25 else "mostly locked-off")]
    if audio and audio.get("tempo_bpm"):
        labels.append(f"music ≈ {audio['tempo_bpm']:.0f} BPM")
    return {"derived": True, "average_shot_length_s": round(asl, 2), "cuts_per_minute": round(len(trans) / dur * 60, 1),
            "transition_mix": kinds, "moving_camera_share": round(moving, 2), "labels": labels}


def tc(t: float, fps: float) -> str:
    f = int(round(t * fps))
    s, fr = divmod(f, int(round(fps)))
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}:{fr:02d}"


def write_md(bd: dict, path: Path) -> None:
    fps = bd["source"]["fps"]
    L = [f"# Reference breakdown — {Path(bd['source']['file']).name}", "",
         f"{bd['source']['width']}×{bd['source']['height']} @ {fps:.3f} fps, {bd['source']['duration']:.2f} s, "
         f"{len(bd['shots'])} shots, {len(bd['transitions'])} transitions.", "",
         "## Shots", "", "| # | In | Out | Dur | Transition in | Camera | Grade | Text |", "|---|---|---|---|---|---|---|---|"]
    for s in bd["shots"]:
        tin = s["transition_in"]
        tins = "—" if not tin else (tin["type"] + (f" {tin['frames']}f" if tin["frames"] else "") + (" (blur)" if tin.get("blurred") else "")
                                    + (f" + {tin['audio_event']}" if tin.get("audio_event") else ""))
        cam = s["camera"]
        cams = cam["move"] + (f" zoom {100 * (cam['zoom_total'] - 1):+.0f}%" if "zoom_total" in cam and abs(cam["zoom_total"] - 1) > 0.02 else "")
        txt = "; ".join(f"“{t['text'][:40]}” ({t['position']}, {t['entrance']['style']})" for t in s["text"]) or ""
        L.append(f"| {s['index']} | {tc(s['start_s'], fps)} | {tc(s['end_s'], fps)} | {s['duration']:.2f}s | {tins} | {cams} | "
                 f"{', '.join(s['grade']['labels'])} (Y {s['grade']['luma']:.2f}, sat {s['grade']['saturation']:.2f}) | {txt} |")
    a = bd.get("audio") or {}
    L += ["", "## Audio", ""]
    if a:
        L.append(f"- Loudness: {a.get('loudness')}")
        L.append(f"- Tempo: {a.get('tempo_bpm')} BPM; cuts on beat: {a.get('cuts_on_beat')} (chance ≈ {a.get('cuts_on_beat_chance')})")
        L.append(f"- Speech coverage: {a.get('speech_coverage')}; words/min: {a.get('words_per_minute')}; language: {a.get('language')}")
        for s in a.get("speech", []):
            L.append(f"  - {tc(s['start'], fps)}–{tc(s['end'], fps)} {s['text']}")
    L += ["", "## Text on screen", ""]
    for t in bd["text"]:
        L.append(f"- {tc(t['start'], fps)}–{tc(t['end'], fps)} “{t['text']}” — {t['position']}/{t['align']}, height "
                 f"{100 * t['height_frac']:.1f}% of frame, {t['script']}, {t['entrance']['style']} ({t['entrance']['ramp_s']} s)")
    at = bd["atmosphere"]
    L += ["", "## Atmosphere (derived from the measurements above)", "", "- " + "; ".join(at["labels"]),
          f"- Average shot length {at['average_shot_length_s']} s, {at['cuts_per_minute']} transitions/min, mix {at['transition_mix']}",
          f"- Letterbox: {bd['letterbox']}"]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def contact(path: Path, out: Path, shots: list[dict], info: dict) -> None:
    from PIL import Image, ImageDraw
    (out / "shots").mkdir(exist_ok=True)
    thumbs = []
    for s in shots:
        t = (s["start_s"] + s["end_s"]) / 2
        p = out / "shots" / f"{s['index']:03d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=480:-2", str(p)], check=True)
        s["still"] = str(p)
        im = Image.open(p).convert("RGB")
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 150, 26], fill=(0, 0, 0))
        d.text((6, 6), f"#{s['index']} {s['duration']:.1f}s {s['camera']['move'][:10]}", fill=(255, 255, 255))
        thumbs.append(im)
    if not thumbs:
        return
    cols = 6
    w, h = thumbs[0].size
    sheet = Image.new("RGB", (cols * w, math.ceil(len(thumbs) / cols) * h), (0, 0, 0))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    sheet.save(out / "contact.jpg", quality=88)


def text_stills(path: Path, out: Path, texts: list[dict], info: dict) -> None:
    """One frame per text event with the OCR box drawn, for visual confirmation of the wording."""
    from PIL import Image, ImageDraw
    (out / "text").mkdir(exist_ok=True)
    for t in texts:
        p = out / "text" / f"{t['id']}.jpg"
        mid = t["start"] + 0.6 * (t["end"] - t["start"])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=1280:-2", str(p)],
                       check=True)
        im = Image.open(p).convert("RGB")
        W, H = im.size
        b = t["box"]
        ImageDraw.Draw(im).rectangle([b[0] * W - 6, b[1] * H - 6, b[2] * W + 6, b[3] * H + 6], outline=(255, 64, 64), width=3)
        im.save(p, quality=90)
        t["still"] = str(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path); ap.add_argument("out", type=Path)
    ap.add_argument("--ocr-step", type=float, default=0.5); ap.add_argument("--ocr-lang", default="eng+tel")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--asr", default="small", help="Whisper model for speech (none to skip)")
    ap.add_argument("--asr-lang", default=None)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    info = probe(a.video)
    F = analyse_frames(a.video, info)
    n = len(F["luma"])
    fps = info["fps"]
    trans = detect_transitions(F, fps)
    shots = shots_from(trans, n, fps)
    texts = [] if a.no_ocr else ocr(a.video, info, a.ocr_step, a.ocr_lang, F)
    audio = audio_analysis(a.video, a.out, trans, a.asr, a.asr_lang) if info["has_audio"] else None
    bt = float(np.median(F["bars_top"])); bb = float(np.median(F["bars_bot"]))
    out_shots = []
    for s in shots:
        rec = {"index": s["index"], "start_frame": s["start"], "end_frame": s["end"], "start_s": round(s["start"] / fps, 3),
               "end_s": round((s["end"] + 1) / fps, 3), "duration": round((s["end"] - s["start"] + 1) / fps, 3),
               "transition_in": s["in"], "transition_out": s["out"], "camera": camera(F, s, fps), "grade": grade(F, s)}
        rec["text"] = [t for t in texts if t["start"] < rec["end_s"] and t["end"] > rec["start_s"]]
        if audio:
            rec["speech"] = " ".join(x["text"] for x in audio["speech"] if x["start"] < rec["end_s"] and x["end"] > rec["start_s"])
        out_shots.append(rec)
    contact(a.video, a.out, out_shots, info)
    text_stills(a.video, a.out, texts, info)
    bd = {"source": {"file": str(a.video.resolve()), **info, "frames_analysed": n}, "transitions": trans, "shots": out_shots,
          "text": texts, "audio": audio,
          "letterbox": {"top": round(bt, 3), "bottom": round(bb, 3), "present": bool(bt > 0.04 and bb > 0.04),
                        "aspect": round(info["width"] / (info["height"] * (1 - bt - bb)), 2) if bt > 0.04 and bb > 0.04 else None},
          "seconds": round(time.time() - t0, 1)}
    bd["atmosphere"] = atmosphere(out_shots, trans, audio, info["duration"])
    (a.out / "breakdown.json").write_text(json.dumps(bd, ensure_ascii=False, indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    write_md(bd, a.out / "BREAKDOWN.md")
    print(f"[breakdown] {len(out_shots)} shots, {len(trans)} transitions, {len(texts)} text events in {bd['seconds']} s → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
