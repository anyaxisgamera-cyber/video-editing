"""Synthesize narration and derive a word-timed timeline for one language.

Usage: python build/narrate.py content/en.json work/en [--ca-bundle PATH]

Writes into the work directory:
  lines/NN.mp3, lines/NN.json   raw neural-TTS clips and their word boundaries
  narration.wav                 48 kHz mono narration placed on the output timeline
  timeline.json                 scenes, subtitle cues, step beats, and total length
  subtitles.srt                 sidecar subtitles matching the burned-in cues

Each script line is synthesized once at a natural (never faster than default)
rate. Lines are separated by pauses; nothing is time-stretched. Subtitle cue
times come from the synthesizer's word boundaries, offset by each line's
placement, so cues follow the actual spoken words.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import ssl
import subprocess
from pathlib import Path

import edge_tts
import edge_tts.communicate as communicate

SAMPLE_RATE = 48000
LEAD_IN = 0.5          # silence before the first line
LINE_GAP = 0.45        # natural breath between lines
END_HOLD = 0.7         # after the last line, before the final card
FINAL_CARD = 3.2       # music-only closing card
CUE_TAIL = 0.25        # keep a cue up briefly after its last word


async def synthesize(text: str, voice: str, rate: str, pitch: str, mp3: Path) -> list[dict]:
    words: list[dict] = []
    stream = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    with mp3.open("wb") as handle:
        async for chunk in stream.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    return words


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def strip_punct(token: str) -> str:
    return re.sub(r"[^\wఀ-౿']", "", token).lower()


def attach_display_tokens(text: str, words: list[dict]) -> list[dict]:
    """Pair boundary words with the script's own tokens so cues keep punctuation."""
    tokens = text.split()
    if len(tokens) == len(words):
        return [{**w, "display": t} for w, t in zip(words, tokens)]
    # The synthesizer may report several script tokens as one word
    # (for example "James 1:14"). Align on normalized characters: each spoken
    # word consumes script tokens until it has covered its own characters.
    result, ti = [], 0
    for w in words:
        need = len(strip_punct(w["text"]))
        taken, have = [], 0
        while ti < len(tokens) and (have < need or not taken):
            taken.append(tokens[ti])
            have += len(strip_punct(tokens[ti]))
            ti += 1
        if taken:
            result.append({**w, "display": " ".join(taken)})
        elif result:
            result[-1]["end"] = w["end"]
    if ti < len(tokens) and result:
        result[-1]["display"] += " " + " ".join(tokens[ti:])
    return result


def attach_segments(segments: list, words: list[dict]) -> list[dict]:
    """Align boundary words segment by segment; overridden segments collapse to one display token."""
    result, wi = [], 0
    for spoken, display in segments:
        n_chars = len(strip_punct(spoken))
        seg_words, have = [], 0
        while wi < len(words) and have < n_chars:
            seg_words.append(words[wi])
            have += len(strip_punct(words[wi]["text"]))
            wi += 1
        if display is None:
            result += attach_display_tokens(spoken, seg_words)
        elif seg_words:
            result.append({"text": spoken, "start": seg_words[0]["start"], "end": seg_words[-1]["end"], "display": display, "cueBreak": True})
    if wi < len(words) and result:
        result[-1]["end"] = words[-1]["end"]
    return result


def chunk_cues(words: list[dict], max_chars: int) -> list[list[dict]]:
    cues, current = [], []
    for w in words:
        candidate = " ".join(x["display"] for x in current + [w])
        if current and len(candidate) > max_chars:
            cues.append(current)
            current = []
        current.append(w)
        if w.get("cueBreak") or re.search(r"[.!?:]$", w["display"]) or (re.search(r",$", w["display"]) and len(" ".join(x["display"] for x in current)) > max_chars * 0.45):
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    # Avoid a dangling one-word cue by merging it backwards when it fits on two lines.
    merged: list[list[dict]] = []
    for cue in cues:
        if merged and len(cue) == 1 and len(" ".join(x["display"] for x in merged[-1] + cue)) <= max_chars * 1.5 \
                and not re.search(r"[.!?:]$", merged[-1][-1]["display"]):
            merged[-1] = merged[-1] + cue
        else:
            merged.append(cue)
    return merged


