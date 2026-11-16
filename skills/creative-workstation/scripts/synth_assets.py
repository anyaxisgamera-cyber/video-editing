#!/usr/bin/env python3
"""Populate the media library with original and openly-licensed design assets, fully catalogued.

  * backgrounds/   lavender + deep-violet gradients (4K), grid-texture and film-grain overlays (alpha)
  * logos/         ORIGINAL fictional brand marks (SVG + transparent PNG) — safe for any test/promo
  * icons/         Lucide (ISC) UI icons and Simple Icons (CC0) software logos, recoloured to the palette
  * fonts/         SIL OFL display serifs/sans (from the canvas-design skill + Debian EB Garamond)
  * transparent-png/  hero stills pulled from the Blender turntables (true alpha)

    python3 synth_assets.py all --library /path/media-library --vendor /path/node_modules
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import Catalog  # noqa: E402

PALETTE = {
    "lavender-50": "#F4EFFF", "lavender-100": "#E9E0FF", "lavender-200": "#D6C7FB", "lavender-300": "#BBA4F2",
    "violet-500": "#8B6CD9", "violet-700": "#4B2D8F", "violet-900": "#24124A", "ink": "#140A2A",
    "gold": "#E8C98A", "white": "#FFFFFF",
}


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


# ------------------------------------------------------------------ backgrounds


def radial(w, h, inner, outer, cx=0.5, cy=0.42, power=1.25):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x / w - cx) * (w / h)) ** 2 + (y / h - cy) ** 2)
    t = np.clip(d / d.max(), 0, 1) ** power
    img = hex_rgb(inner) * (1 - t[..., None]) + hex_rgb(outer) * t[..., None]
    rng = np.random.default_rng(3)
    img += rng.normal(0, 1.2, img.shape)  # dither: no banding in 8-bit gradients
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def grid_overlay(w, h, step=96, color=(255, 255, 255), alpha=26, dot_alpha=60):
    a = np.zeros((h, w), dtype=np.uint8)
    a[::step, :] = alpha
    a[:, ::step] = alpha
    yy, xx = np.mgrid[0:h:step, 0:w:step]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            a[np.clip(yy + dy, 0, h - 1), np.clip(xx + dx, 0, w - 1)] = dot_alpha
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = a
    return Image.fromarray(rgba, "RGBA")


def grain(size=1024, alpha=20, seed=5):
    rng = np.random.default_rng(seed)
    n = rng.normal(128, 50, (size, size)).clip(0, 255).astype(np.uint8)
    rgba = np.stack([n, n, n, np.full_like(n, alpha)], -1)
    return Image.fromarray(rgba, "RGBA").filter(ImageFilter.GaussianBlur(0.6))


def make_backgrounds(lib: Path, cat: Catalog):
    out = lib / "backgrounds"
    jobs = {
        "lavender-mist-4k.png": lambda: radial(3840, 2160, PALETTE["lavender-50"], PALETTE["lavender-300"]),
        "violet-night-4k.png": lambda: radial(3840, 2160, PALETTE["violet-700"], PALETTE["ink"], power=1.0),
        "lilac-dusk-4k.png": lambda: radial(3840, 2160, PALETTE["lavender-200"], PALETTE["violet-700"], cx=0.3, cy=0.3),
        "grid-overlay-4k.png": lambda: grid_overlay(3840, 2160),
        "grid-overlay-dark-4k.png": lambda: grid_overlay(3840, 2160, color=(36, 18, 74), alpha=30, dot_alpha=70),
        "film-grain-tile-1024.png": lambda: grain(),
    }
    for name, fn in jobs.items():
        p = out / name
        if not p.exists():
            fn().save(p, optimize=True)
        cat.add(p, "backgrounds", "generated://synth_assets.py/backgrounds", "original",
                "None (original)", tags=["background", "lavender-luxe"])


# ------------------------------------------------------------------ original logos

LOGOS = {
    "regalia": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 160">
  <g fill="none" stroke="{c}" stroke-width="5"><circle cx="80" cy="80" r="62"/><circle cx="80" cy="80" r="52" stroke-width="1.5"/></g>
  <path fill="{c}" d="M52 104h56v8H52zm4-8 6-34 12 14 6-22 6 22 12-14 6 34z"/>
  <text x="168" y="98" font-family="Italiana, 'EB Garamond', serif" font-size="58" letter-spacing="10" fill="{c}">REGALIA</text>
  <text x="172" y="128" font-family="'Instrument Sans', sans-serif" font-size="15" letter-spacing="7" fill="{c}" opacity=".75">STRATEGY · ELEVATED</text>
</svg>""",
    "aurelia": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140">
  <path fill="none" stroke="{c}" stroke-width="4" d="M70 18 118 122H22z"/><path fill="{c}" d="M52 92h36v5H52z"/>
  <text x="140" y="88" font-family="Gloock, 'EB Garamond', serif" font-size="54" letter-spacing="4" fill="{c}">Aurelia</text>
