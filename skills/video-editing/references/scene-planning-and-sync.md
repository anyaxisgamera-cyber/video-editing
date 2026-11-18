# Automatic scene planning and synchronization

The user does not provide timestamps. Derive every time from the script and from measured media, on one frame grid per video and language.

## 1. Divide the script into scenes

Read the whole script first and state its thesis. Then split it into scenes at changes of idea, place, time, speaker, or emphasis — usually one to three sentences each. Give each scene:

- a stable ID (`s01`, `s02`, …) shared by every language;
- its purpose (hook, context, claim, evidence, turn, resolution, call to action);
- narration text per language and optional on-screen text per language;
- the visual that illustrates its meaning (an asset ID from the register), source in-point, fit, focus point, and camera move;
- transition in, minimum on-screen time, and sound cues.

`plan/<video>/scenes.json`:

```json
{
  "video": "v01",
  "fps": 30,
  "lead_in_seconds": 0.6,
  "gap_seconds": 0.35,
  "tail_seconds": 1.5,
  "scenes": [
    {
      "id": "s01",
      "purpose": "hook",
      "narration": {"en": "Every journey starts with a single step.", "te": "ప్రతి ప్రయాణం ఒక్క అడుగుతోనే మొదలవుతుంది."},
      "on_screen": {"en": "", "te": ""},
      "visual": {"asset": "a01", "in": 2.0, "fit": "cover", "focus": [0.5, 0.45],
                 "move": {"type": "push_in", "amount": 0.06}},
      "transition_in": {"type": "fade", "seconds": 0.4},
      "min_seconds": 2.5,
      "hold_after_seconds": 0.3,
      "sfx": [{"asset": "a20", "at": "start", "offset_seconds": -0.15, "volume": 0.4}]
    }
  ],
  "music": {"asset": "a30", "volume": 0.3, "duck_to": 0.1, "fade_out_seconds": 2.0}
}
```

Moves: `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`, `tilt_up`, `tilt_down` (amount = zoom fraction or travel as a fraction of the frame). Transitions: `cut`, `fade` (crossfade), `fade_from_black`, `dip` (through black). Use richer transitions through Remotion's `@remotion/transitions` only when the style guide calls for them.

Framing per format: `fit` and `zoom` take one value or a per-format object, for example `"fit": {"9:16": "contain", "16:9": "cover"}` to letterbox a wide subject in the vertical cut, or `"zoom": {"16:9": 2.0, "9:16": 1.3}` to punch in on a small subject in a large still (zoom ≥ 1, centred on `focus`). Without `focus`, the focus point comes from `analyze_media.py`. When its crop check says the subject leaves a cover crop and you keep that crop after looking at the stills, record `"crop_reviewed": {"9:16": true}`; otherwise QC fails `subject_in_frame`. `on_screen_style` is `title`, `lower_third`, or `top`; `plan/<video>/style.json` may set one `look` (`contrast`, `saturation`, `brightness`, `warmth`, `vignette`) for every shot.

## 2. Measure narration

Put one narration file per scene and language at `narration/<video>/<lang>/<scene>.wav` (or `.mp3`, `.m4a`, `.flac`). Optional word timings from Whisper-style JSON (`segments[].words[]` with `word`, `start`, `end`), such as the output of `video_workbench.py transcribe`, go next to it as `<scene>.words.json`.

Never assume two languages take the same time. Translations differ in length, voices differ in rate, and scripts differ in how much fits on a caption line. Each language gets its own timing map.

## 3. Build the timing map

```bash
python3 "$SKILL_DIR/scripts/production.py" timing /path/to/production --video v01 --language te \
  [--fit gaps] [--max-chars 42] [--max-cps 17]
```

For each scene the tool:

1. measures the narration file and its speech window (leading and trailing silence removed by `silencedetect`);
2. sets the scene length to the largest of: speech + hold after + gap, `min_seconds`, and the reading time of its on-screen text;
3. converts all boundaries to frames once, so cuts never drift through rounding;
4. extends each visual by half of any crossfade on either side, and checks that the asset has enough source duration after its in-point (an image can hold any length; a short clip is an error, never a freeze);
5. places narration at the scene start plus the lead-in for the first scene, SFX relative to the scene start, and on-screen text inside the scene with a margin;
6. builds captions: word timings when a words file exists, otherwise words distributed across the measured speech window in proportion to their length. The method is recorded, so proportional timing is never presented as forced alignment;
7. writes music volume keyframes that duck under every narration window with attack and release ramps;
8. compares the total with the target duration.

Output: `timing/<video>/<lang>.timing.json` (frames and seconds), `captions/<video>/<lang>.srt`, and warnings for over-fast captions, short clips, and target misses.

## 4. Fit the target duration honestly

The narration length is fixed by the words and voice. To approach the target:

- `--fit gaps` adjusts the pauses between scenes and the holds within the allowed range (it never time-stretches narration);
- beyond that, shorten or lengthen the script for that language, or ask the user whether the target is a maximum or a guide.

Report the remaining difference per language instead of hiding it.

## 5. Synchronization rules

- Cut on scene boundaries, usually just before the narration that the new picture illustrates. Never reveal the answer before the narration says it.
- Captions follow the measured speech; split pages at punctuation and keep within the line-length and reading-rate limits for the language.
- Duck music under narration; let it breathe in gaps and at the end.
- Place a sound effect only where something on screen motivates it, aligned to the visual event, not to the cut by habit.
- When the style guide asks for cuts on the beat, move cut points to the nearest musical beat only within the scene's gap, never into speech.
- After rendering, check sync on the real output: strips around every cut, and the narration located in the final mix. `production.py render` cross-correlates every narration file with the mastered audio and fails the deliverable when any offset exceeds 10 ms. The measurement needs numpy; without it the report says "not measured" rather than passing silently.
