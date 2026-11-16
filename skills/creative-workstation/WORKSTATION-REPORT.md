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

## 5. Real editing capabilities (each exercised; numbers are measured)

| Capability | Tool | Status | Evidence |
|---|---|---|---|
| Reference style analysis | `analyze_reference.py` (+ analyze-video-editing `--deep`) | VERIFIED | On a render with known edits: all 9 scene boundaries within ±0.25 s, mean scene 6.0 s (exact), 95.7 BPM vs 96, 63 % purple share. Not yet run on the real Reference Video 1 (file not supplied). |
| Licence-checked asset collection | `collect_mixkit.py` | VERIFIED | 6 clips + 3 SFX + 2 music; restricted clips refused (visible `data-license` vs generic JSON-LD) |
| Asset catalogue | `catalog.py` | VERIFIED | 137 assets, all with source URL, path, format, dims/duration, licence, commercial flag, restrictions, sha256; `CATALOG.md` |
| Original 3D assets | `blender_assets.py` (Blender 4.5 Cycles) | VERIFIED | 13 turntables × 72 frames (alpha) + 96-frame board-orbit camera shot |
| Colour grading | `grade.py` (.cube LUTs, fable method) | VERIFIED | 4 looks, comparison grids, 6 clips graded once |
| Storyboard → timeline | `timeline.py` | VERIFIED | Exact frame totals (30 s … 60 min); whoosh peaks on downbeats; chapter expansion |
| Motion graphics engine | `engine/` (Remotion 4.0.544) | VERIFIED | 9 scene types, 7 transitions, blur-in/out serif type, floating 3D objects with depth blur, footage panels, silhouette, logos, Lottie |
| Music + SFX | `audio_synth.py` | VERIFIED | Any length (60 min bed in ~2 min), 6 SFX with sync points |
| A/V sync | `tests/sync_check.py` | VERIFIED | Template matching of every SFX in the master + transition change-centroid (results below) |
| Rendering | `render.py` | VERIFIED | Resumable hashed chunks, mastered audio, BT.709 video, verification that fails on out-of-spec output |
| Loudness mastering | `render.py` measured loop | VERIFIED | All masters −16.1…−16.2 LUFS, ≤ −2.2 dBTP; 0-sample A/V lag after limiting |
| Colour delivery | `--color-space=bt709`, `conform_color.py` | VERIFIED | `yuv420p`/tv/BT.709; vs browser PNG ground truth within ~1–1.5 code values |
| One-command workflow | `project.py init/build` | VERIFIED | Reference → 20 s master: 600/600 frames, −16.2 LUFS, sync passed, exit 0 |
| Talking-head edits | fable-video-edit | VERIFIED | `tests/fable_workflow_test.py`: correct take picks, 0 fillers after re-transcription |
| Background removal / silhouettes | `photo_tools.py` (rembg) | VERIFIED | u2net_human_seg cut-out with true alpha; silhouette + rim glow |
| Restoration / colour correction | `photo_tools.py enhance` | VERIFIED | Denoise 23.17→24.67 dB PSNR; + reference match 30.27 dB |
| Object removal | `photo_tools.py inpaint` | VERIFIED | Region PSNR 4.51→33.0 dB (OpenCV Telea) |
| Posters / thumbnails / compositing | `photo_tools.py compose` | VERIFIED | 1080×1350 poster, 1280×720 thumbnail (layered, glow/shadow/blur, OFL serifs) |
| Image → video | `photo_tools.py parallax` | VERIFIED | 2.5D parallax, 120/120 frames |
| Resize / convert / HEIC / batch | image-editing skill | VERIFIED | WebP, HEIC, batch thumbnails |
| Animated vector | Lottie via `@remotion/lottie` | VERIFIED | Original sparkle Lottie rendered in end card / logo wall |

## 6. Render tests (all measured on this host: 4 vCPU, no GPU)

