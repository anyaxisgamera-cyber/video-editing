# James 1:14 — Understanding Temptation (English + Telugu Shorts)

Two separate vertical devotional shorts built with this repository's `video-editing` workflow:
workbench `init` / `init-motion` scaffolding, a typed Remotion composition, a workbench
`render-ffmpeg` plan for the final mix and mux, and workbench `validate` plus review sheets.

| Deliverable | Language | Narration voice | Reference |
|---|---|---|---|
| `output/James_1_14_English.mp4` | English | `en-US-AvaNeural` | James 1:14 (NIV) |
| `output/James_1_14_Telugu.mp4` | Telugu | `te-IN-ShrutiNeural` | యాకోబు 1:14 |

Media (plates, audio, renders) is generated, not committed; see the repository `.gitignore`
and `AGENTS.md`. Everything is reproducible from the files here.

## Layout

```
content/{en,te}.json      script lines, headlines, verse text, final message, voice
build/narrate.py          per-line neural TTS + word boundaries -> narration.wav, timeline.json, subtitles.srt
build/music.py            original synthesized ambient bed (deterministic)
build/plates.py           SD-Turbo symbolic stills (generate) and 1080x1920 finishing (finish)
build/props.py            content + timeline -> motion/props/<lang>.json, stages fonts
build/mix.py              voice/music premix with side-chain ducking, measured loudnorm, render plan
build/qa.py               VAD subtitle coverage + Whisper ASR check on the delivered MP4
plates.selection.json     which seed was chosen for each scene
motion/                   Remotion project (template from init-motion) + ScriptureShort composition
editorial-plan.json       brief, beats, and track ownership
```

## Rebuild

Python dependencies (in a virtualenv): `edge-tts numpy faster-whisper` and, for plates only,
`torch diffusers transformers accelerate`. Behind a TLS-intercepting proxy, pass `--ca-bundle`.

```bash
WB=../../skills/video-editing/scripts/video_workbench.py
python build/plates.py generate work/plates
python build/plates.py finish work/plates plates.selection.json motion/public/media
(cd motion && npm install)
for L in en te; do
  python build/narrate.py content/$L.json work/$L
  python build/music.py work/$L/music.wav "$(python -c "import json;print(json.load(open('work/$L/timeline.json'))['duration'])")"
  python build/props.py content/$L.json work/$L/timeline.json motion/props/$L.json
  (cd motion && npx remotion render src/index.ts ScriptureShort ../output/$L/picture.mp4 \
     --props=props/$L.json --codec=h264 --crf=12 --pixel-format=yuv420p --muted)
  python build/mix.py $L
  python3 $WB render-ffmpeg work/$L/render-plan.json
  python build/qa.py $L output/<deliverable>.mp4 work/$L/qa.json
done
```

Add `--browser-executable=/path/to/chrome-headless-shell` to Remotion commands where Remotion
cannot download its own browser.

## Notes

- Narration is synthesized at each voice's default rate and never time-stretched. The Telugu
  script is longer when spoken, so the Telugu cut runs longer than the English one.
- On-screen verse text: NIV (2011) for English; the Telugu card uses the traditional Telugu
  Bible wording of James 1:14. Spoken lines are the supplied scripts, verbatim.
- Plates are AI-generated symbolic imagery without people; they were chosen by eye per scene.

## v2 — kinetic-typography cut (current deliverables)

Rebuilt to follow a reference kinetic-typography short (studied with
`skills/analyze-video-editing`): alternating cream/black frames, bold tight sans
(Inter Tight / Noto Sans Telugu), words revealed on their spoken timestamps with the
key word in red (glowing on black), isolated objects, a pinned checklist card, circle
wipes, arc swooshes, push-ins, a soft 92 BPM bed, and whooshes/pops synced to cuts.
Every narration word appears on screen exactly once, so the kinetic text is the caption
track (SRT sidecars are also written). The v1 lavender `ScriptureShort` remains intact.

Voice: ElevenLabs `eleven_v4`, voice "Brian" (premade), one request per language with
character timestamps (`build/narrate_el.py`; reads `ELEVENLABS_API_KEY`, any placeholder
works behind a key-injecting proxy). Word starts are corrected by a measured −0.15 s.

```bash
for L in en te; do
  python build/narrate_el.py content/$L.json work/$L-kinetic
  python build/kinetic_props.py content/$L.json work/$L-kinetic motion/props/$L-kinetic.json
  python build/kinetic_audio.py motion/props/$L-kinetic.json work/$L-kinetic
  (cd motion && npx remotion render src/index.ts KineticShort ../output/$L-kinetic/picture.mp4 \
     --props=props/$L-kinetic.json --codec=h264 --crf=12 --pixel-format=yuv420p --muted)
  python build/mix.py $L --work work/$L-kinetic --props motion/props/$L-kinetic.json \
     --picture output/$L-kinetic/picture.mp4 --tag $L-kinetic
  python3 $WB render-ffmpeg work/$L-kinetic/render-plan.json
  python build/qa_kinetic.py $L output/<deliverable>.mp4 motion/props/$L-kinetic.json work/$L-kinetic/qa.json
done
```

Objects (`motion/public/media/obj-*.png`) are SD-Turbo renders on a plain backdrop,
matted with `build/cutout.py light` (no learned matting model); picks are in
`objects.selection.json`.
