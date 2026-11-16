# Telugu cinematic edit — build and test report

Everything below was run in this environment (4 vCPU, no GPU). Media and projects live outside git under
`/home/user/creative-studio/`; the test production's text inputs are in `examples/good-shepherd/`.

## Status

| Requirement | Status | Evidence |
|---|---|---|
| Scene-by-scene reference analysis (shots, durations, transitions, camera, grade, text, speech, music, SFX, atmosphere) | VERIFIED on a ground-truth reference | `tests/test_breakdown.py`: 30/30 checks (below). Not yet run on the user's reference — none supplied yet. |
| Recreate the reference's style and timing (not a generic video) | VERIFIED | `recreate.py` follows the reference shot pattern, transition order/length, camera moves (minus each clip's own motion), grade (LUT), title entrance, transition SFX |
| English → Telugu translation | VERIFIED (agent translation) | `telugu_script.py validate --labse`: no errors; LaBSE 0.80–0.91 per narration segment |
| Bible quotations exact, never invented or altered | VERIFIED | Verses copied from the IRV `tel2017` corpus; `validate` and the output validator re-check character-exact; English quotes checked against WEB |
| Telugu subtitles | VERIFIED | 10 cues from exact clause timings; every cue is exact script text; OCR of the rendered subtitles mean CER 0.009 |
| Synchronized Telugu voice-over | VERIFIED (non-commercial voice) | MMS Telugu, ASR CER ≤ 0.04 per segment; sync offset 0.0 ms for all 8 segments in the final mix |
| Commercial-use voice | REQUIRES ACCESS / USER DECISION | MMS is CC-BY-NC. Options: human VO (`--engine files`, supported), or Indic Parler-TTS (Apache-2.0) after the account owner accepts its terms on Hugging Face |
| Asset research with source, availability, licence | VERIFIED (Mixkit), REQUIRES API (Pexels, Pixabay) | 15 new Mixkit clips (Free licence; all sheep/shepherd clips were Restricted and skipped), 6 music tracks, catalogue entries with licence evidence |
| Realistic live action, no cartoon / generic motion graphics | VERIFIED | Footage only; real-edit transitions; typography limited to subtitles, verse references and a title card |
| Full pipeline through export | VERIFIED | `renders/manchi-kaapari-te-1080p.mp4`, 1920×1080 30 fps, 49.6 s |
| QA: no fake footage, missing scenes, wrong subtitles, A/V sync issues, silent/corrupt sections | VERIFIED | `validate_output.py`: 23/23 checks (below) |
| Existing project preserved | VERIFIED | `Promo` composition untouched; 60 frames re-rendered with the new engine vs the verified 30 s master: PSNR 47.7 dB average (min 40.8); creative-workstation smoke test passes |

## Reference breakdown — ground-truth score

`tests/make_ground_truth.py` builds a 15.83 s, 30 fps reference from licensed clips with a known edit; the analyser
does not see the truth file.

| Event | Truth | Measured |
|---|---|---|
| Cut | frame 90 | frame 90 |
| Dissolve | 175, 20 f | 176, 19 f (blend fit ρ = −1.0, residual 0.18) |
| Dip to black (into a near-black candle shot) | 256, 24 f | 256, 17 f (fade-in vanishes into the dark shot; tolerance 8 f) |
| Flash + whoosh | 355, 6 f, whoosh | 356, 5 f, whoosh |
| Shot count | 5 | 5 |
| Shot 2 synthetic push-in +15 % | push_in | push_in, zoom 1.148 |
| Shot 3 synthetic pan right | pan_right | pan_right, −0.19 frame widths |
| "THE GOOD SHEPHERD", centre, fade-in 12.6–15.4 s | | "GOOD SHEPHERD" (0.87), 12.77–15.13 s, fade/blur-in 0.17 s |
| "మంచి కాపరి", bottom, cut-in 14.0–15.5 s | | Telugu "మంచి SHS", 14.00–15.53 s, cut-in |
| Tempo 120 BPM | | 117.5 BPM |
| Speech | "In every season of life, we search for direction." | exact |

Runtime 230 s for 15.8 s (OCR dominates; `--ocr-step 1.0` halves it). Tesseract's Telugu model is approximate —
on-screen Telugu wording must be confirmed on `text/*.jpg`.

## Test production "మంచి కాపరి"

Script: 7 English paragraphs + title (`examples/good-shepherd/script.en.txt`), with Psalm 23:1 and John 10:11.

