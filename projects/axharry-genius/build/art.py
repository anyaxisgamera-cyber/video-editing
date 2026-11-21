"""Finish selected art for the render: python build/art.py SRC_DIR art.selection.json

Upscales each chosen 512x512 SD-Turbo image to 1080x1080 (Lanczos + gentle unsharp)
into motion/public/art/<scene>_<seed>.jpg, and copies the original logo unmodified
into motion/public/brand/.
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
src, sel = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
out = ROOT / "motion" / "public" / "art"
out.mkdir(parents=True, exist_ok=True)
for scene, seeds in sel.items():
    for s in seeds:
        im = Image.open(src / f"{scene}_{s}.png").convert("RGB").resize((1080, 1080), Image.LANCZOS)
        im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2)).save(out / f"{scene}_{s}.jpg", quality=93)
brand = ROOT / "motion" / "public" / "brand"
brand.mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / "brand" / "axharry-logo-original.jpg", brand / "axharry-logo-original.jpg")
print(f"finished {sum(len(v) for v in sel.values())} images")
