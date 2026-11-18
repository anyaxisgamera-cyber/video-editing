---
name: telugu-cinematic-edit
description: Reference-based recreation of a live-action cinematic edit with a Telugu script. Measures the reference scene by scene (shots, durations, cut / dissolve / dip / flash transitions, camera moves, grade, on-screen text, speech, music tempo, transition SFX), translates English to Telugu with Bible quotations copied exactly from licensed Telugu Bibles (never generated or altered), makes an ASR-verified Telugu voice-over and timed Telugu subtitles, uses licence-checked footage and music, matches the grade with LUTs, renders through the creative-workstation Cinematic composition, and validates the output (decode, black/freeze/silence, loudness, A/V sync, subtitles, speech, provenance). Use when the user supplies a reference video plus an English script and wants a realistic Telugu version in the reference's style and timing. Triggers include recreate this video in Telugu, Telugu voiceover, Telugu subtitles, Bible verse in Telugu, devotional video, reference edit breakdown, match this edit.
---

# Telugu cinematic edit — reference + English script in, verified Telugu film out

Set `SKILL_DIR` to this folder. Run Python with `/opt/cws-venv/bin/python`. Rendering uses the shared engine and
`render.py` of `../creative-workstation` (composition `Cinematic`; `Promo` is unchanged). Projects live outside git
under `/home/user/creative-studio/projects/<name>/`, assets in `/home/user/creative-studio/media-library/`.
Licences and availability of every model / corpus / asset source: `references/sources.md`.

## Hard rules

1. **Bible quotations are never translated, paraphrased or generated.** A scripture segment's Telugu is copied from a
   licensed corpus (`scripts/bible.py`, default IRV `tel2017`) for its reference; `validate` fails on any difference.
   An English quote that does not match its reference is reported to the user, not "fixed".
2. **No invented assets.** Every clip, music bed and SFX is a catalogued library asset with its licence; Mixkit
   `videoRestricted` (personal-use) items are skipped. If footage for an idea is not available under a usable licence,
   say so and choose another honest image — never a fake.
3. **Live action only.** Footage, real-edit transitions, restrained typography. No cartoon visuals, decorative motion
   graphics or effects the reference does not use.
4. **Nothing is reported done until `validate_output.py` passes** on the exported file.
5. Ask the user only for genuine decisions: the reference + script, a commercial-use decision on the voice (MMS is
   non-commercial), gated-model access, the Bible version if the audience expects a specific wording.

## Pipeline

```bash
S=$SKILL_DIR/scripts; W=$SKILL_DIR/../creative-workstation/scripts; P=/home/user/creative-studio/projects/<name>
PY=/opt/cws-venv/bin/python

# 1  Analyse the reference (≈ 14× real time on 4 CPUs, mostly OCR; --ocr-step 1.0 for long references)
$PY $S/reference_breakdown.py ref.mp4 $P/reference/breakdown --asr small --asr-lang en
#    → breakdown.json, BREAKDOWN.md (scene table), contact.jpg, shots/NNN.jpg, text/textNN.jpg (confirm OCR wording!)

# 2  Script: segment → translate narration → validate (scripture auto-filled from the corpus)
$PY $S/telugu_script.py segment script.en.txt $P/script/script.json --version tel2017 [--speak-reference]
$PY $S/telugu_script.py sheet $P/script/script.json          # what to translate + glossary (IRV terminology)
#    write translations.te.json {"s01": "…"} — natural, respectful Telugu (మీరు / ఆయన), glossary terms
$PY $S/telugu_script.py fill $P/script/script.json translations.te.json --by "translator"
$PY $S/telugu_script.py validate $P/script/script.json --labse   # must pass

# 3  Voice: per segment, clause-by-clause synthesis, best of N seeds by Telugu ASR CER (or --engine files for a VO artist)
$PY $S/telugu_tts.py synth $P/script/script.json $P/voice --engine mms --rate 0.92 --scripture-rate 0.85 --candidates 8

# 4  Assets: licence-checked footage/music/SFX into the library (see creative-workstation collect_mixkit.py), then
#    write plan.json: clips per segment (+ in-points), title_clips, music, sfx, credits

# 5  Recreate the reference's edit on the Telugu timeline (pacing, transitions, moves, LUT grade, text, SFX, ducking)
$PY $S/recreate.py $P --breakdown $P/reference/breakdown/breakdown.json --script $P/script/script.json \
    --voice $P/voice --plan $P/plan.json            # → timeline.json, timeline.te.srt/.ass, timeline.recreation.json

# 6  Render (chunked, resumable, mastered to −16 LUFS / −1.5 dBTP, self-verifying) and validate
$PY $W/render.py $P --timeline timeline.json --out $P/renders/<name>-1080p.mp4 --chunk-seconds 20
$PY $S/validate_output.py $P --video renders/<name>-1080p.mp4      # must pass
```

## What each tool measures / guarantees

- `reference_breakdown.py` — per-frame analysis at source fps: histogram cuts; dissolves confirmed by a linear-blend fit;
  dips/fades/flashes from luma runs and ramps; ORB+RANSAC camera motion per shot (zoom %, pan/tilt in frame widths,
  roll, handheld jitter); grade (key, contrast, black/white, saturation, warmth, tint, split tone, palette, Lab stats);
  letterbox; text events by screen region (word readings voted across frames) with entrance style; Whisper speech
  with word times; tempo/beats, cut-on-beat ratio; hits/whooshes at transitions; loudness; derived atmosphere labels.
  Scored by `tests/test_breakdown.py` against a ground-truth reference built by `tests/make_ground_truth.py`.
- `telugu_script.py` — segmentation with scripture detection, exact corpus fill, glossary, validation (Telugu
  ratio, no Latin left, length ratio, LaBSE meaning score, exact verse match), subtitle cues from exact clause
  timings (≤ 2 lines × 30 aksharas, reading-rate check), SRT/ASS.
- `telugu_tts.py` — MMS Telugu (non-commercial flag), espeak, or human recordings; ASR round-trip CER per segment
  with a second-opinion model; 48 kHz levelled WAVs + `voice.json` with clause timings.
- `recreate.py` — reference pattern → shots per segment (content-matched clips, no repeated footage), transitions
  in the reference's order and length, digital move = reference move − the clip's own measured motion, LUT
  (Reinhard Lab transfer toward the reference look), verse reference cards, title card with the reference's entrance,
  whooshes where the reference has them, music bed ducked under the voice.
- `validate_output.py` — see its docstring; writes `<video>.validation.json` and `.VALIDATION.md`.

## Limits (measured, not hidden)

- MMS Telugu voice is 16 kHz VITS (clear but band-limited, CC-BY-NC). For commercial or premium delivery use a human
  VO (`--engine files`) or unlock Indic Parler-TTS (Apache-2.0) on Hugging Face.
- Tesseract's Telugu OCR is approximate: confirm on-screen Telugu wording from `text/*.jpg`.
- Dips into near-black shots are measured shorter than they are (the fade-in disappears into the dark shot).