| Master | Size | Frames | Duration | Loudness | True peak | Colour | Render time (video) | Sync |
|---|---|---|---|---|---|---|---|---|
| REGALIA promo 60 s | 1920×1080 | 1800/1800 | 60.000 s | −16.2 LUFS | −3.4 dBTP | BT.709 tv | 249 s (7.2 fps) | 20 SFX: median 0.0 ms, max 0.07 ms; 9 transitions: median 0.5 f |
| 30 s cut | 1920×1080 | 900/900 | 30.000 s | −16.2 | −3.4 | BT.709 tv | 180 s (5.0 fps) | — |
| 4K test | 3840×2160 | 450/450 | 15.000 s | −16.1 | −3.4 | BT.709 tv | 237 s (1.9 fps) | — |
| Long-form 5 min | 1920×1080 | 9000/9000 | 300.000 s | −16.2 | −3.2 | BT.709 tv | 1584 s (5.7 fps) | 108 SFX: median 0.0 ms; 47 transitions: median 0.7 f |
| Long-form 10 min | 1920×1080 | 18000/18000 | 600.000 s | −16.1 | −2.2 | BT.709 tv | 3114 s (5.8 fps) | 216 SFX: median 0.0 ms (non-tonal max 1.18 ms); 96 transitions: median 0.8 f |
| Long-form 60 min | 960×540 | (in progress) | 3600.000 s target | | | | | |

All masters: full decode without errors; AAC 48 kHz; frame count == compiled timeline. The 60 s, 30 s, 4K and 5 min
masters were rendered before two fixes were made and were then corrected without re-rendering the picture:
colour conformed to BT.709 (`conform_color.py`) and audio re-mastered (`render.py --remaster`).

## 7. Defects found by verification and fixed (in order)

1. Iris/soft-wipe transitions left a corner mask on the incoming scene → mask removed at p = 1.
2. Bundle `public/` symlink nested (`public/public`) → images 404'd silently in a benchmark → `render.py` relinks.
3. `@remotion/media` `<Video>` ignored CSS `object-fit` → uses its `objectFit` prop.
4. Poster layers showed hard rectangles (blur clipped to bbox, non-premultiplied blur) → pad + `RGBa` blur.
5. Restoration recipe *lowered* PSNR (gray-world WB on a dark, blue scene) → blind restoration = denoise only;
   colour correction needs a reference (`--match`).
6. Whisper drops "um/uh" → documented disfluent `--initial_prompt` (verified).
7. Blur dissolves perceived ~3 frames early (top layer opaque at 65 %) → symmetric crossfade (+0.12 f after).
8. Render chunks could be reused after code edits → chunk folders keyed by timeline + engine + settings hash.
9. Catalogue missed synthesized audio and the board shot; graded-clip rows broke the Markdown table → fixed.
10. Masters were full-range BT.601, untagged (`yuvj420p`) → BT.709 limited range.
11. `loudnorm` fell back to dynamic mode on every master; AAC overshot to −0.7 dBTP → measured mastering loop.
12. CI skipped the audio-synthesis checks (no numpy on the runner) → `uv run --with …` + `--require-audio`.
13. Analyzer derived pacing from hard cuts only (0 cuts on an all-dissolve edit) → counts soft transitions.
14. `sync_check.py` took 10+ min on 10 minutes of media → O(N) window search (2.5 min, identical results).

## 8. Missing dependencies, unavailable features, licensing, limitations

- **NOT AVAILABLE**: PNGEgg, Pexels, Pixabay (Cloudflare challenge), Icon-Icons (blocked) from this host.
- **REQUIRES API**: Pexels/Pixabay official APIs (keys), each::labs skills (`EACHLABS_API_KEY`), ElevenLabs
  (make-product-video voice/music), Gemini (analyzer semantic audio).
- **PARTIAL**: 4K — text/vector layers are native 4K; Blender sprites (600×800) and footage (1080p) are upscaled
  (re-render with `--size 1200x1600` / grade at 2160p for native 4K). Long-form expansion cycles the storyboard's
  scene types with content variations — real 30–60 min films need more authored scenes. Image upscaling is
  Lanczos + sharpen (no ML super-resolution model installed).
- **Measurement caveat**: tonal SFX (the D-major swell) can be located one period (6.8 ms) off by waveform
  correlation; non-tonal cues are exact.
- **Performance**: no GPU → 1080p30 at ~5–7 fps, 4K at ~1.9 fps, 540p at ~8 fps (60 s of 1080p ≈ 4–5 min;
  10 min ≈ 53 min; 60 min at 1080p ≈ 5–6 h).
- **Licences**: Remotion is source-available (free for individuals and companies ≤ 3 people; larger orgs need a
  licence). Mixkit clips: no standalone redistribution; Mixkit music: not for TV/radio, games, CDs. Simple Icons
  logos are trademarks (nominative use only). Fonts are SIL OFL. Everything else here is original.
- **Not done**: the real Reference Video 1/2 files were never provided, so no analysis of them exists; the
  movie clips seen in Reference Video 2 have no identified source and were not fetched.
