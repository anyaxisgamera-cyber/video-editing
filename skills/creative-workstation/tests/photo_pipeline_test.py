#!/usr/bin/env python3
"""Quantitative photo-pipeline test on a real frame with known, synthetic damage.

Damage is applied to a clean frame, then restored; PSNR against the clean original must improve.
Also exercises background removal, silhouettes, LUT grading, image→video parallax and the installed
`image-editing` skill (jlouage) for resize/WebP/HEIC export. Usage:

    /opt/cws-venv/bin/python photo_pipeline_test.py CLEAN_FRAME.png OUT_DIR [LUT.cube]
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "scripts" / "photo_tools.py"
IMAGE_EDIT = Path.home() / ".claude/skills/image-editing/scripts/image_edit.py"
PY = sys.executable


def psnr(a: np.ndarray, b: np.ndarray, region=None) -> float:
    if region:
        x, y, w, h = region
        a, b = a[y:y + h, x:x + w], b[y:y + h, x:x + w]
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def tool(*args):
    out = subprocess.run([PY, str(TOOLS), *map(str, args)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def main() -> int:
    clean_p, out = Path(sys.argv[1]), Path(sys.argv[2])
    lut = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    out.mkdir(parents=True, exist_ok=True)
    clean = np.asarray(Image.open(clean_p).convert("RGB"))
    H, W = clean.shape[:2]
    rng = np.random.default_rng(0)
    res = {"input": str(clean_p), "size": [W, H]}

    # 1a. blind restoration (no reference): noise + colour cast + lifted/flattened tones
    deg = clean.astype(np.float32) * [1.12, 0.95, 0.80] * 0.8 + 18
    deg = np.clip(deg + rng.normal(0, 12, deg.shape), 0, 255).astype(np.uint8)
    Image.fromarray(deg).save(out / "1-degraded.png")
    tool("enhance", out / "1-degraded.png", out / "1-denoised.png", "--denoise", "7")
    den = np.asarray(Image.open(out / "1-denoised.png").convert("RGB"))
    # 1b. colour correction to a reference (shot matching): the graded hero still is the reference
    tool("enhance", out / "1-degraded.png", out / "1-restored.png", "--denoise", "7", "--match", clean_p)
    rest = np.asarray(Image.open(out / "1-restored.png").convert("RGB"))
    # 1c. stylistic enhancement (not scored as restoration)
    tool("enhance", out / "1-restored.png", out / "1-styled.png", "--clahe", "1.6", "--sharpen", "0.4")
    res["restoration"] = {"psnr_degraded": round(psnr(clean, deg), 2), "psnr_denoised": round(psnr(clean, den), 2),
                          "psnr_denoised_plus_reference_match": round(psnr(clean, rest), 2),
                          "note": "reference = the clean frame (shot-matching scenario); CLAHE/sharpen output 1-styled.png is stylistic"}
    res["restoration"]["improved"] = bool(res["restoration"]["psnr_denoised"] > res["restoration"]["psnr_degraded"]
                                          and res["restoration"]["psnr_denoised_plus_reference_match"] > res["restoration"]["psnr_denoised"])

    # 2. object removal: a stamped "logo" block + a scratch, removed by inpainting with a rect mask
    obj = Image.fromarray(clean.copy())
    d = ImageDraw.Draw(obj)
    box = (int(W * 0.70), int(H * 0.10), int(W * 0.12), int(H * 0.10))
    d.rectangle([box[0], box[1], box[0] + box[2], box[1] + box[3]], fill=(240, 30, 200))
    d.text((box[0] + 10, box[1] + 10), "WATERMARK", fill=(255, 255, 255))
    d.line([(int(W * 0.1), int(H * 0.2)), (int(W * 0.3), int(H * 0.9))], fill=(255, 255, 255), width=4)
    obj.save(out / "2-with-object.png")
    scratch_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(scratch_mask).line([(int(W * 0.1), int(H * 0.2)), (int(W * 0.3), int(H * 0.9))], fill=255, width=4)
    scratch_mask.save(out / "2-scratch-mask.png")
    tool("inpaint", out / "2-with-object.png", out / "2-object-removed.png", "--rect", ",".join(map(str, box)),
         "--mask", out / "2-scratch-mask.png")
    rem = np.asarray(Image.open(out / "2-object-removed.png").convert("RGB"))
    objn = np.asarray(obj)
    res["object_removal"] = {"region": box, "psnr_with_object": round(psnr(clean, objn, box), 2),
                             "psnr_after_removal": round(psnr(clean, rem, box), 2)}
    res["object_removal"]["improved"] = bool(res["object_removal"]["psnr_after_removal"] > res["object_removal"]["psnr_with_object"])

    # 3. background removal + silhouette + transparency check
    r = tool("remove-bg", clean_p, out / "3-cutout.png", "--model", "u2net_human_seg")
    a = np.asarray(Image.open(out / "3-cutout.png").getchannel("A"))
    tool("silhouette", out / "3-cutout.png", out / "3-silhouette.png")
    res["background_removal"] = {**r, "alpha_min": int(a.min()), "alpha_max": int(a.max()), "is_transparent": bool(a.min() < 10 and a.max() > 245)}

    # 4. LUT colour grade of a still (same .cube files as the video grade)
    if lut:
        tool("grade", clean_p, lut, out / "4-graded.png")
        g = np.asarray(Image.open(out / "4-graded.png").convert("RGB")).astype(float)
        res["grade"] = {"lut": lut.name, "mean_rgb_before": [round(v, 1) for v in clean.reshape(-1, 3).mean(0)],
                        "mean_rgb_after": [round(v, 1) for v in g.reshape(-1, 3).mean(0)]}

    # 5. image → video (2.5D parallax)
    r = tool("parallax", clean_p, out / "5-parallax.mp4", "--duration", "4", "--fps", "30", "--size", "1280x720")
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                                    "stream=width,height,nb_read_packets:format=duration", "-of", "json", str(out / "5-parallax.mp4")],
                                   capture_output=True, text=True).stdout)
    res["parallax"] = {**r, "probe": pr}

    # 6. installed image-editing skill (jlouage): resize to web, WebP + HEIC export, info
    uv = shutil.which("uv")
    ie = {}
    for name, extra in (("6-web.webp", ["--width", "960", "--quality", "85"]), ("6-archive.heic", ["--quality", "90"])):
        o = subprocess.run([uv, "run", "-q", str(IMAGE_EDIT), str(out / "1-restored.png"), "-o", str(out / name), *extra],
                           capture_output=True, text=True)
        ie[name] = json.loads(o.stdout) if o.returncode == 0 else {"error": o.stderr[-300:]}
    res["image_editing_skill"] = {k: {kk: v.get(kk) for kk in ("status", "outputDimensions", "fileSize", "error")} for k, v in ie.items()}

    res["passed"] = bool(res["restoration"]["improved"] and res["object_removal"]["improved"]
                         and res["background_removal"]["is_transparent"]
                         and res["parallax"]["probe"]["streams"][0]["nb_read_packets"] == "120"
                         and all(v.get("status") == "complete" for v in ie.values()))
    (out / "photo-test-report.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
