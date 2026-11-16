#!/usr/bin/env python3
"""Photo & graphic production: background removal, silhouettes, restoration/enhancement, object removal,
LUT grading, layered compositing (posters / thumbnails / stories) and image-to-video parallax.

Complements the installed `image-editing` skill (jlouage: resize/convert/HEIC/watermark/batch), which this
tool calls for nothing — they chain via files. Run with the workstation venv (/opt/cws-venv/bin/python).

    photo_tools.py extract-frame VIDEO --at 4.2 OUT.png
    photo_tools.py remove-bg IN OUT.png [--model u2net|isnet-general-use|u2net_human_seg] [--matting]
    photo_tools.py silhouette CUTOUT.png OUT.png [--color #140A2A] [--rim #BBA4F2]
    photo_tools.py enhance IN OUT [--denoise 6] [--match REF.png] [--clahe 2.0] [--sharpen 0.8] [--wb] [--upscale 2]
    photo_tools.py inpaint IN OUT --rect x,y,w,h [--rect ...] | --mask MASK.png      # object removal
    photo_tools.py grade IN LUT.cube OUT
    photo_tools.py compose SPEC.json OUT.png                                         # posters/thumbnails
    photo_tools.py parallax IN OUT.mp4 [--duration 6] [--fps 30] [--size 1920x1080]  # image → video
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("/home/user/creative-studio/media-library/fonts")
PRESETS = {"poster": (1080, 1350), "thumbnail": (1280, 720), "story": (1080, 1920), "square": (1080, 1080),
           "hd": (1920, 1080), "4k": (3840, 2160)}


def rgba(c: str, a: int | None = None):
    v = ImageColor.getrgb(c)
    return (*v[:3], a if a is not None else (v[3] if len(v) == 4 else 255))


# ------------------------------------------------------------------ cutouts


def extract_frame(video: Path, at: float, out: Path):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(at), "-i", str(video),
                    "-frames:v", "1", str(out)], check=True)
    return out


def remove_bg(src: Path, out: Path, model: str = "u2net", matting: bool = False) -> dict:
    from rembg import new_session, remove
    sess = new_session(model)
    im = Image.open(src).convert("RGB")
    cut = remove(im, session=sess, alpha_matting=matting, alpha_matting_foreground_threshold=240,
                 alpha_matting_background_threshold=12, alpha_matting_erode_size=8)
    bbox = cut.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox:
        cut = cut.crop(bbox)
    cut.save(out)
    a = np.asarray(cut.getchannel("A"))
    return {"out": str(out), "model": model, "size": cut.size, "opaque_fraction": round(float((a > 128).mean()), 3),
            "transparent_fraction": round(float((a < 8).mean()), 3)}


def silhouette(cutout: Path, out: Path, color: str = "#140A2A", rim: str | None = "#BBA4F2") -> dict:
    im = Image.open(cutout).convert("RGBA")
    alpha = im.getchannel("A")
    solid = Image.new("RGBA", im.size, rgba(color))
    solid.putalpha(alpha)
    if rim:
        pad = 40
        canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
        glow_a = Image.new("L", canvas.size, 0)
        glow_a.paste(alpha, (pad, pad))
        edge = ImageChops.subtract(glow_a.filter(ImageFilter.MaxFilter(5)), glow_a).filter(ImageFilter.GaussianBlur(6))
        glow = Image.new("RGBA", canvas.size, rgba(rim))
        glow.putalpha(edge.point(lambda v: min(255, v * 3)))
        canvas.alpha_composite(glow)
        canvas.alpha_composite(solid, (pad, pad))
        solid = canvas
    solid.save(out)
    return {"out": str(out), "size": solid.size}


# ------------------------------------------------------------------ restoration / enhancement


def color_match(bgr: np.ndarray, ref_path: Path) -> np.ndarray:
    """Reinhard colour transfer in LAB: match per-channel mean/std to a reference image (shot matching)."""
    import cv2
    ref = cv2.imread(str(ref_path))
    src_lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    ref_lab = cv2.cvtColor(ref, cv2.COLOR_BGR2LAB).astype(np.float32)
    for c in range(3):
        m, s = src_lab[..., c].mean(), src_lab[..., c].std() + 1e-6
        rm, rs = ref_lab[..., c].mean(), ref_lab[..., c].std()
        src_lab[..., c] = (src_lab[..., c] - m) / s * rs + rm
    return cv2.cvtColor(np.clip(src_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def enhance(src: Path, out: Path, denoise: float = 0, clahe: float = 0, sharpen: float = 0, wb: bool = False,
            upscale: float = 1.0, match: Path | None = None) -> dict:
    """Restoration (denoise) and correction (match to a reference / gray-world WB) are separate from
    stylistic enhancement (CLAHE local contrast, sharpening). Measured on a real frame with known damage:
    NL-means denoise restores (PSNR 23.2→24.7 dB); reference matching corrects casts; gray-world WB and
    auto-levels can make a deliberately dark/tinted image *worse*, so they are opt-in only."""
    import cv2
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    alpha = img[..., 3] if img.ndim == 3 and img.shape[2] == 4 else None
    bgr = img[..., :3] if alpha is not None else img
    ops = []
    if denoise:
        bgr = cv2.fastNlMeansDenoisingColored(bgr, None, denoise, denoise, 7, 21)
        ops.append(f"NL-means denoise h={denoise}")
    if match:
        bgr = color_match(bgr, match)
        ops.append(f"Reinhard LAB colour match to {Path(match).name}")
    if wb:  # gray-world white balance (assumes the scene averages to neutral — not true for stylised shots)
        f = bgr.astype(np.float32)
        means = f.reshape(-1, 3).mean(0)
        bgr = np.clip(f * (means.mean() / means), 0, 255).astype(np.uint8)
        ops.append("gray-world WB")
    if clahe:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=clahe, tileGridSize=(8, 8)).apply(lab[..., 0])
        bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        ops.append(f"CLAHE {clahe}")
    if upscale and upscale != 1.0:
        bgr = cv2.resize(bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LANCZOS4)
        if alpha is not None:
            alpha = cv2.resize(alpha, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LANCZOS4)
        ops.append(f"Lanczos upscale x{upscale}")
    if sharpen:
        blur = cv2.GaussianBlur(bgr, (0, 0), 1.6)
        bgr = cv2.addWeighted(bgr, 1 + sharpen, blur, -sharpen, 0)
        ops.append(f"unsharp {sharpen}")
    res = np.dstack([bgr, alpha]) if alpha is not None else bgr
    cv2.imwrite(str(out), res)
    return {"out": str(out), "ops": ops, "size": [int(res.shape[1]), int(res.shape[0])]}


def inpaint(src: Path, out: Path, rects: list[str], mask: Path | None = None, radius: int = 9) -> dict:
    import cv2
    img = cv2.imread(str(src))
    m = np.zeros(img.shape[:2], np.uint8)
    if mask:
        m = (cv2.imread(str(mask), cv2.IMREAD_GRAYSCALE) > 127).astype(np.uint8) * 255
    for r in rects:
        x, y, w, h = (int(v) for v in r.split(","))
        m[y:y + h, x:x + w] = 255
    m = cv2.dilate(m, np.ones((7, 7), np.uint8))
    res = cv2.inpaint(img, m, radius, cv2.INPAINT_TELEA)
    cv2.imwrite(str(out), res)
    return {"out": str(out), "masked_pixels": int((m > 0).sum()), "method": "OpenCV Telea inpainting"}


def grade(src: Path, lut: Path, out: Path):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", f"lut3d='{lut}'",
                    str(out)], check=True)
    return {"out": str(out), "lut": lut.name}


# ------------------------------------------------------------------ layered compositing


def font(name: str, size: int):
    p = FONT_DIR / name
    return ImageFont.truetype(str(p if p.exists() else name), size)


def background(spec: dict, size):
    w, h = size
    kind = spec.get("type", "gradient")
    if kind == "image":
        im = Image.open(spec["src"]).convert("RGBA")
        s = max(w / im.width, h / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        return im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width - w) // 2 + w, (im.height - h) // 2 + h))
    inner, outer = np.array(rgba(spec.get("inner", "#F4EFFF"))[:3], np.float32), np.array(rgba(spec.get("outer", "#BBA4F2"))[:3], np.float32)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = spec.get("center", [0.5, 0.42])
    d = np.sqrt(((x / w - cx) * (w / h)) ** 2 + (y / h - cy) ** 2)
    t = np.clip(d / d.max(), 0, 1)[..., None] ** spec.get("power", 1.2)
    arr = inner * (1 - t) + outer * t + np.random.default_rng(1).normal(0, 1.0, (h, w, 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def place_image(canvas: Image.Image, L: dict):
    im = Image.open(L["src"]).convert("RGBA")
    if "height" in L:
        s = L["height"] / im.height
        im = im.resize((max(1, round(im.width * s)), max(1, round(L["height"]))), Image.LANCZOS)
    if L.get("rotate"):
        im = im.rotate(L["rotate"], expand=True, resample=Image.BICUBIC)
    if L.get("opacity", 1) < 1:
        im.putalpha(im.getchannel("A").point(lambda a: round(a * L["opacity"])))
    x, y = L["x"] - im.width * L.get("anchor", [0.5, 0.5])[0], L["y"] - im.height * L.get("anchor", [0.5, 0.5])[1]
    # pad before any blur/glow/shadow so the falloff is not clipped to the tight bounding box (hard rectangles)
    pad = int(3 * max(L.get("blur", 0), L.get("glowBlur", 30) if L.get("glow") else 0,
                      L.get("shadowBlur", 24) if L.get("shadow") else 0)) + 2
    padded = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    padded.paste(im, (pad, pad))
    im, x, y = padded, x - pad, y - pad
    if L.get("blur"):  # blur premultiplied colour so transparent pixels don't bleed dark/light fringes
        im = im.convert("RGBa").filter(ImageFilter.GaussianBlur(L["blur"])).convert("RGBA")
    if L.get("shadow"):
        sh = Image.new("RGBA", im.size, rgba(L.get("shadowColor", "#140A2A")))
        sh.putalpha(im.getchannel("A").point(lambda a: round(a * 0.45)))
        sh = sh.filter(ImageFilter.GaussianBlur(L.get("shadowBlur", 24)))
        canvas.alpha_composite(sh, (round(x + L.get("shadowOffset", [0, 22])[0]), round(y + L.get("shadowOffset", [0, 22])[1])))
    if L.get("glow"):
        g = Image.new("RGBA", im.size, rgba(L["glow"]))
        g.putalpha(im.getchannel("A").filter(ImageFilter.GaussianBlur(L.get("glowBlur", 30))))
        canvas.alpha_composite(g, (round(x), round(y)))
    canvas.alpha_composite(im, (round(x), round(y)))


def place_text(canvas: Image.Image, L: dict):
    f = font(L.get("font", "InstrumentSerif-Regular.ttf"), L["size"])
    tracking = L.get("tracking", 0)
    text = L["text"].upper() if L.get("upper") else L["text"]
    lines = text.split("\n")
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = L["y"]
    lh = L.get("lineHeight", 1.05) * L["size"]
    for line in lines:
        widths = [d.textlength(ch, font=f) + tracking for ch in line]
        total = sum(widths) - (tracking if line else 0)
        align = L.get("align", "center")
        x = L["x"] - (total / 2 if align == "center" else total if align == "right" else 0)
        for ch, wch in zip(line, widths):
            d.text((x, y), ch, font=f, fill=rgba(L.get("color", "#24124A")), anchor="ls")
            x += wch
        y += lh
    if L.get("glow"):
        g = layer.filter(ImageFilter.GaussianBlur(L.get("glowBlur", 18)))
        tint = Image.new("RGBA", canvas.size, rgba(L["glow"]))
        tint.putalpha(g.getchannel("A"))
        canvas.alpha_composite(tint)
    if L.get("blur"):
        layer = layer.filter(ImageFilter.GaussianBlur(L["blur"]))
    canvas.alpha_composite(layer)


def compose(spec_path: Path, out: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    base = spec_path.parent
    size = tuple(spec["size"]) if isinstance(spec.get("size"), list) else PRESETS[spec.get("size", "poster")]
    canvas = background({**spec.get("background", {}),
                         **({"src": str(base / spec["background"]["src"])} if spec.get("background", {}).get("src") else {})}, size)
    for L in spec.get("layers", []):
        L = dict(L)
        if "src" in L:
            L["src"] = str((base / L["src"]).resolve()) if not Path(L["src"]).is_absolute() else L["src"]
        if L["type"] == "image":
            place_image(canvas, L)
        elif L["type"] == "text":
            place_text(canvas, L)
        elif L["type"] == "grid":
            step, col = L.get("step", 72), rgba(L.get("color", "#4B2D8F"), L.get("alpha", 22))
            g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(g)
            for x in range(0, size[0], step):
                d.line([(x, 0), (x, size[1])], fill=col, width=1)
            for y in range(0, size[1], step):
                d.line([(0, y), (size[0], y)], fill=col, width=1)
            canvas.alpha_composite(g)
        elif L["type"] == "rule":
            d = ImageDraw.Draw(canvas)
            d.line([(L["x1"], L["y"]), (L["x2"], L["y"])], fill=rgba(L.get("color", "#24124A")), width=L.get("width", 2))
        elif L["type"] == "vignette":
            v = np.zeros((size[1], size[0]), np.float32)
            yy, xx = np.mgrid[0:size[1], 0:size[0]]
            r = np.sqrt(((xx / size[0]) - 0.5) ** 2 + ((yy / size[1]) - 0.5) ** 2) / 0.7071
            v = (np.clip((r - 0.55) / 0.45, 0, 1) ** 1.5 * L.get("strength", 0.35) * 255).astype(np.uint8)
            vig = Image.new("RGBA", canvas.size, rgba(L.get("color", "#24124A")))
            vig.putalpha(Image.fromarray(v))
            canvas.alpha_composite(vig)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, quality=95) if out.suffix.lower() in (".jpg", ".jpeg") else canvas.save(out)
    return {"out": str(out), "size": size, "layers": len(spec.get("layers", []))}


# ------------------------------------------------------------------ image → video (2.5D parallax)


def parallax(src: Path, out: Path, duration: float = 6.0, fps: int = 30, size: str = "1920x1080",
             model: str = "u2net") -> dict:
    """Split subject (rembg) from background (OpenCV inpaint of the hole), then animate the two layers
    with different zoom/drift → depth. Frames stream to ffmpeg, so memory stays flat."""
    import cv2
    from rembg import new_session, remove
    W, H = (int(v) for v in size.split("x"))
    im = Image.open(src).convert("RGB")
    s = max(W / im.width, H / im.height) * 1.12
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    cut = remove(im, session=new_session(model))
    alpha = np.asarray(cut.getchannel("A"))
    hole = cv2.dilate((alpha > 20).astype(np.uint8) * 255, np.ones((25, 25), np.uint8))
    bg = cv2.inpaint(cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR), hole, 15, cv2.INPAINT_TELEA)
    bg = Image.fromarray(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)).convert("RGBA")
    fg = cut
    n = round(duration * fps)
    proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    for i in range(n):
        t = i / max(1, n - 1)
        e = t * t * (3 - 2 * t)  # smoothstep
        frame = Image.new("RGBA", (W, H))
        for layer, zoom, dx in ((bg, 1.0 + 0.05 * e, -30 * e), (fg, 1.0 + 0.12 * e, 40 * e)):
            lw, lh = round(layer.width * zoom), round(layer.height * zoom)
            L = layer.resize((lw, lh), Image.BILINEAR)
            frame.alpha_composite(L, (round((W - lw) / 2 + dx), round((H - lh) / 2)))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    return {"out": str(out), "frames": n, "fps": fps, "size": [W, H], "subject_fraction": round(float((alpha > 128).mean()), 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("extract-frame"); s.add_argument("video", type=Path); s.add_argument("--at", type=float, default=0); s.add_argument("out", type=Path)
    s = sub.add_parser("remove-bg"); s.add_argument("src", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--model", default="u2net"); s.add_argument("--matting", action="store_true")
    s = sub.add_parser("silhouette"); s.add_argument("cutout", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--color", default="#140A2A"); s.add_argument("--rim", default="#BBA4F2")
    s = sub.add_parser("enhance"); s.add_argument("src", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--denoise", type=float, default=0); s.add_argument("--clahe", type=float, default=0)
    s.add_argument("--sharpen", type=float, default=0); s.add_argument("--wb", action="store_true"); s.add_argument("--upscale", type=float, default=1.0)
    s.add_argument("--match", type=Path, help="reference image for colour matching")
    s = sub.add_parser("inpaint"); s.add_argument("src", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--rect", action="append", default=[]); s.add_argument("--mask", type=Path)
    s = sub.add_parser("grade"); s.add_argument("src", type=Path); s.add_argument("lut", type=Path); s.add_argument("out", type=Path)
    s = sub.add_parser("compose"); s.add_argument("spec", type=Path); s.add_argument("out", type=Path)
    s = sub.add_parser("parallax"); s.add_argument("src", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--duration", type=float, default=6); s.add_argument("--fps", type=int, default=30); s.add_argument("--size", default="1920x1080")
    a = ap.parse_args(argv)
    if a.cmd == "extract-frame":
        r = {"out": str(extract_frame(a.video, a.at, a.out))}
    elif a.cmd == "remove-bg":
        r = remove_bg(a.src, a.out, a.model, a.matting)
    elif a.cmd == "silhouette":
        r = silhouette(a.cutout, a.out, a.color, a.rim or None)
    elif a.cmd == "enhance":
        r = enhance(a.src, a.out, a.denoise, a.clahe, a.sharpen, a.wb, a.upscale, a.match)
    elif a.cmd == "inpaint":
        r = inpaint(a.src, a.out, a.rect, a.mask)
    elif a.cmd == "grade":
        r = grade(a.src, a.lut, a.out)
    elif a.cmd == "compose":
        r = compose(a.spec, a.out)
    else:
        r = parallax(a.src, a.out, a.duration, a.fps, a.size)
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
