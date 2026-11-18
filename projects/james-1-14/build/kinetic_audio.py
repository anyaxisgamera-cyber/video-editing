"""Music bed and edit-synced sound effects for the kinetic cut.

Usage: python build/kinetic_audio.py motion/props/en-kinetic.json work/en-kinetic

Writes music.wav (original 92 BPM soft beat: pad, sub bass, gentle kick/snap)
and sfx.wav (whoosh into every cut, bigger whoosh + low thump on circle wipes,
soft pop on each red key word, ticks on card items, a low hit + shimmer on the
closing card). Everything is synthesized deterministically; nothing is sampled.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 92.0
rng = np.random.default_rng(1114)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from music import envelope, pad, reverb  # noqa: E402  (reuse the project's pad + reverb)


def write(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as h:
        h.setnchannels(2)
        h.setsampwidth(2)
        h.setframerate(SR)
        h.writeframes((x * 32767).astype("<i2").tobytes())


def add(buf: np.ndarray, at: float, sig: np.ndarray, pan: float = 0.5) -> None:
    s = int(at * SR)
    if s >= len(buf) or s + len(sig) <= 0:
        return
    if s < 0:
        sig, s = sig[-s:], 0
    e = min(len(buf), s + len(sig))
    buf[s:e, 0] += sig[: e - s] * (1 - pan) * 2 ** 0.5 * 0.7071
    buf[s:e, 1] += sig[: e - s] * pan * 2 ** 0.5 * 0.7071


def kick(gain=0.9):
    t = np.arange(int(0.45 * SR)) / SR
    f = 48 + 90 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5) * gain


def snap(gain=0.22):
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = np.diff(np.concatenate([[0], noise]))  # brighter
    return noise * np.exp(-t * 32) * gain


def whoosh(length=0.42, gain=0.32, rise=True):
    n = int(length * SR)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    # sweeping one-pole low-pass: cutoff glides up (rise) through the cut
    cutoff = (300 + 5200 * (t if rise else 1 - t) ** 1.6) / SR
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        a = 2 * np.pi * cutoff[i]
        acc += a / (1 + a) * (noise[i] - acc)
        y[i] = acc
    shape = np.sin(np.pi * t) ** 1.5
    return y / (np.max(np.abs(y)) + 1e-9) * shape * gain


def pop(gain=0.22, f0=880):
    t = np.arange(int(0.11 * SR)) / SR
    f = f0 * (1 + 0.6 * np.exp(-t * 60))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38) * gain


def tick(gain=0.16):
    t = np.arange(int(0.05 * SR)) / SR
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * gain


def thump(gain=0.7):
    t = np.arange(int(1.2 * SR)) / SR
    f = 38 + 60 * np.exp(-t * 9)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2) * gain


def shimmer(gain=0.08):
    t = np.arange(int(2.6 * SR)) / SR
    y = sum(np.sin(2 * np.pi * f * t) for f in (1174.7, 1479.98, 1760.0, 2349.3))
    return y / 4 * np.exp(-t * 1.4) * np.clip(t / 0.05, 0, 1) * gain


def main() -> None:
    props = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    work = Path(sys.argv[2])
    duration = props["canvas"]["durationInFrames"] / props["canvas"]["fps"]
    final_start = props["final"]["start"]
    total = int(duration * SR)

    # ---- music ----
    music = pad(duration, rng) * 0.9
    beat = 60.0 / BPM
    drums = np.zeros((total, 2))
    bass = np.zeros((total, 2))
    roots = [38, 35, 31, 33]  # D B G A (an octave down)
    t = 0.6
    k = 0
    while t < duration - 0.3:
        bar_pos = k % 4
        if t < final_start - 0.1:  # drums drop out for the closing card
            if bar_pos in (0, 2):
                add(drums, t, kick(0.55))
            if bar_pos in (1, 3):
                add(drums, t, snap(0.10), pan=0.45)
            add(drums, t + beat / 2, tick(0.035), pan=0.62)
        if bar_pos == 0:
            root = roots[(k // 4) % 4]
            n = int(beat * 4 * SR)
            tt = np.arange(n) / SR
            note = np.sin(2 * np.pi * 440 * 2 ** ((root - 69) / 12) * tt) * envelope(n, 0.05, 0.4) * 0.16
            add(bass, t, note)
        t += beat
        k += 1
    music = reverb(music, rng, seconds=2.6, wet=0.3) + drums + bass
    music *= envelope(total, 0.8, 2.2)[:, None]
    music /= np.max(np.abs(music)) / 0.5
    write(work / "music.wav", music)

    # ---- sound effects ----
    sfx = np.zeros((total, 2))
    for i, scene in enumerate(props["scenes"]):
        if i > 0:
            big = scene.get("enter") == "circle"
            w = whoosh(0.5 if big else 0.36, 0.30 if big else 0.2)
            add(sfx, scene["start"] - len(w) / SR * 0.55, w, pan=0.4 + 0.2 * (i % 2))
            if big:
                add(sfx, scene["start"], thump(0.35))
        for word in scene["words"]:
            if word["key"]:
                add(sfx, word["start"] - 0.02, pop(0.16, 760 + 120 * (i % 3)))
        for item in scene.get("items", []):
            add(sfx, item["start"] - 0.03, tick(0.2))
        if scene.get("exit") == "tilt":
            w = whoosh(0.4, 0.22, rise=False)
            add(sfx, scene["end"] - 0.4, w, pan=0.7)
    add(sfx, final_start - 0.2, whoosh(0.45, 0.26))
    add(sfx, final_start, thump(0.6))
    add(sfx, final_start + 0.05, shimmer())
    write(work / "sfx.wav", sfx)
    print(json.dumps({"duration": round(duration, 3), "scenes": len(props["scenes"])}))


if __name__ == "__main__":
    main()
