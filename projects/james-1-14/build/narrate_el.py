"""ElevenLabs narration with word timing for the kinetic edit.

Usage: python build/narrate_el.py content/en.json work/en-kinetic [--ca-bundle PATH]

Voices the whole script in ONE request (natural prosody across sentences) using
/v1/text-to-speech/{voice}/with-timestamps, then converts the character
alignment into word timings. The API key is read from ELEVENLABS_API_KEY; in a
proxy-injected environment any placeholder value works.

Writes: narration.mp3, narration.wav (48 kHz mono), alignment.json,
        words.json (display words with times and line index), subtitles.srt
Spoken text may differ from on-screen text through a line's "speak" segments
(e.g. a verse reference read aloud as words but shown as "1:14").
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import urllib.request
from pathlib import Path


def tts(text: str, voice: str, model: str, settings: dict, ca: str | None) -> dict:
    body = json.dumps({"text": text, "model_id": model, "voice_settings": settings}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
        data=body,
        headers={"Content-Type": "application/json", "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "proxy-injected")},
    )
    ctx = ssl.create_default_context(cafile=ca) if ca else None
    with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
        return json.load(resp)


def to_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("work_dir")
    ap.add_argument("--ca-bundle")
    ap.add_argument("--reuse", action="store_true", help="reuse an existing alignment.json/narration.mp3")
    args = ap.parse_args()

    content = json.loads(Path(args.content).read_text(encoding="utf-8"))
    el = content["elevenlabs"]
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # Build the spoken text and remember which span of it belongs to which display token.
    spoken_parts: list[str] = []
    spans: list[dict] = []  # {start, end (char offsets in spoken text), display, line, merge}
    cursor = 0
    for li, line in enumerate(content["lines"]):
        segments = line.get("speak") or [[line["text"], None]]
        for spoken, display in segments:
            if spoken_parts:
                sep = "\n\n" if not spans or spans[-1]["line"] != li else " "
                spoken_parts.append(sep)
                cursor += len(sep)
            if display is not None:
                spans.append({"start": cursor, "end": cursor + len(spoken), "display": display, "line": li})
            else:
                for m in re.finditer(r"\S+", spoken):
                    spans.append({"start": cursor + m.start(), "end": cursor + m.end(), "display": m.group(0), "line": li})
            spoken_parts.append(spoken)
            cursor += len(spoken)
    spoken_text = "".join(spoken_parts)

    if args.reuse and (work / "alignment.json").exists():
        alignment = json.loads((work / "alignment.json").read_text(encoding="utf-8"))
    else:
        result = tts(spoken_text, el["voice_id"], el["model_id"], el.get("voice_settings", {}), args.ca_bundle)
        (work / "narration.mp3").write_bytes(base64.b64decode(result["audio_base64"]))
        alignment = result["alignment"]
        (work / "alignment.json").write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")

    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    if "".join(chars) != spoken_text:
        raise SystemExit("Alignment characters differ from the submitted text; refusing to guess word timing.")

    lead = float(content.get("leadIn", 0.35))
    # Measured on this pipeline's output (Whisper word onsets and energy onsets on
    # the final mix): ElevenLabs character start times run ~0.13-0.19 s late, while
    # end times are within 0.05 s. Starts are corrected by this offset.
    start_offset = float(el.get("startOffset", -0.15))
    words = []
    for span in spans:
        idx = [i for i in range(span["start"], span["end"]) if chars[i].strip()]
        words.append({
            "display": span["display"],
            "line": span["line"],
            "start": round(max(lead + starts[idx[0]] + start_offset, words[-1]["end"] if words else 0.0), 3),
            "end": round(lead + ends[idx[-1]], 3),
        })

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "narration.mp3"),
                    "-af", f"adelay={int(lead * 1000)}:all=1,aresample=48000", "-ac", "1", "-c:a", "pcm_s24le",
                    str(work / "narration.wav")], check=True)
    (work / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")

    # Sidecar subtitles: one cue per script sentence-ish chunk, from real word times.
    cues, current = [], []
    for w in words:
        current.append(w)
        text = " ".join(x["display"] for x in current)
        if re.search(r"[.!?:,]$", w["display"]) and len(text) > 14 or len(text) > content["subtitleMaxChars"]:
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    srt = []
    for n, cue in enumerate(cues, 1):
        nxt = cues[n][0]["start"] - 0.04 if n < len(cues) else cue[-1]["end"] + 0.4
        srt.append(f"{n}\n{to_srt_time(cue[0]['start'])} --> {to_srt_time(min(cue[-1]['end'] + 0.3, nxt))}\n"
                   + " ".join(x["display"] for x in cue) + "\n")
    (work / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    print(json.dumps({"words": len(words), "speech_end": words[-1]["end"], "chars": len(spoken_text)}))


if __name__ == "__main__":
    main()
