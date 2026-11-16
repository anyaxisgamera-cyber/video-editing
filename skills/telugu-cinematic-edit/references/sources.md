# Sources, licences and availability (checked in this environment)

Status: **VERIFIED** = downloaded/used and measured here · **REQUIRES ACCESS** = exists, licence known, blocked by a
gate the account owner must accept · **NOT USED** = available but its licence does not fit · **NOT AVAILABLE** = cannot
be reached from this environment without credentials.

## Telugu voice (TTS)

| Model / tool | Licence | Status | Notes |
|---|---|---|---|
| `facebook/mms-tts-tel` (Meta MMS, VITS, 16 kHz) | CC-BY-NC-4.0 | VERIFIED | Default engine. **Non-commercial only** — `voice.json` carries `commercial_use: false`. ASR round-trip CER 0.00–0.04 per segment on the test script. Tokenizer has no punctuation → clauses are synthesised separately and joined with pauses. |
| `ai4bharat/indic-parler-tts` | Apache-2.0 | REQUIRES ACCESS | Gated (auto-approve). With a valid token the API answers "not in the authorized list" until the account owner clicks *Agree and access repository* on the model page (and a fine-grained token needs "read access to public gated repos"). Commercial-friendly — use it for paid/monetised delivery once unlocked. |
| `ai4bharat/IndicF5` | MIT | REQUIRES ACCESS | Gated, same procedure. |
| espeak-ng `te` voice | GPL-3.0 program, output unrestricted | VERIFIED | Robotic; scratch timing only. |
| Human voice actor (`telugu_tts.py --engine files`) | your contract | supported | Recommended for commercial delivery: recordings are trimmed, levelled, ASR-checked and timed per clause from their pauses. |

## Telugu speech recognition (verification only)

| Model | Licence | Status | Use |
|---|---|---|---|
| `vasista22/whisper-telugu-small` | Apache-2.0 | VERIFIED | First-pass CER check of every synthesised segment and of the final mix. |
| `vasista22/whisper-telugu-medium` | Apache-2.0 | VERIFIED | Second opinion when the small model rejects a segment (it drops the rare sentence-initial word యెహోవా; the medium model hears ఏహోవా, CER 0.04). |
| OpenAI Whisper `small` | MIT | VERIFIED | English transcript of the reference (word timestamps). |

## Translation quality

| Model | Licence | Status | Use |
|---|---|---|---|
| `sentence-transformers/LaBSE` | Apache-2.0 | VERIFIED | Cross-lingual EN↔TE similarity per segment. On the test script: narration 0.80–0.91; the published IRV verses vs their WEB English score 0.81–0.83, so ≥ 0.8 is in the range of human Bible translation. Flags < 0.6. |
| `facebook/nllb-200-*` | CC-BY-NC-4.0 | NOT USED | Licence. |
| `ai4bharat/indictrans2-*` | MIT | REQUIRES ACCESS | Gated; would add a back-translation view. |

## Bible text (exact quotations — never generated)

| Corpus | Licence | Status |
|---|---|---|
| `tel2017` Telugu Indian Revised Version (IRV) 2019, © 2017, 2019 Bridge Connectivity Solutions — ebible.org | CC BY-SA 4.0 | VERIFIED, default (31 004 verses) |
| `telotsa` Biblica® Open Telugu Contemporary Version — ebible.org | CC BY-SA 4.0 | VERIFIED (30 936 verses) |
| `engwebp` World English Bible — ebible.org | Public domain | VERIFIED, used to check English quotations |
| Telugu ERV (`tel2010`) | © — no open licence | NOT USED |
| BSI Telugu "Old Version" (1880s wording familiar to many congregations) | — | NOT AVAILABLE as a licence-verified digital source here; supply a source if this wording is required |

CC BY-SA 4.0 requires attribution: the end card carries "వచనాలు: Telugu IRV · CC BY-SA 4.0" and the full attribution
string from `bible.py lookup` belongs in the video description. Note that BY-SA is share-alike for the *text*.

## Fonts

| Font | Licence | Status |
|---|---|---|
| Noto Sans Telugu, Noto Serif Telugu (Regular/Bold) | SIL OFL 1.1 | VERIFIED — copied into `media-library/fonts`, licence file `NotoTelugu-LICENSE.txt` |
| Mandali, NTR, Gidugu, Ramabhadra … (fonts-telugu / teluguvijayam) | SIL OFL 1.1 | installed system-wide, not catalogued |

## Footage, music, sound effects

| Source | Licence | Status | Notes |
|---|---|---|---|
| Mixkit video | Mixkit Stock Video Free License (`data-license="videoFree"`) | VERIFIED | `collect_mixkit.py` skips `videoRestricted` items (personal use only). **Every sheep / shepherd clip found was Restricted**, so the test uses landscapes, light, candles and people instead. Newer items (id ≥ 100000) download through `/free-stock-video/download/<id>/` — supported since this build. |
| Mixkit music | Mixkit Stock Music Free License | VERIFIED | Web/social/VOD/ads OK; not TV/radio broadcast, CD/DVD or games; do not register with Content ID. |
| Mixkit SFX | Mixkit Sound Effects Free License | VERIFIED | Inside an end product only. |
| Pexels / Pixabay | Pexels / Pixabay licences | NOT AVAILABLE | Their websites answer automated clients with a Cloudflare challenge; their official APIs need an API key (not configured). |
| Wikimedia Commons | per file (CC BY / CC BY-SA / PD) | reachable | Licence must be read per file; attribution required for CC BY(-SA). |

## OCR

Tesseract 5 (Apache-2.0) with `eng` and `tel` traineddata. Latin titles are read reliably; Telugu reading is
approximate (e.g. "మంచి కాపరి" → "మంచి SHS"), so `reference_breakdown.py` saves a still for every text event and the
validator uses OCR for *presence and timing* of subtitles, while text correctness is proven at string level against
the validated script.
