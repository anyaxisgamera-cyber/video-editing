# AXHARRY reference-voice deliverables: voice similarity and QA report

All measurements were taken locally with networking disabled. Nothing was uploaded.

## Deliverables (1080p)

| File | Properties | SHA-256 |
|---|---|---|
| `AXHARRY_ENGLISH_REFERENCE_VOICE.mp4` | 1080×1920, 30 fps, h264 + aac 48000 Hz 2 ch, 64.10 s, 79,248,925 bytes | `28a40ba16c9d8a4a2a25019362293285b0c2cc9545c6566128c92fed67ccee41` |
| `AXHARRY_TELUGU_REFERENCE_VOICE.mp4` | 1080×1920, 30 fps, h264 + aac 48000 Hz 2 ch, 79.40 s, 97,283,194 bytes | `08d1bd14a7ac070aecec880d0baa937de84b0e2ce047863421ec1287d4b951b8` |

Approved masters `AXHARRY_ENGLISH.mp4` and `AXHARRY_TELUGU.mp4` and the original reference audio are unchanged
(hashes re-verified before and after every sandboxed run).

## Voice similarity (SpeechBrain ECAPA cosine vs `(256k)_vocals_mixed.m4a`)

| Audio | Similarity |
|---|---:|
| Ceiling: reference first half vs second half (same speaker) | 0.923 |
| Telugu, Adam source (before) | -0.021 |
| **Telugu, converted** | **0.562** |
| English line 16, Adam source (before) | 0.045 |
| **English line 16, converted** | **0.650** |
| English lines 1–15 | the original recording itself (not converted) |

Interpretation: conversion moved both voices from unrelated to Adam (about 0.0) to clearly toward the reference
(0.56 Telugu, 0.65 English), but below the same-recording ceiling (0.92). **This is not an exact voice match.** The reference
contains English speech only; Telugu identity is a cross-language conversion of it.

## Intelligibility

- English line 16 (converted): Whisper heard "From now on, I share my knowledge." (similarity 1.00).
- English full master: transcript similarity 1.000 to the script; all 177 words matched.
- Telugu converted, per-line Whisper large-v3-turbo vs script: mean **0.756**
  (Adam source: 0.931). Pronunciation clarity is reduced, most on lines 9, 15 and 16.

| Line | Similarity | Heard |
|---:|---:|---|
| 1 | 0.66 | చెపు పోకన నిపు నూడి కి అగా మే ధావి కి మాద్యా తేరా ఏం టోని కింసా. |
| 2 | 0.81 | నిపునుడు ఒకా విషయంగురంచి తిలిసుకు వాలసినా దంతా నిర్సుకుంతారు. |
| 3 | 0.94 | కాని మేధావి మేధావి ఆ సమాచారాని ఉపయోగించి నియమాలనే పూర్తిగా తిరగాస్తాదు. |
| 4 | 0.84 | చాలామంది జ్నానాని సమాజన్లో ఇమిడి పోరాని కేవారకుంతారు. |
| 5 | 0.71 | పుయోగం కోసం దభు కోసం గోసం గోరవం కోసం చేదు తారో |
| 6 | 0.88 | వేరోకరి చేతిలో మంచి పనిముట్లుగా మారడానికే వాలు సిక్షన అపొందు తునారో. |
| 7 | 0.88 | కాని నన్ను ఆప్పాని ముర్టును పట్టికునే చేయిగా పేంచారు. |
| 8 | 0.83 | ప్రపంచచిరిట్రగురంచిగాని సాఇంస అందం గురంచిగాని నాకు పర్తింపు లేదు. |
| 9 | 0.44 | విగె ాధీ పయాత్యం మాత్రయాట్రెంం కముం దూద్డింట్కానాగుాగాండుం. |
| 10 | 0.84 | కున్ని పుస్తకాలు బట్టి పట్టినంత మాత్రాన నుగు తెలివాఇన వాడిగాన కుండునావా |
| 11 | 0.73 | అసలేన అగ్నాన వంటే వక మంచి మనిశితో చాద్డపని చేంసడాని కి ఏ బటం వకాలో కచ్చితంగా తిస్కోనా. |
| 12 | 0.86 | నిను కంట్రోల చేరాని కి నేను నిస్నే హితుని కావాసిన ఆవాస్రం లేదు. |
| 13 | 0.78 | నువు దేని కాయపరతావ అవి తేలి సేచాలు |
| 14 | 0.77 | యప్పటికి విలువకోలు పోని ఏకాఇకా కవింసి సమాచారమే |
| 15 | 0.57 | ఇప్డు ఇగదిలో అందరికెండే దనవం తునీ నేనాయే ఇకాన్టినాసుగివాదివారాడిసుగి. |
| 16 | 0.55 | కపాి నా క్నాన నాన ననిట పంసు కనుటం. |