</svg>""",
    "noctis": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140">
  <path fill="{c}" d="M74 20a50 50 0 1 0 46 70 40 40 0 1 1-46-70z"/>
  <circle cx="104" cy="40" r="4" fill="{c}"/><circle cx="118" cy="58" r="2.5" fill="{c}"/>
  <text x="150" y="88" font-family="'Instrument Serif', serif" font-size="56" letter-spacing="8" fill="{c}">NOCTIS</text>
</svg>""",
    "vanta": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140">
  <path fill="{c}" d="M20 30h36l22 48 22-48h36l-58 94z"/><path fill="none" stroke="{c}" stroke-width="3" d="M14 22h128"/>
  <text x="160" y="92" font-family="'Instrument Sans', sans-serif" font-weight="700" font-size="54" letter-spacing="14" fill="{c}">VANTA</text>
</svg>""",
    "lumen": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140">
  <path fill="{c}" d="m70 14 10 42 42 14-42 14-10 42-10-42-42-14 42-14z"/>
  <text x="140" y="90" font-family="'Libre Baskerville', serif" font-style="italic" font-size="52" fill="{c}">Lumen</text>
</svg>""",
}


def rsvg(svg: Path, png: Path, width: int):
    subprocess.run(["rsvg-convert", "-w", str(width), "-b", "none", "-o", str(png), str(svg)], check=True)


def make_logos(lib: Path, cat: Catalog):
    out = lib / "logos"
    for name, tpl in LOGOS.items():
        for tone, color in (("ink", PALETTE["violet-900"]), ("white", PALETTE["white"])):
            svg = out / f"{name}-{tone}.svg"
            svg.write_text(tpl.replace("{c}", color))
            png = svg.with_suffix(".png")
            rsvg(svg, png, 1600)
            for p in (svg, png):
                cat.add(p, "logos", "generated://synth_assets.py/logos", "original",
                        "Fictional brand created for testing; not a real company", tags=["logo", name, tone])


# ------------------------------------------------------------------ icons (third-party, open licenses)

LUCIDE = ["crown", "gem", "sparkles", "trophy", "star", "play", "chart-line", "shield-check", "rocket", "target",
          "chess-knight", "chess-king", "chess-queen"]
SIMPLE = ["blender", "python", "ffmpeg", "react", "nodedotjs", "figma", "github", "opencv", "typescript"]


def make_icons(lib: Path, cat: Catalog, vendor: Path):
    out_i, out_l = lib / "icons", lib / "logos"
    for name in LUCIDE:
        src = vendor / "lucide-static" / "icons" / f"{name}.svg"
        svg = out_i / f"lucide-{name}.svg"
        txt = src.read_text().replace('stroke="currentColor"', f'stroke="{PALETTE["lavender-50"]}"')
        svg.write_text(txt)
        rsvg(svg, svg.with_suffix(".png"), 512)
        for p in (svg, svg.with_suffix(".png")):
            cat.add(p, "icons", f"https://lucide.dev/icons/{name}", "ISC",
                    "Keep the ISC copyright notice when redistributing the SVG source", tags=["icon", "lucide", name],
                    attribution="Lucide Icons (ISC)", source_page="https://www.npmjs.com/package/lucide-static/v/1.73.0")
    for name in SIMPLE:
        src = vendor / "simple-icons" / "icons" / f"{name}.svg"
        svg = out_l / f"software-{name}.svg"
        svg.write_text(src.read_text().replace("<path ", f'<path fill="{PALETTE["lavender-50"]}" '))
        rsvg(svg, svg.with_suffix(".png"), 512)
        for p in (svg, svg.with_suffix(".png")):
            cat.add(p, "logos", f"https://simpleicons.org/?q={name}", "CC0-1.0",
                    "Path data is CC0, but the logo is a TRADEMARK of its owner: use only nominatively "
                    "(to refer to that product) and follow the brand's guidelines; no implied endorsement",
                    tags=["logo", "software", "simple-icons", name],
                    source_page="https://www.npmjs.com/package/simple-icons/v/16.38.0")


