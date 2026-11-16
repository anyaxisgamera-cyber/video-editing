#!/usr/bin/env python3
"""Original music beds and sound effects, synthesized from scratch (no samples, no third-party rights).

Music is rendered bar-by-bar and streamed to disk, so any duration works (30 s ... 60+ min)
with constant memory. The beat grid (bpm, bar length) is written next to the WAV so the
timeline generator can land cuts and transitions on downbeats.

    python3 audio_synth.py music out.wav --duration 300 --bpm 96 --seed 7
    python3 audio_synth.py sfx /path/sound-effects            # whoosh, impact, shimmer, riser, tick, swell
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000


def midi_hz(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    env = np.full(n, s, dtype=np.float32)
    if a_n:
        env[:a_n] = np.linspace(0, 1, a_n, dtype=np.float32)
    if d_n:
        env[a_n:a_n + d_n] = np.linspace(1, s, len(env[a_n:a_n + d_n]), dtype=np.float32)
    if r_n and n > r_n:
        env[-r_n:] *= np.linspace(1, 0, r_n, dtype=np.float32)
    return env


def lowpass(x: np.ndarray, hz: float, order: int = 2) -> np.ndarray:
    sos = butter(order, min(hz, SR / 2 - 100), btype="low", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sos = butter(2, [lo, min(hi, SR / 2 - 100)], btype="band", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    return np.stack([mono * l, mono * r], axis=1)


# ------------------------------------------------------------------ instruments


def pad(freqs, dur, rng, bright=1800.0):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros((n, 2), dtype=np.float32)
    for f in freqs:
        for k, det in enumerate((-0.11, 0.0, 0.13)):
            ph = rng.uniform(0, 1)
            saw = 2 * ((t * f * 2 ** (det / 12) + ph) % 1.0) - 1
            out += stereo(saw.astype(np.float32) * 0.05, pan=(-0.6, 0.0, 0.6)[k])
    sweep = lowpass(out, bright)
    return sweep * adsr(n, 1.4, 0.8, 0.85, 1.6)[:, None]


def pluck(f, dur, pan=0.0):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    env = np.exp(-t * 5.5).astype(np.float32) * np.minimum(1, t * 400)
    return stereo((tone * env * 0.16).astype(np.float32), pan)


def with_delay(x, delay_s, fb=0.38, taps=4):
    d = int(delay_s * SR)
    out = np.zeros((len(x) + d * taps, 2), dtype=np.float32)
    out[:len(x)] += x
    g = 1.0
    for k in range(1, taps + 1):
        g *= fb
        seg = x[:, ::-1] if k % 2 else x  # ping-pong
        out[k * d:k * d + len(x)] += seg * g
    return out


def kick(dur=0.5):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = 42 + 85 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return stereo((np.sin(ph) * np.exp(-t * 7) * 0.55).astype(np.float32))


def hat(rng, dur=0.09, amp=0.05):
    n = int(dur * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    x = bandpass(noise, 7000, 15000) * np.exp(-np.arange(n) / SR * 45).astype(np.float32) * amp
    return stereo(x, pan=rng.uniform(-0.3, 0.3))


def sub(f, dur):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return stereo((np.sin(2 * np.pi * f * t) * adsr(n, 0.02, 0.2, 0.7, 0.25) * 0.22).astype(np.float32))


# ------------------------------------------------------------------ music

PROGRESSIONS = {
    # (root midi, chord tones as semitones) — lush minor progression for an elegant promo
    "noir": [(50, [0, 3, 7, 10, 14]), (46, [0, 4, 7, 11, 14]), (43, [0, 3, 7, 10, 14]), (45, [0, 5, 7, 10, 14])],
    "dawn": [(48, [0, 4, 7, 11, 14]), (45, [0, 3, 7, 10, 14]), (41, [0, 4, 7, 11, 16]), (43, [0, 5, 7, 10, 14])],
}


def section_for(bar_index: int) -> int:
    """4-bar intro, then a 24-bar cycle: 8 groove, 12 full, 4 breakdown (promo pacing)."""
    if bar_index < 4:
        return 0
    k = (bar_index - 4) % 24
    return 1 if k < 8 else (2 if k < 20 else 3)


def music(out: Path, duration: float, bpm: float = 96, seed: int = 7, style: str = "noir") -> dict:
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = 4 * beat
    bar_n = int(round(bar * SR))
    nbars = int(math.ceil(duration / bar))
    prog = PROGRESSIONS[style]
    total_n = int(round(duration * SR))
    tail = np.zeros((0, 2), dtype=np.float32)
    written = 0
    fade_n = int(min(4.0, duration * 0.15) * SR)
    with sf.SoundFile(out, "w", SR, 2, subtype="PCM_24") as fh:
        for b in range(nbars):
            root, tones = prog[(b // 2) % len(prog)]
            section = section_for(b)  # 0 intro/air, 1 groove, 2 full, 3 breakdown
            first_bar_of_chord = b % 2 == 0
            buf = np.zeros((bar_n * 4, 2), dtype=np.float32)

            def put(x, at_s):
                i = int(round(at_s * SR))
                j = min(len(buf), i + len(x))
                buf[i:j] += x[:j - i]

            if first_bar_of_chord:
                bright = 900 + 1400 * (section in (1, 2)) + 600 * (section == 2)
                put(pad([midi_hz(root + 12 + t) for t in tones[:4]], bar * 2 + 0.6, rng, bright), 0)
            if b >= 1 and section != 3:
                for k in range(4):
                    put(sub(midi_hz(root - 12), beat * 0.95), k * beat)
            if b >= 2 and section in (1, 2):
                pattern = [0, 2, 4, 1, 3, 4, 2, 1]
                for k in range(8):
                    note = root + 24 + tones[pattern[(k + b) % 8] % len(tones)]
                    put(with_delay(pluck(midi_hz(note), 0.6, pan=0.5 * math.sin(k)), beat * 0.75, 0.3, 3),
                        k * beat / 2)
            if b >= 4 and section == 2:
                for k in (0, 2):
                    put(kick(), k * beat)
                for k in range(4):
                    put(hat(rng), k * beat + beat / 2)
            if section == 3 and first_bar_of_chord:
                put(with_delay(pluck(midi_hz(root + 36 + tones[1]), 1.5, 0.3), beat, 0.45, 5), beat)
            # carry previous tail
            buf[:len(tail)] += tail
            chunk, tail = buf[:bar_n], buf[bar_n:].copy()
            nz = np.nonzero(np.any(np.abs(tail) > 1e-6, axis=1))[0]
            tail = tail[:nz[-1] + 1] if len(nz) else np.zeros((0, 2), dtype=np.float32)
            # trim to requested duration + master fade
            remain = total_n - written
            chunk = chunk[:remain]
            idx = np.arange(written, written + len(chunk))
            fade = np.clip((total_n - idx) / max(fade_n, 1), 0, 1).astype(np.float32)
            fadein = np.clip(idx / (0.5 * SR), 0, 1).astype(np.float32)
            chunk = np.tanh(chunk * 1.2 * (fade * fadein)[:, None]) * 0.8
            fh.write(chunk)
            written += len(chunk)
            if written >= total_n:
                break
    grid = {"bpm": bpm, "beat_seconds": beat, "bar_seconds": bar, "bars": nbars, "duration": duration,
            "sample_rate": SR, "style": style, "seed": seed,
            "sections": "4-bar intro, then cycles of 8 groove + 12 full (kick+hats) + 4 breakdown bars",
            "license": "original", "generator": "audio_synth.py"}
    out.with_suffix(".grid.json").write_text(json.dumps(grid, indent=2))
    return grid


# ------------------------------------------------------------------ SFX


def norm(x, peak=0.89):
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def sweep_noise(dur, f0, f1, f_peak, rng, peak_at=0.6):
    n = int(dur * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    hop = 512
    out = np.zeros(n + hop * 2, dtype=np.float32)
    win = np.hanning(hop * 2).astype(np.float32)
    for i in range(0, n - hop * 2, hop):
        p = i / n
        fc = f0 + (f_peak - f0) * (p / peak_at) if p < peak_at else f_peak + (f1 - f_peak) * ((p - peak_at) / (1 - peak_at))
        seg = np.fft.rfft(noise[i:i + hop * 2] * win)
        freqs = np.fft.rfftfreq(hop * 2, 1 / SR)
        mask = np.exp(-0.5 * ((np.log(freqs + 1) - math.log(fc)) / 0.45) ** 2)
        out[i:i + hop * 2] += np.fft.irfft(seg * mask).astype(np.float32) * win
    return out[:n]


def reverb(x, seconds=1.6, mix=0.35, rng=None):
    rng = rng or np.random.default_rng(1)
    n = int(seconds * SR)
    ir = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-np.arange(n) / SR * 4.5)[:, None].astype(np.float32)
    ir = lowpass(ir, 6000)
    wet = np.stack([np.convolve(x[:, c], ir[:, c]) for c in range(2)], axis=1)  # len(x) + n - 1
    dry = np.pad(x, ((0, len(wet) - len(x)), (0, 0)))
    return dry * (1 - mix) + norm(wet, 0.6) * mix


def make_sfx(folder: Path) -> list[Path]:
    rng = np.random.default_rng(11)
    folder.mkdir(parents=True, exist_ok=True)
    made = []

    def save(name, x):
        p = folder / f"synth-{name}.wav"
        sf.write(p, norm(x), SR, subtype="PCM_24")
        made.append(p)

    # whoosh: band-passed noise sweeping up then down, pan sweep; peak at 60 % (align peak with the cut)
    n = int(1.2 * SR)
    w = sweep_noise(1.2, 300, 500, 4200, rng, 0.6)
    env = np.interp(np.arange(n), [0, 0.6 * n, n], [0, 1, 0]).astype(np.float32) ** 1.6
    pan = np.linspace(-0.8, 0.8, n)
    save("whoosh", np.stack([w * env * np.cos((pan + 1) * np.pi / 4), w * env * np.sin((pan + 1) * np.pi / 4)], 1))
    # impact: pitch-dropping sub + noise transient + reverb
    t = np.arange(int(1.6 * SR)) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 18)) / SR) * np.exp(-t * 3.2)
    crack = lowpass(rng.standard_normal(len(t)).astype(np.float32), 2500) * np.exp(-t * 28).astype(np.float32)
    save("impact", reverb(stereo((boom * 0.9 + crack * 0.6).astype(np.float32)), 1.8, 0.3, rng))
    # shimmer: detuned high partials, slow swell — for logo / sparkle reveals
    t = np.arange(int(2.2 * SR)) / SR
    sh = sum(np.sin(2 * np.pi * f * (1 + rng.uniform(-0.002, 0.002)) * t + rng.uniform(0, 6))
             for f in (1760, 2217, 2637, 3520, 4434))
    sh = sh * np.minimum(1, t / 0.25) * np.exp(-t * 1.6) * (1 + 0.3 * np.sin(2 * np.pi * 7 * t))
    save("shimmer", reverb(stereo(sh.astype(np.float32) * 0.2), 1.4, 0.5, rng))
    # riser: noise + rising tone into a cut (ends at 100 %)
    t = np.arange(int(2.0 * SR)) / SR
    rise = sweep_noise(2.0, 200, 6000, 6000, rng, 0.99) * (t / 2.0) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(110 * 2 ** (t * 1.5)) / SR) * (t / 2.0) ** 3 * 0.4
    save("riser", stereo((rise + tone).astype(np.float32)))
    # tick: soft UI tick for staggered text/letters
    t = np.arange(int(0.08 * SR)) / SR
    save("tick", stereo((np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 90)).astype(np.float32) * 0.5))
    # swell: reversed reverb tail, ends at 100 % — use before blur-in titles
    x = reverb(stereo((np.sin(2 * np.pi * 523.25 * t[:1]) * 0).astype(np.float32)), 0.01)  # noop warm
    t = np.arange(int(1.4 * SR)) / SR
    tone = sum(np.sin(2 * np.pi * f * t) for f in (293.66, 440, 587.33)) * np.exp(-t * 2.5)
    sw = reverb(stereo(tone.astype(np.float32) * 0.3), 1.2, 0.6, rng)[::-1]
    save("swell", sw)
    for p in made:
        meta = {"generator": "audio_synth.py", "license": "original", "sample_rate": SR,
                "sync_point": {"whoosh": "60% (peak)", "riser": "end", "swell": "end", "impact": "start",
                               "shimmer": "start", "tick": "start"}[p.stem.replace("synth-", "")]}
        p.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub_ = ap.add_subparsers(dest="cmd", required=True)
    m = sub_.add_parser("music"); m.add_argument("out", type=Path); m.add_argument("--duration", type=float, required=True)
    m.add_argument("--bpm", type=float, default=96); m.add_argument("--seed", type=int, default=7)
    m.add_argument("--style", default="noir", choices=sorted(PROGRESSIONS))
    s = sub_.add_parser("sfx"); s.add_argument("folder", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "music":
        print(json.dumps(music(a.out, a.duration, a.bpm, a.seed, a.style), indent=2))
    else:
        print("\n".join(str(p) for p in make_sfx(a.folder)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
