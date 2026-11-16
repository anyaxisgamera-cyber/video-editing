# Creative Workstation — build & verification report

Host: Ubuntu 24.04.5 (x86_64), 4 vCPU, 15 GB RAM, **no GPU**, egress through an allow-listed proxy. Built 2026-11-16.
Statuses: VERIFIED (installed and exercised with a measured result), INSTALLED (present, not exercised end-to-end),
PARTIAL, NOT AVAILABLE, REQUIRES API.

**Reference videos:** the two screen recordings were **not present** in the workstation. Reference Video 1's style
is implemented from the written brief; Reference Video 2's sourcing workflow from the listed sites. The reference
analyzer is ready for the real files (validated on a render with known edit decisions).

## 1. Repositories inspected

| Repository | Commit | Licence | Finding |
|---|---|---|---|
| filipenevola/fable-video-edit (primary video) | fdc4f5e | MIT | SKILL.md + `check-prereqs.sh`, `transcribe.sh` + 6 reference docs (EDL schema, ffmpeg recipes, .cube grading, Remotion cue sheets, take selection). The session's `anyaxisgamera-cyber/fable-video-edit` fork is byte-identical. |
| jlouage/Image-Editing-Claude-Skill (primary photo) | f94a8c4 | MIT | `.claude/skills/image-editing/` = SKILL.md + `image_edit.py` (Pillow, pillow-heif, numpy via `uv`). No network/subprocess. Its triggers list "remove background" but it has **no** ML background removal (alpha flatten/mask/autocrop only). |
| anyaxisgamera-cyber/video-editing (fork of gitethanwoo/video-editing) | 8b633c2 | MIT (+ Remotion notice) | 5 real skills with scripts + smoke tests (analyzer, B-roll, render-plan runner, Remotion template). Both smoke tests pass. New skill added here. |
| anyaxisgamera-cyber/editing-skill | 4072495 | — | Reference-extraction skill (frames, tiles, palette, contact sheets, QA). Docs + 4 small tools. |
| anyaxisgamera-cyber/Ultimate-Video-Editing-Skills | 7d0af0d | MIT (in frontmatter) | Documentation-only skill (FFmpeg recipes, colour, motion design). |
| anyaxisgamera-cyber/skills (each::labs) | e4e641e | MIT | 576 SKILL.md wrappers around a paid generative API → **REQUIRES API** (`EACHLABS_API_KEY` not set). |
| remotion-dev/skills | 3e20ac7 | (no LICENSE file; Remotion's own licence applies) | Official Remotion agent skills; router `remotion-best-practices`. |
| anthropics/skills | 1780c5e | Apache-2.0 per skill | `canvas-design` (+ 50 OFL fonts), `algorithmic-art`, `slack-gif-creator`, `theme-factory`… |
| heygen-com/hyperframes | 49e9424 | Apache-2.0 | HTML/GSAP → video engine + ~20 skills. Not installed: its skill fires an account-linked telemetry "usage beacon" on start, and Remotion is the requested engine. |
| diffusionstudio/lottie | 3c72912 | MIT | `text-to-lottie` skill (Lottie JSON authoring). |

## 2. Skills installed (user scope `~/.claude/skills/`) — discovery VERIFIED

Claude Code picked each up live (they appeared in the session's skill registry right after install). Name clashes
with the each::labs project skills were resolved by Claude Code as `skills:image-editing` / `skills:video-editing`.

| Skill | SKILL.md path | Status |
|---|---|---|
| fable-video-edit | `~/.claude/skills/fable-video-edit/SKILL.md` | VERIFIED — prereqs all PASS; Whisper transcription → take selection → EDL → cuts → re-transcribe → LUT + loudnorm (tests/fable_workflow_test.py) |
| image-editing | `~/.claude/skills/image-editing/SKILL.md` | VERIFIED — HEIC encode/decode, WebP export, autocrop+flatten, batch thumbnails |
| creative-workstation (new) | `~/.claude/skills/creative-workstation/SKILL.md` → repo `skills/creative-workstation/` | VERIFIED — this report |
| analyze-video-editing | `~/.claude/skills/analyze-video-editing/SKILL.md` | VERIFIED — smoke test + `--deep` run on a render |
| video-editing (workbench) | `~/.claude/skills/video-editing/SKILL.md` | VERIFIED — smoke test passes |
| find-broll | `~/.claude/skills/find-broll/SKILL.md` | INSTALLED |
| make-product-video | `~/.claude/skills/make-product-video/SKILL.md` | INSTALLED — voice/music need the ElevenLabs CLI → REQUIRES API |
| editing-skill | `~/.claude/skills/editing-skill/SKILL.md` | INSTALLED |
| ultimate-video-editor | `~/.claude/skills/ultimate-video-editor/SKILL.md` | INSTALLED (documentation) |
| remotion-best-practices | `~/.claude/skills/remotion-best-practices/SKILL.md` | VERIFIED — used to build the engine |
| canvas-design | `~/.claude/skills/canvas-design/SKILL.md` | VERIFIED — its OFL fonts are the workstation's typefaces |
| text-to-lottie | `~/.claude/skills/text-to-lottie/SKILL.md` | INSTALLED (Lottie rendering itself VERIFIED via @remotion/lottie) |

## 3. Engines (`scripts/doctor.sh` — all PASS)

FFmpeg/FFprobe 6.1.1 (lut3d, loudnorm, silencedetect, xstack, drawtext) · Node 22.23 · Remotion 4.0.544
(+ transitions, fonts, lottie, media) · Python 3.13 venv `/opt/cws-venv` · Pillow 12.3 · pillow-heif 1.8.1 ·
OpenCV 5.0.0 · NumPy 2.5 / SciPy 1.18 · rembg (onnxruntime 1.29; u2net_human_seg) · openai-whisper (torch 2.15 CPU;
base model) · librosa 1.0.1 · PySceneDetect 0.7.3 · uv 0.11 · ImageMagick 6.9.12 · librsvg 2.58 · **Blender 4.5.16
LTS** (official build, SHA-256 verified; Cycles CPU + OIDN) · SoX 14.4 · Tesseract 5.3 · espeak-ng 1.51 (test speech)
· Chromium headless shell (Playwright) used by Remotion.

## 4. Asset websites tested

See `references/asset-sourcing.md`. PNGEgg, Pexels, Pixabay: Cloudflare JS challenge (also in headless Chromium) —
NOT AVAILABLE from this host (not bypassed). Icon-Icons: hard block — NOT AVAILABLE. Pexels/Pixabay official APIs —
REQUIRES API (keys). **Mixkit: VERIFIED** — licence text read from the site; per-item licence enforced; 6 clips,
3 SFX, 2 music tracks collected; restricted clips refused automatically.

## 5–7. Capabilities, render tests, limitations

(Filled in below by the final test run.)
