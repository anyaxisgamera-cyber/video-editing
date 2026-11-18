"""Deterministic cutouts for objects generated on plain light or black backgrounds.

Usage: python build/cutout.py light|dark SRC.png DST.png

light: (any plain, roughly uniform backdrop) denoises, fits a smooth quadratic
       background surface to the border pixels, measures each pixel's Lab distance
       from it, keeps the largest region not connected to the border, and feathers
       the edge. Shadows are dropped; the composition adds its own.
dark:  alpha from brightness above the black background (for glowing objects).
No learned model and no downloaded code are involved.
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image, ImageFilter
from skimage import color, measure, morphology
from skimage.filters import median


def fit_background(lab: np.ndarray, border: np.ndarray) -> np.ndarray:
    h, w, _ = lab.shape
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = xx / w - 0.5, yy / h - 0.5
    basis = np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], axis=-1)
    A = basis[border]
    out = np.empty_like(lab)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A, lab[..., c][border], rcond=None)
        out[..., c] = basis @ coef
    return out


def light(src: str, dst: str) -> None:
    im = Image.open(src).convert("RGB")
    # Denoise before measuring: generated studio backdrops carry speckle grain.
    smooth = im.filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.GaussianBlur(1.5))
    rgb = np.asarray(smooth, dtype=np.float32) / 255
    lab = color.rgb2lab(rgb)
    h, w = lab.shape[:2]
    b = max(8, int(0.05 * min(h, w)))
    border = np.zeros((h, w), bool)
    border[:b], border[-b:], border[:, :b], border[:, -b:] = True, True, True, True
    bg = fit_background(lab, border)
    dist = np.linalg.norm(lab - bg, axis=-1)
    # Background = low-distance pixels connected to the frame edge.
    low = dist < 13.0
    labels = measure.label(low, connectivity=1)
    edge_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bgmask = np.isin(labels, edge_labels[edge_labels > 0])
    fg = morphology.remove_small_objects(~bgmask, max_size=1500)
    fg = morphology.remove_small_holes(fg, max_size=6000)
    fg = morphology.binary_opening(fg, morphology.disk(3))
    keep = measure.label(fg)
    if keep.max() > 1:  # keep the largest object only
        sizes = np.bincount(keep.ravel()); sizes[0] = 0
        fg = keep == sizes.argmax()
    a = Image.fromarray((fg * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.6))
    out = im.copy()
    out.putalpha(a)
    out.save(dst)


def dark(src: str, dst: str) -> None:
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, dtype=np.float32) / 255
    lum = rgb.max(axis=-1)
    alpha = np.clip((lum - 0.04) / 0.22, 0, 1)
    # Un-premultiply against black so edges keep their color.
    safe = np.maximum(alpha[..., None], 1e-3)
    col = np.clip(rgb / safe, 0, 1) * (alpha[..., None] > 0)
    rgba = np.dstack([col, alpha])
    Image.fromarray((rgba * 255).astype("uint8"), "RGBA").save(dst)


if __name__ == "__main__":
    {"light": light, "dark": dark}[sys.argv[1]](sys.argv[2], sys.argv[3])
