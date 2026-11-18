"""Generate an original, soft ambient score (pad + sparse bell motif + reverb).

Usage: python build/music.py OUTPUT.wav DURATION_SECONDS [--seed N]

Deterministic and royalty-free: everything is synthesized from sine partials.
The music sits under narration, so it is deliberately sparse, warm, and slow.
"""

from __future__ import annotations

import argparse
import wave

import numpy as np

SR = 48000
CHORD_SECONDS = 4.0
# D major, gentle I – vi – IV – V(sus) progression; MIDI note numbers.
PROGRESSION = [
    [50, 57, 62, 66, 69, 76],   # Dadd9
    [47, 54, 62, 66, 69, 73],   # Bm7(add11-ish voicing)
    [43, 55, 62, 66, 71, 74],   # Gmaj7
    [45, 57, 62, 64, 69, 71],   # Asus2
]
MOTIF = [74, 76, 78, 81, 78, 76, 73, 74]  # bell line, one note per ~1s, gaps added below


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1)
    r = np.clip((n / SR - t) / release, 0, 1)
    return np.sin(a * np.pi / 2) ** 2 * np.sin(r * np.pi / 2) ** 2


def pad(duration: float, rng: np.random.Generator) -> np.ndarray:
    total = int(duration * SR)
    out = np.zeros((total, 2))
    step = int(CHORD_SECONDS * SR)
    overlap = int(1.6 * SR)
    for k, start in enumerate(range(-overlap // 2, total, step)):
        chord = PROGRESSION[k % len(PROGRESSION)]
        n = step + overlap
        t = np.arange(n) / SR
        voice = np.zeros((n, 2))
        for note in chord:
            f = hz(note)
            for detune, pan in ((-0.0025, 0.3), (0.0025, 0.7)):
                phase = rng.uniform(0, 2 * np.pi)
                lfo = 1 + 0.002 * np.sin(2 * np.pi * 0.13 * t + phase)
                tone = (np.sin(2 * np.pi * f * (1 + detune) * t * lfo + phase)
                        + 0.18 * np.sin(4 * np.pi * f * (1 + detune) * t + phase)
                        + 0.05 * np.sin(6 * np.pi * f * t + phase))
                gain = 0.05 if note < 52 else 0.035
                voice[:, 0] += tone * gain * (1 - pan)
                voice[:, 1] += tone * gain * pan
        voice *= envelope(n, 1.4, 1.4)[:, None]
        a, b = max(start, 0), min(start + n, total)
        out[a:b] += voice[a - start:b - start]
    return out


def bells(duration: float, rng: np.random.Generator) -> np.ndarray:
    total = int(duration * SR)
    out = np.zeros((total, 2))
    t0, i = 2.0, 0
    while t0 < duration - 3.0:
        note = MOTIF[i % len(MOTIF)]
        n = int(3.0 * SR)
        t = np.arange(n) / SR
        f = hz(note)
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2.01 * f * t) * np.exp(-t * 3)
                + 0.12 * np.sin(2 * np.pi * 3.98 * f * t) * np.exp(-t * 6))
        tone *= np.exp(-t * 1.6) * np.clip(t / 0.008, 0, 1) * 0.06
        pan = 0.35 + 0.3 * rng.random()
        s = int(t0 * SR)
        e = min(s + n, total)
        out[s:e, 0] += tone[: e - s] * (1 - pan)
        out[s:e, 1] += tone[: e - s] * pan
        t0 += rng.choice([1.0, 1.0, 2.0])
        i += 1
    return out


def reverb(x: np.ndarray, rng: np.random.Generator, seconds: float = 3.2, wet: float = 0.38) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.empty_like(x)
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-t * 6.9 / seconds)
        ir = np.convolve(ir, np.ones(24) / 24, mode="same")  # darken the tail
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(np.ceil(np.log2(len(x) + n)))
        y = np.fft.irfft(np.fft.rfft(x[:, ch], size) * np.fft.rfft(ir, size), size)[: len(x)]
        out[:, ch] = (1 - wet) * x[:, ch] + wet * y
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("duration", type=float)
    parser.add_argument("--seed", type=int, default=114)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    mix = pad(args.duration, rng) + bells(args.duration, rng)
    mix = reverb(mix, rng)
    mix *= envelope(len(mix), 2.0, 2.8)[:, None]
    mix /= np.max(np.abs(mix)) / 0.5
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(args.output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
