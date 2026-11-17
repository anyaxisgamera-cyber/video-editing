# Multiple videos, languages, and delivery formats

The user specifies how many videos, the duration of each, and the languages for each. Treat each (video, language) pair as its own edit that shares a plan, and each (format, resolution) as its own render with its own checks.

## The deliverable matrix

`production.py init` writes `production.json` with one entry per video × language × format × resolution:

```text
deliverables/<video>/<lang>/<video>-<lang>-<format>-<resolution>.mp4
deliverables/<video>/<lang>/<video>-<lang>-<format>-<resolution>.validation.json
```

Format keys use a hyphen in file names (`9x16`, `16x9`). Videos are independent: separate scripts, scene plans, style guides when appropriate, timing maps, and statuses. Shared brand elements live in one place and are reused.

## Default delivery formats

Unless the user says otherwise:

| Format | 1080p | 4K (when feasible) |
|---|---|---|
| 9:16 vertical | 1080×1920 | 2160×3840 |
| 16:9 widescreen | 1920×1080 | 3840×2160 |

Reframe for each format; do not letterbox one into the other. For every scene, choose a focus point and check the crop in both orientations. A scene may need a different asset in 9:16 when the subject does not survive the crop.

Keep text and captions in each format's safe area. Vertical platforms overlay their own interface near the bottom and right edge, so captions sit higher in 9:16 than in 16:9.

## 4K feasibility

4K is delivered "wherever technically feasible". Decide per video and format with evidence:

```bash
python3 "$SKILL_DIR/scripts/production.py" feasibility /path/to/production --video v01
```

The report gives, for each format, the largest upscale any visual asset needs after cover-cropping. Then:

- **native** (no upscale): deliver 4K.
- **upscaled**: tell the user the factor and the scenes affected, and deliver 4K only if they accept it, or replace the assets with higher-resolution sources. Until `upscale_accepted: true` is set on that deliverable in `production.json`, `production.py status` reports it as `upscaled`, not `validated`.
- Graphics-only scenes are resolution-independent and do not limit 4K.

Measure render time on a representative range at 4K before committing to the full matrix, and report it.

Cropping a landscape source to 9:16 always enlarges it: a 1920×1080 clip covering a 1080×1920 frame needs ×1.78 even at 1080p. Prefer native vertical footage for 9:16 scenes when the register has it, and report the factor when it does not.

## Adapting each language

Adapt rather than literally translate:

- **Narration.** Use a natural translation in the register the audience expects. Keep names, numbers, and quotations faithful. Use a glossary so key terms stay consistent across videos. Quotations from fixed texts (scripture, laws, published works) must come from a licensed published translation, not a new translation.
- **Pronunciation.** Keep a per-language lexicon of names, brands, and loanwords with the intended pronunciation. Apply it through the voice's phoneme or SSML controls, or respell the word in the narration text sent to the voice. Listen to every name. Where possible, check intelligibility with speech recognition in that language.
- **Voice.** Choose a voice per language with a licence that fits the deliverables (commercial or not). Record its licence in the register. Ask before voice cloning ([approvals.md](approvals.md)).
- **Captions.** Use per-language line length and reading-rate limits (`--max-chars`, `--max-cps`). Scripts with large glyphs, such as Indic, Thai, and CJK, need shorter lines than Latin. Right-to-left scripts need `direction: rtl` in the language entry.
- **On-screen text.** Re-set every title for the language's font and length, check it does not overflow, and keep numbers and dates in local conventions.
- **Cultural context.** Check imagery, gestures, colours, examples, and humour for the audience. Replace scenes that do not carry the meaning across cultures, and note those replacements in the report.
- **Timing.** Build and fit a timing map per language from that language's measured narration. Never reuse another language's cut points.

Each language entry in `production.json` can set its caption font (`font.family`, `font.file`), `direction`, `max_chars`, and `max_cps`.

## Review per language and format

Review each (video, language, format) on its own: contact sheet, caption stills, transition strips, and a listen-through. The checks in [quality-gates.md](quality-gates.md) apply per deliverable.
