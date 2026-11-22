# AXHARRY FINAL: delivery and QA report

Date: 2026-11-22. There are 8 masters: English and Telugu, each in 9:16 and 16:9, each at 1080p and 4K. All of them are in `/mnt/user-data/outputs`, and each copy there is byte-identical to the validated file.

## Deliverables

| File | Size (px) | Frames | Duration | File size | SHA-256 (first 16) | In outputs |
|---|---|---|---|---|---|---|
| AXHARRY_ENGLISH_FINAL_9x16_1080p.mp4 | 1080x1920 | 1923 | 64.10 s | 71M | `8f85af3aaec7c724` | yes |
| AXHARRY_ENGLISH_FINAL_9x16_4K.mp4 | 2160x3840 | 1923 | 64.10 s | 195M | `c2ba7eb0a0a0f6fd` | yes |
| AXHARRY_ENGLISH_FINAL_16x9_1080p.mp4 | 1920x1080 | 1923 | 64.10 s | 76M | `416e84fc3a57a3f3` | yes |
| AXHARRY_ENGLISH_FINAL_16x9_4K.mp4 | 3840x2160 | 1923 | 64.10 s | 223M | `03f1d520e9d37c20` | yes |
| AXHARRY_TELUGU_FINAL_9x16_1080p.mp4 | 1080x1920 | 2389 | 79.63 s | 86M | `1b51a4be1653c6a7` | yes |
| AXHARRY_TELUGU_FINAL_9x16_4K.mp4 | 2160x3840 | 2389 | 79.63 s | 238M | `2379cd4c081de99a` | yes |
| AXHARRY_TELUGU_FINAL_16x9_1080p.mp4 | 1920x1080 | 2389 | 79.63 s | 94M | `d63a69fe96d61ab8` | yes |
| AXHARRY_TELUGU_FINAL_16x9_4K.mp4 | 3840x2160 | 2389 | 79.63 s | 276M | `9b6ac90b7d3812f8` | yes |

Also delivered:
- `AXHARRY_ENGLISH_FINAL.srt` (54 cues) and `AXHARRY_TELUGU_FINAL.srt` (57 cues). Both are generated from the on-screen caption timeline, so they match the captions exactly, and they are identical to the SRTs verified earlier.
- `AXHARRY_FOOTAGE_CREDITS.md`, covering sources, licences, attribution text and cautions.

## Voices

The voices are unchanged and nothing was substituted.

- **English:** the approved reference-voice narration (`work/en-ref`). Lines 1–15 are the original recording. Line 16 ("From now on, I share my knowledge.") is the Seed-VC conversion approved earlier.
- **Telugu:** the saved Daniel voice (ElevenLabs premade voice `onwK4e9ZLuTAKqWW03F9`), as recorded in `brand/voices.json`.
- **Protected assets are unchanged:**
  - Reference audio sha `034dae48fd0f…`
  - Logo sha `e51c8df7b7a9…`
  - The approved `AXHARRY_ENGLISH.mp4` is still sha `a68b38f25f5e85ac5ec7…`, both in `output/` and in the outputs folder.

## Checks performed and results

1. **Workbench validation** (`video_workbench.py render-ffmpeg`) on all 8 masters: 11 of 11 checks passed for each one. The checks are video and audio streams, width, height, duration, fps, sample rate, codec, pixel format, full decode, and loudness.
2. **Loudness:**
   - English: integrated −14.07 LUFS, true peak −1.60 dBTP.
   - Telugu: integrated −14.27 LUFS, true peak −1.52 dBTP.
   - The target was −14 LUFS with a true-peak ceiling of −1.5 dBTP; the true peaks stay below it.
3. **Narration sync** (`build/qa_kinetic.py`):
   - **English 9:16 and 16:9:** 177 of 177 words were matched by speech recognition, and every caption word falls on speech. Median caption-onset error is 0.00 s (90th percentile 0.02 s), and transcript-to-script similarity is 1.00.
   - **Telugu 9:16**, transcribed with Whisper large-v3-turbo:
     - Speech is present under all 123 caption words.
     - Transcript-to-script similarity is 0.885, consistent with the 0.893 measured on the clean narration.
     - Median onset error is 0.06 s.
     - The small Whisper model cannot transcribe Telugu, so that run's text score is not meaningful and is not used here.
4. **Black frames** (blackdetect, ≥0.15 s): none in any of the 8 masters.
5. **Frozen frames** (freezedetect, ≥1.2 s): the only hits are the intentional end-card hold, at about 62.5 s in English and about 78 s in Telugu.
6. **4K audio:** the decoded audio of each 4K master is bit-identical to its 1080p master, which went through the sync checks.
7. **Visual check:** for every master I viewed one frame from the middle of every shot, plus the end card. In each one:
   - the footage plays;
   - captions are timed to the voice;
   - the hook badge and logo badge do not overlap;
   - Telugu glyphs render correctly;
   - the credits appear on the end card.
8. **Source cuts inside clips:** I ran scene detection on all 24 cut clips across the span each shot uses. No clip contains a cut from the source film. Two in-points were moved during QA to achieve this.
9. **Telugu 16:9 4K was rendered in two halves**, frames 0–1194 and 1195–2388, because a full render takes longer than one job may run here. The halves were joined without re-encoding. I checked the result for frame count (2389), a clean full decode, and visual continuity at the join, then it went through the same validation as the others.

## Edit summary

- 16 lines and 29 shots (English) or 32 shots (Telugu). 22–23 of those shots are licensed film footage; the rest are the original AXHARRY anime art, kept for the anime look and for the gold finale.
- Footage plays muted. Short source shots are slowed to no less than 0.7× speed to fill a beat, and no clip repeats within a line.
- Effects carried over: crash zoom, chromatic split, whip blur, speed lines, halftone, grain, light leaks, and the crimson grade that turns gold.
- In 16:9, footage fills the frame, captions sit in the lower third, the hook is at the top and the logo is at the bottom centre.

## Limitations and open items

- **Telugu sync measurement:** speech recognition for Telugu is weaker, so the Telugu sync check is less exact than the English one.
- **Caligari source quality:** the only source is 320×240, so its two shots are softer than the rest.
- **Before monetizing:** see `FOOTAGE_CREDITS.md` for the cautions about Metropolis (rights outside the US) and the Superman trademark.
- **Not used:** Classroom of the Elite clips were never supplied and have no reuse licence. The anime and studio licensing portals only offer licensing inquiries and have no downloadable footage. openimages.eu was unreachable.
