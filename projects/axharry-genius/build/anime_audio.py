"""Original score and edit-synced sound design for the AXHARRY anime cut.

Usage: python build/anime_audio.py motion/props/en.json work/en

music.wav: A-minor synth drone; sub pulse + kick/hat enter at the third scene and
           build; risers into intense scenes; at the closing message the drums
           drop and the harmony resolves to a warm major chord.
sfx.wav:   whoosh on every cut, sub-bass hit on key words, impact on intense cuts,
           soft glitch ticks on caption changes, riser + shimmer into the end card.
All sound is synthesized deterministically (no samples, no third-party audio).
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 100.0
rng = np.random.default_rng(1001)


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def env(n: int, a: float, r: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.clip(t / max(a, 1e-4), 0, 1) * np.clip((n / SR - t) / max(r, 1e-4), 0, 1)


def add(buf, at, sig, pan=0.5):
    s = int(at * SR)
    if s >= len(buf):
        return
    if s < 0:
        sig, s = sig[-s:], 0
    e = min(len(buf), s + len(sig))
    buf[s:e, 0] += sig[: e - s] * (1 - pan) * 1.4142 * 0.7071
    buf[s:e, 1] += sig[: e - s] * pan * 1.4142 * 0.7071


def pad_chord(notes, dur, gain=0.05, bright=0.15):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for m in notes:
        for d in (-0.003, 0.003):
            ph = rng.uniform(0, 6.283)
            y += np.sin(2 * np.pi * hz(m) * (1 + d) * t + ph) + bright * np.sin(4 * np.pi * hz(m) * t + ph)
    return y * gain * env(n, 1.2, 1.2)


def kick(g=0.6):
    t = np.arange(int(0.4 * SR)) / SR
    f = 45 + 110 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8) * g


def hat(g=0.05):
    n = int(0.06 * SR)
    x = np.diff(np.concatenate([[0], rng.standard_normal(n)]))
    return x * np.exp(-np.arange(n) / SR * 70) * g


def sub(note, dur, g=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(note) * t) * np.exp(-t * 3.5) * g


def noise_sweep(length, g, rise=True, lo=250, hi=7000):
    n = int(length * SR)
    t = np.linspace(0, 1, n)
    x = rng.standard_normal(n)
    cut = (lo + (hi - lo) * (t if rise else 1 - t) ** 1.7) / SR
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        a = 2 * np.pi * cut[i]
        acc += a / (1 + a) * (x[i] - acc)
        y[i] = acc
    return y / (np.abs(y).max() + 1e-9) * np.sin(np.pi * t) ** 1.4 * g


def impact(g=0.55):
    t = np.arange(int(1.0 * SR)) / SR
    f = 36 + 70 * np.exp(-t * 12)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4)
    crack = rng.standard_normal(len(t)) * np.exp(-t * 40) * 0.3
    return (body + crack) * g


def tick(g=0.05):
    t = np.arange(int(0.035 * SR)) / SR
    return np.sign(np.sin(2 * np.pi * 1800 * t)) * np.exp(-t * 140) * g


def shimmer(g=0.08, dur=2.4):
    t = np.arange(int(dur * SR)) / SR
    y = sum(np.sin(2 * np.pi * f * t) for f in (1046.5, 1318.5, 1568.0, 2093.0))
    return y / 4 * np.exp(-t * 1.3) * np.clip(t / 0.04, 0, 1) * g


def reverb(x, seconds=2.4, wet=0.28):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.empty_like(x)
    for c in range(2):
        ir = rng.standard_normal(n) * np.exp(-t * 6.9 / seconds)
        ir = np.convolve(ir, np.ones(20) / 20, mode="same")
        ir /= np.sqrt((ir ** 2).sum())
        size = 1 << int(np.ceil(np.log2(len(x) + n)))
        y = np.fft.irfft(np.fft.rfft(x[:, c], size) * np.fft.rfft(ir, size), size)[: len(x)]
        out[:, c] = (1 - wet) * x[:, c] + wet * y
    return out


def write(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as h:
        h.setnchannels(2)
        h.setsampwidth(2)
        h.setframerate(SR)
        h.writeframes((x * 32767).astype("<i2").tobytes())


def main() -> None:
    props = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    work = Path(sys.argv[2])
    total = props["canvas"]["durationInFrames"] / props["canvas"]["fps"]
    n = int(total * SR)
    scenes = props["scenes"]
    gold = props["goldFrom"]
    end_card = props["endCard"]
    groove_from = scenes[3]["start"] if len(scenes) > 3 else 4.0

    # ---- music ----
    music = np.zeros((n, 2))
    minor = [[45, 52, 57, 60, 64], [41, 48, 53, 57, 60], [43, 50, 55, 59, 62], [40, 47, 52, 56, 59]]  # Am F G E
    bar = 4 * 60 / BPM
    t0, k = 0.0, 0
    while t0 < gold:
        dur = min(bar + 1.2, gold - t0 + 1.2)
        add(music, t0, pad_chord(minor[k % 4], dur, 0.045 + 0.01 * min(1, t0 / 20)), 0.5)
        t0 += bar
        k += 1
    # resolution: C major -> F major (warm), from the closing line to the end
    add(music, gold - 0.2, pad_chord([48, 55, 60, 64, 67, 72], (end_card - gold) + 1.6, 0.06, 0.25))
    add(music, end_card - 0.2, pad_chord([41, 53, 57, 60, 65, 69], total - end_card + 0.2, 0.06, 0.25))
    beat = 60 / BPM
    roots = [33, 29, 31, 28]
    t0, k = groove_from, 0
    while t0 < gold - 0.1:
        intensity = min(1.0, (t0 - groove_from) / 20 + 0.45)
        if k % 2 == 0:
            add(music, t0, kick(0.5 * intensity))
        add(music, t0 + beat / 2, hat(0.045 * intensity), 0.62)
        if k % 4 == 2:
            add(music, t0, hat(0.08 * intensity), 0.4)
        add(music, t0, sub(roots[(k // 16) % 4], beat * 0.95, 0.2 * intensity))
        t0 += beat
        k += 1
    music = reverb(music)
    music *= env(n, 1.5, 2.0)[:, None]
    music /= np.abs(music).max() / 0.5
    write(work / "music.wav", music)

    # ---- sound effects ----
    sfx = np.zeros((n, 2))
    intense = set(props.get("intense", []))
    for si, s in enumerate(scenes):
        for j, shot in enumerate(s["shots"]):
            if shot["start"] < 0.1:
                continue
            w = noise_sweep(0.32, 0.18 if s["id"] not in intense else 0.26)
            add(sfx, shot["start"] - 0.2, w, 0.35 + 0.3 * ((si + j) % 2))
            if s["id"] in intense and j == 0:
                add(sfx, shot["start"], impact(0.5))
        if s["id"] in intense:
            add(sfx, s["start"] - 1.2, noise_sweep(1.2, 0.12, True, 150, 5000), 0.5)
        for c in s["chunks"]:
            add(sfx, c["start"] - 0.02, tick(0.035), 0.6)
        for w in s["words"]:
            if w["key"]:
                add(sfx, w["start"], sub(33, 0.5, 0.3))
    add(sfx, end_card - 0.9, noise_sweep(1.0, 0.18, True, 200, 9000), 0.5)
    add(sfx, end_card, shimmer(0.09, 2.6), 0.5)
    add(sfx, end_card, impact(0.25))
    write(work / "sfx.wav", sfx)
    print(json.dumps({"duration": round(total, 3), "groove_from": round(groove_from, 2), "gold": gold, "end_card": end_card}))


if __name__ == "__main__":
    main()