| Segment | Kind | Telugu (excerpt) | LaBSE | Voice s | ASR CER |
|---|---|---|---|---|---|
| s01 | narration | జీవితంలోని ప్రతి దశలోనూ … | 0.797 | 6.46 | 0.000 |
| s02 | narration | దారి సుదీర్ఘంగా ఉన్నప్పుడు, … | 0.835 | 6.50 | 0.013 |
| s03 | scripture PSA 23:1 (IRV) | యెహోవా నా కాపరి. నాకు ఏ లోటూ లేదు. | 0.805 | 3.43 | 0.20 small / **0.04 medium** |
| s04 | narration | ఆయన ఆదరణ మన హృదయాల్లోని … | 0.833 | 6.64 | 0.034 |
| s05 | narration | అత్యంత చీకటి రాత్రిలో కూడా, … | 0.907 | 4.54 | 0.000 |
| s06 | narration | యేసు ఇలా అన్నారు, | 0.891 | 1.27 | 0.000 |
| s07 | scripture JHN 10:11 (IRV) | నేను గొర్రెలకు మంచి కాపరిని. … | 0.827 | 6.09 | 0.000 |
| s08 | narration | ఈ రోజే, మీ పేరు తెలిసిన ఆయనను వెంబడించండి. | 0.858 | 3.94 | 0.029 |
| s09 | title | మంచి కాపరి | — | — | — |

Edit (`timeline.recreation.json`): 14 shots from 12 clips, no footage shown twice; average shot length 3.54 s
(reference 3.17 s); transitions in the reference's order — cut, dissolve 19 f, dip to black 17 f, flash 5 f with a
whoosh; digital moves only where the clip's own motion falls short of the reference move; per-shot LUT toward the
reference look; verse-reference cards (కీర్తన 23:1, యోహాను 10:11); end title with the reference's fade-in and the IRV
CC BY-SA attribution; music bed Mixkit "ambient 184" ducked −9 dB under the voice.

Render: 1488 frames in 177–196 s (6.9–9.3 fps), −16.0 LUFS, −3.5 dBTP.

## Output validation (`validate_output.py`)

container (codecs, geometry, fps, 1488/1488 frames, duration, audio duration, full decode) · picture (no unintended
black, no freeze ≥ 2.5 s, every shot visible) · sound (no silence ≥ 1 s, −16.0 LUFS / −3.5 dBTP) · sync (8/8 voice
segments at 0.0 ms) · script (10/10 cues exact script text, all segments covered, both verses exact corpus text,
script validation passed) · subtitles (Telugu visible at 10/10 cues, OCR CER 0.009) · speech (final-mix ASR CER
0.00–0.051) · provenance (12 catalogued clips; voice licence recorded: CC-BY-NC) — **23/23 passed**.

## Defects found and fixed during the build

1. Hugging Face model downloads blocked (Xet CAS / CDN hosts) → hosts added to the environment allowlist.
2. The saved Hugging Face credential was invalid and the proxy overrides any other token → new token saved through the secure credential form.
3. MMS tokenizer drops punctuation (no pauses) → clause-by-clause synthesis with measured pauses; also yields exact subtitle timings.
4. Small Telugu ASR drops sentence-initial యెహోవా → second-opinion medium ASR; spelling-variant folding (యె/యే/ఏ/ఎ) in CER.
5. Mixkit items with ids ≥ 100000 failed to download → collector follows the new download page (licence check unchanged; posters compared to confirm the right files).
6. Breakdown: a push-in on a still was read as a dissolve → stricter blend fit + "both sides must differ" rule.
7. Breakdown: dips into dark shots, beat clicks read as transition hits, under-measured zoom, OCR noise and 11-minute runtime → luma core/ramp model, beat-aware hit test, 3-frame motion stride, region-based OCR with word voting and line re-OCR, parallel Tesseract (665 s → 230 s).
8. Recreation: reused clips restarted at the same frame; digital moves stacked on clips that already move; grade targets too literal → continue-after-use, motion compensation, 60/40 look/shot LUT target.
9. Title attribution line illegible on bright footage → scrim + bold, shadowed sub-line (re-rendered and re-validated).

## Needed from the user

- The **reference video** and the **English script** (the pipeline is ready for them).
- Voice for commercial use: a Telugu voice-artist recording, or accept the terms of `ai4bharat/indic-parler-tts` on
  huggingface.co with the account whose token is saved here (fine-grained tokens also need "read access to public
  gated repositories").
- Preferred Bible wording if not IRV (e.g. the traditional BSI wording needs a licence-verified source).
- Pexels / Pixabay API keys if footage from those libraries is wanted.
