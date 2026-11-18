"""Generate and finish the symbolic scene plates.

  python build/plates.py generate work/plates            # SD-Turbo on CPU, 3 seeds per scene
  python build/plates.py finish work/plates selection.json motion/public/media

`generate` needs torch + diffusers and downloads stabilityai/sd-turbo from
Hugging Face. Plates are illustrative symbolism only (no people), reviewed by
eye before selection. `finish` upscales the chosen 576x1024 seed to 1080x1920
with Lanczos, adds gentle sharpening and grain-preserving softness, and writes
JPEGs that the Remotion composition loads by scene id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

STYLE = (", cinematic film still, soft lavender and violet color grade, gentle volumetric light, "
         "shallow depth of field, serene, reverent, highly detailed, film grain")
SCENES = {
    "s1_candle": "a single small candle flame glowing quietly in a dark room, wisps of smoke, deep purple darkness",
    "s2_apple": "a single glossy apple resting on a dark wooden table, one soft beam of light falling on it, dark purple background",
    "s3_path": "a lonely dirt path in a misty meadow that forks into two separate paths, one path towards bright light, twilight, lavender fog",
    "s4_hourglass": "an antique hourglass with sand falling through it on a table, soft window light, dusky purple room",
    "s5_light": "golden and lavender sunbeams breaking through dramatic clouds over quiet hills at sunrise, heavenly light rays, majestic sky",
    "s6_bible": "an open old bible on a wooden table beside a window, soft morning light on the pages, lavender flowers nearby",
    "s7_cross": "a simple wooden cross silhouette on a hill under a soft lavender and pink dawn sky, calm and peaceful",
}
SEEDS = (11, 23, 37)


def generate(out: Path) -> None:
    import torch
    from diffusers import AutoPipelineForText2Image

    out.mkdir(parents=True, exist_ok=True)
    pipe = AutoPipelineForText2Image.from_pretrained("stabilityai/sd-turbo", torch_dtype=torch.float32)
    for name, prompt in SCENES.items():
        for seed in SEEDS:
            target = out / f"{name}_{seed}.png"
            if target.exists():
                continue
            image = pipe(prompt + STYLE, num_inference_steps=4, guidance_scale=0.0, width=576, height=1024,
                         generator=torch.Generator().manual_seed(seed)).images[0]
            image.save(target)
            print(name, seed, flush=True)


def finish(source: Path, selection: Path, out: Path) -> None:
    from PIL import Image, ImageFilter

    out.mkdir(parents=True, exist_ok=True)
    chosen = json.loads(selection.read_text())
    for scene, seed in chosen.items():
        image = Image.open(source / f"{scene}_{seed}.png").convert("RGB")
        image = image.resize((1080, 1920), Image.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=2.2, percent=45, threshold=3))
        image.save(out / f"{scene}.jpg", quality=93)
        print(f"{scene}: seed {seed}")


if __name__ == "__main__":
    if sys.argv[1] == "generate":
        generate(Path(sys.argv[2]))
    elif sys.argv[1] == "finish":
        finish(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        sys.exit(__doc__)