# ------------------------------------------------------------------ fonts

OFL_FONTS = ["Italiana-Regular.ttf", "Gloock-Regular.ttf", "InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf",
             "LibreBaskerville-Regular.ttf", "CrimsonPro-Regular.ttf", "CrimsonPro-Italic.ttf", "YoungSerif-Regular.ttf",
             "InstrumentSans-Regular.ttf", "InstrumentSans-Bold.ttf", "WorkSans-Regular.ttf"]


def make_fonts(lib: Path, cat: Catalog, canvas_fonts: Path):
    out = lib / "fonts"
    for f in OFL_FONTS:
        src = canvas_fonts / f
        if not src.exists():
            continue
        dst = out / f
        shutil.copy2(src, dst)
        family = f.split("-")[0]
        lic = canvas_fonts / f"{family}-OFL.txt"
        if lic.exists():
            shutil.copy2(lic, out / lic.name)
        cat.add(dst, "fonts", "https://github.com/anthropics/skills/tree/main/skills/canvas-design/canvas-fonts",
                "OFL-1.1", "May be embedded/used in videos and images; do not sell the font file by itself",
                tags=["font", family], attribution=f"{family} (SIL Open Font License)")
    for src in (Path("/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf"),
                Path("/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Italic.ttf")):
        if src.exists():
            dst = out / src.name
            shutil.copy2(src, dst)
            cat.add(dst, "fonts", "https://packages.ubuntu.com/noble/fonts-ebgaramond-extra", "OFL-1.1",
                    "May be embedded; do not sell the font file by itself", tags=["font", "EB Garamond"])


# ------------------------------------------------------------------ transparent stills from 3D


def make_png_stills(lib: Path, cat: Catalog):
    for seq in sorted((lib / "3d-assets").glob("*/meta.json")):
        folder = seq.parent
        frames = sorted(folder.glob("f_*.png"))
        if not frames or "board" in folder.name:
            continue
        hero = frames[len(frames) // 8]  # ~45° three-quarter view
        im = Image.open(hero)
        bbox = im.getchannel("A").getbbox()
        dst = lib / "transparent-png" / f"{folder.name}-hero.png"
        im.crop(bbox).save(dst)
        cat.add(dst, "transparent-png", f"generated://blender_assets.py/{folder.name}/{hero.name}", "original",
                "None (original 3D render)", tags=["3d", "chess", "cutout"])
        cat.add(folder, "3d-assets", f"generated://blender_assets.py/{folder.name}", "original",
                "None (original procedural 3D asset)", tags=["3d", "turntable", "png-sequence"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["all", "backgrounds", "logos", "icons", "fonts", "stills"])
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--vendor", type=Path, default=Path("/home/user/creative-studio/.vendor/node_modules"))
    ap.add_argument("--canvas-fonts", type=Path, default=Path.home() / ".claude/skills/canvas-design/canvas-fonts")
    a = ap.parse_args(argv)
    cat = Catalog(a.library)
    if a.what in ("all", "fonts"):
        make_fonts(a.library, cat, a.canvas_fonts)
    if a.what in ("all", "backgrounds"):
        make_backgrounds(a.library, cat)
    if a.what in ("all", "logos"):
        make_logos(a.library, cat)
    if a.what in ("all", "icons"):
        make_icons(a.library, cat, a.vendor)
    if a.what in ("all", "stills"):
        make_png_stills(a.library, cat)
    cat.save()
    print(f"catalogued assets: {len(cat.data['assets'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