Parameter test (line 1): style strength 0.7 / 30 steps gave 0.73 intelligibility and 0.514 similarity; 0.5 / 50 steps gave
0.69 and 0.514; 0.3 / 50 steps gave 0.69 and 0.495. Lower style strength did not improve clarity, so 0.7 / 30 steps was kept.

## Timing and sync

- Conversion preserved length exactly (Telugu 76.000 s, English line 2.790 s). Speech-envelope correlation with the source:
  Telugu 0.919, English line 0.965.
- English captions realigned to the original recording: 170/170 words aligned by
  ASR, 0 interpolated; caption onset offset median 0.0 s, 90th percentile 0.02 s.
- Telugu captions unchanged (timing preserved): every word has speech under it; onset median 0.03 s.
- English line 16 was loudness-matched to the original recording (+3.5 dB) and placed 57.92 s in.

## Audio

| | Integrated | True peak |
|---|---:|---:|
| English master | -14.08 LUFS | -1.93 dBTP |
| Telugu master | -14.07 LUFS | -1.61 dBTP |

Converted Telugu raw peak was 0.0 dBFS on 3.3e-05 of samples; it was attenuated 3 dB
before mixing, and the mix limiter holds the true peak under −1.5 dBTP. No silences longer than 1.2 s in either master.

## Video

Both masters: every frame decodes (English 1,923/1,923; Telugu 2,382/2,382); no black frames; workbench validation passed
(geometry, fps, codec, pixel format, 48 kHz, full decode, loudness). The Telugu reference-voice picture stream is bit-identical
(MD5 `d5dd0f5f6c34dfbf733a8763763f44c6`) to the previously verified Telugu master, so its captions, hook badge, original logo and
visuals carry over unchanged. The English reference-voice picture was re-rendered for the new timing; its contact sheet was reviewed.

## 4K deliverables

| File | Properties | SHA-256 |
|---|---|---|
| `AXHARRY_ENGLISH_REFERENCE_VOICE_4K.mp4` | 2160×3840 (9:16), 30 fps, H.264 High + AAC 48 kHz stereo, 64.10 s, 197,640,151 bytes; -14.08 LUFS, -1.93 dBTP | `1cf025358db6a84f96074c5bcf342957d1c442afe0b982898f8bbc54dc4b8974` |
| `AXHARRY_TELUGU_REFERENCE_VOICE_4K.mp4` | 2160×3840 (9:16), 30 fps, H.264 High + AAC 48 kHz stereo, 79.40 s, 245,411,158 bytes; -14.07 LUFS, -1.61 dBTP | `6d9ed330eac7b5396c8baafb00198c8bad3b70e911489bf35f6855daf7d4448c` |

Both 4K masters passed workbench validation (geometry, fps, codec, pixel format, 48 kHz, full decode, loudness); all frames
decode (1,923 / 2,382); no black frames; each audio track is bit-identical to its verified 1080p master
(English MD5 8572c5c8088f0d3723fa8f96fb8285ad, Telugu MD5 a8c2ebed9f11c2c78969cbc9bbf57bda).

**4K provenance:** rendered at 2160×3840 by Remotion (`--scale=2`); typography, captions, badges, logo framing and effects are
drawn at 4K. The anime artwork is upscaled from 512×512 generated images (Lanczos), so artwork detail is not native 4K.

## Known defect (all AXHARRY renders, including the earlier approved masters)

White caption words show thin dark internal outlines where glyph contours overlap (for example the leg of "R" and inside "D").
Cause: the captions' 1.5 px `-webkit-text-stroke`, which strokes overlapping contours. Red and gold key words have no stroke and are
unaffected. Fix: remove the stroke (the drop shadow already provides contrast) and re-render the pictures (about 30 min at 1080p,
about 2 h at 4K). Audio and timing would not change.