def to_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("content")
    parser.add_argument("work_dir")
    parser.add_argument("--ca-bundle", default=None, help="CA bundle for TLS-intercepting proxies")
    args = parser.parse_args()
    if args.ca_bundle:
        communicate._SSL_CTX = ssl.create_default_context(cafile=args.ca_bundle)

    content = json.loads(Path(args.content).read_text(encoding="utf-8"))
    work = Path(args.work_dir)
    (work / "lines").mkdir(parents=True, exist_ok=True)

    cursor = LEAD_IN
    placed, cues, steps, scenes = [], [], [], []
    for index, line in enumerate(content["lines"]):
        mp3 = work / "lines" / f"{index:02d}.mp3"
        # Optional "speak" segments: [spoken text, on-screen text or null]. Used where
        # the voice must say something differently from how it is written, such as
        # a verse reference that would otherwise be read as a clock time.
        segments = line.get("speak") or [[line["text"], None]]
        spoken = " ".join(seg[0] for seg in segments)
        words = asyncio.run(synthesize(spoken, content["voice"], content["rate"], content["pitch"], mp3))
        (work / "lines" / f"{index:02d}.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        clip_len = probe_duration(mp3)
        cursor += line.get("pauseBefore", 0.0)
        start = cursor
        words = attach_segments(segments, words)
        for cue_words in chunk_cues(words, content["subtitleMaxChars"]):
            cues.append({
                "start": round(start + cue_words[0]["start"], 3),
                "end": round(start + cue_words[-1]["end"] + CUE_TAIL, 3),
                "text": " ".join(w["display"] for w in cue_words),
                "line": index,
            })
        for step in line.get("steps", []):
            first = strip_punct(step.split()[0])
            hit = next((w for w in words if strip_punct(w["display"]) == first and w["start"] + start >= (steps[-1]["start"] + 0.01 if steps else 0)), None)
            steps.append({"text": step, "start": round(start + (hit["start"] if hit else 0), 3)})
        speech_end = start + (words[-1]["end"] if words else clip_len)
        placed.append({"index": index, "file": str(mp3.name), "start": round(start, 3), "clip": round(clip_len, 3),
                       "speechStart": round(start + (words[0]["start"] if words else 0), 3), "speechEnd": round(speech_end, 3)})
        cursor = speech_end + LINE_GAP

    # A cue never overlaps the next one.
    for a, b in zip(cues, cues[1:]):
        a["end"] = round(min(a["end"], b["start"] - 0.04), 3)

    final_start = placed[-1]["speechEnd"] + END_HOLD
    total = final_start + FINAL_CARD
    for i, (line, p) in enumerate(zip(content["lines"], placed)):
        scene_start = 0.0 if i == 0 else round(p["speechStart"] - 0.35, 3)
        scenes.append({"id": line["scene"], "start": scene_start, "line": i, "headline": line.get("headline", "")})
    scenes.append({"id": content["final"]["scene"], "start": round(final_start, 3), "line": None, "headline": ""})
    for a, b in zip(scenes, scenes[1:]):
        a["end"] = b["start"]
    scenes[-1]["end"] = round(total, 3)

    # Mix the placed clips into one narration track (no time-stretching).
    inputs, filters = [], []
    for k, p in enumerate(placed):
        inputs += ["-i", str(work / "lines" / p["file"])]
        delay = int(round(p["start"] * 1000))
        filters.append(f"[{k}:a]aresample={SAMPLE_RATE},adelay={delay}:all=1[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(placed)))
    filters.append(f"{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,apad,atrim=0:{total:.3f},"
                   f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=mono[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-c:a", "pcm_s24le", str(work / "narration.wav")], check=True)

    timeline = {
        "language": content["language"],
        "duration": round(total, 3),
        "finalStart": round(final_start, 3),
        "lines": placed,
        "scenes": scenes,
        "cues": cues,
        "steps": steps,
    }
    (work / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    srt = []
    for n, cue in enumerate(cues, 1):
        srt.append(f"{n}\n{to_srt_time(cue['start'])} --> {to_srt_time(cue['end'])}\n{cue['text']}\n")
    (work / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    print(json.dumps({"duration": timeline["duration"], "cues": len(cues), "lines": len(placed)}))


if __name__ == "__main__":
    main()
