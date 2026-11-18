#!/usr/bin/env python3
"""Measure registered visual assets so crops and grades are chosen from evidence, then store it in the register.

    PY analyze_media.py PROD [--ids a01,a02] [--force]

PY needs numpy and opencv-python. For each downloaded image/video in research/source-register.json:
  focus      where the subject is (0..1, 0..1): the centre of detected faces (OpenCV Haar cascade) when present,
             otherwise the weighted centroid of a spectral-residual saliency map — averaged over up to 8 frames
  crop_check whether that subject survives a cover crop to 9:16 and 16:9 (subject box fully inside the crop window)
  exposure   mean luma, clipped highlights/shadows; sharpness (variance of the Laplacian, 640-px copy)
production.py timing uses `analysis.focus` when a scene gives no focus point of its own.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import production as P  # noqa: E402


def frames(path: Path, kind: str, n: int = 8, w: int = 640) -> list[np.ndarray]:
    import cv2
    if kind == "image":
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:  # formats OpenCV cannot read (webp variants, tiff): let ffmpeg decode one frame
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:-2",
                                  "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True).stdout
            facts = P.media_facts(path)
            h = int(round(facts["height"] * w / facts["width"] / 2) * 2)
            return [np.frombuffer(raw, np.uint8).reshape(h, w, 3)] if raw else []
        h = int(round(img.shape[0] * w / img.shape[1]))
        return [cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)]
    facts = P.media_facts(path)
    dur = facts.get("duration") or 1
    h = int(round(facts["height"] * w / facts["width"] / 2) * 2)
    out = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf",
                              f"scale={w}:{h}", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True).stdout
        if len(raw) == w * h * 3:
            out.append(np.frombuffer(raw, np.uint8).reshape(h, w, 3))
    return out


def saliency(gray: np.ndarray) -> np.ndarray:
    """Spectral residual saliency (Hou & Zhang 2007) on a 64-px-high copy."""
    import cv2
    small = cv2.resize(gray, (int(64 * gray.shape[1] / gray.shape[0]), 64)).astype(np.float32)
    f = np.fft.fft2(small)
    logamp = np.log(np.abs(f) + 1e-9)
    residual = logamp - cv2.blur(logamp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * np.angle(f)))) ** 2
    sal = cv2.GaussianBlur(sal, (9, 9), 2.5)
    return cv2.resize(sal / (sal.max() + 1e-9), (gray.shape[1], gray.shape[0]))


def analyse(path: Path, kind: str) -> dict:
    import cv2
    fr = frames(path, kind)
    if not fr:
        return {"error": "could not decode frames"}
    # Haar face detection ships with OpenCV 4; OpenCV 5 builds may omit it — then saliency alone decides
    cascade = None
    if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    pts, boxes, method = [], [], "saliency"
    luma, sharp, clip_hi, clip_lo = [], [], [], []
    for img in fr:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        H, W = g.shape
        luma.append(float(g.mean() / 255)); sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        clip_hi.append(float((g >= 250).mean())); clip_lo.append(float((g <= 5).mean()))
        faces = cascade.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=(int(W * 0.04), int(W * 0.04))) \
            if cascade is not None else []
        if len(faces):
            method = "faces"
            x0 = min(f[0] for f in faces); y0 = min(f[1] for f in faces)
            x1 = max(f[0] + f[2] for f in faces); y1 = max(f[1] + f[3] for f in faces)
            pts.append(((x0 + x1) / 2 / W, (y0 + y1) / 2 / H))
            boxes.append((x0 / W, y0 / H, x1 / W, y1 / H))
        else:
            s = saliency(g)
            m = s > np.percentile(s, 90)
            ys, xs = np.nonzero(m)
            wts = s[m]
            cx, cy = float((xs * wts).sum() / wts.sum() / W), float((ys * wts).sum() / wts.sum() / H)
            pts.append((cx, cy))
            x0, x1 = np.percentile(xs, [10, 90]) / W
            y0, y1 = np.percentile(ys, [10, 90]) / H
            boxes.append((float(x0), float(y0), float(x1), float(y1)))
    fx = float(np.clip(np.median([p[0] for p in pts]), 0.15, 0.85))
    fy = float(np.clip(np.median([p[1] for p in pts]), 0.2, 0.8))
    bx = (float(np.median([b[0] for b in boxes])), float(np.median([b[1] for b in boxes])),
          float(np.median([b[2] for b in boxes])), float(np.median([b[3] for b in boxes])))
    H, W = fr[0].shape[:2]
    crops = {}
    for fmt, (cw, ch) in (("9:16", (9, 16)), ("16:9", (16, 9))):
        # cover crop window in normalized source coordinates, placed like ScriptVideo does (focus-weighted offset)
        s = max(cw / W, ch / H)
        win_w, win_h = cw / s / W, ch / s / H
        left, top = (1 - win_w) * fx, (1 - win_h) * fy
        inside_box = bx[0] >= left - 0.01 and bx[2] <= left + win_w + 0.01 and bx[1] >= top - 0.01 and bx[3] <= top + win_h + 0.01
        crops[fmt] = {"window": [round(left, 3), round(top, 3), round(left + win_w, 3), round(top + win_h, 3)],
                      "subject_inside": bool(inside_box)}
    return {"focus": [round(fx, 3), round(fy, 3)],
            "focus_method": method + ("" if cascade is not None else " (face detection unavailable in this OpenCV build)"), "subject_box": [round(v, 3) for v in bx],
            "crop_check": crops, "mean_luma": round(float(np.mean(luma)), 3), "sharpness": round(float(np.median(sharp)), 1),
            "clipped_highlights": round(float(np.mean(clip_hi)), 4), "crushed_shadows": round(float(np.mean(clip_lo)), 4),
            "frames": len(fr), "analysed_at": P.now()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("production", type=Path); ap.add_argument("--ids"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    prod = a.production.resolve()
    reg = P.load_register(prod)
    ids = set(a.ids.split(",")) if a.ids else None
    n, changed = 0, []
    for e in reg["assets"]:
        if e.get("kind") not in ("image", "video") or e.get("status") not in ("downloaded", "used"):
            continue
        if (ids and e["id"] not in ids) or (e.get("analysis") and not a.force and not ids):
            continue
        res = analyse(prod / e["local_path"], "image" if (e["kind"] == "image" or (e.get("probe") or {}).get("still")) else "video")
        e["analysis"] = res
        changed.append(e)
        n += 1
        cc = res.get("crop_check", {})
        print(f"{e['id']:10} focus={res.get('focus')} via {res.get('focus_method')} | 9:16 subject inside: "
              f"{cc.get('9:16', {}).get('subject_inside')} | luma {res.get('mean_luma')} sharp {res.get('sharpness')}")
    P.save_register_entries(prod, changed)
    print(f"analysed {n} asset(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
