---
name: creative-workstation
description: End-to-end AI creative workstation for promo videos and graphics in a layered "lavender-luxe" motion-design style (purple/lavender grid backgrounds, large serif blur-in typography, floating 3D chess pieces and objects, footage in rounded panels, silhouettes, logo walls, scene transitions) — plus license-checked asset collection, a catalogued media library, Blender 3D assets, beat-synced music/SFX, chunked full-length rendering (30 s to 60+ min, 1080p/4K) and photo work (background removal, compositing, posters, thumbnails, restoration, object removal, image-to-video). Use when the user gives a reference video and asset links and wants an original video or image made in that style. Triggers: make a promo like this reference, motion graphics video, animated typography, blur text reveal, chess promo, collect assets, asset catalogue, storyboard to video, render full-length video, poster, thumbnail, remove background, silhouette.
---

# Creative Workstation — reference + asset links in, verified video and images out

Set `SKILL_DIR` to this folder. Tools live in `scripts/` (run Python with `/opt/cws-venv/bin/python`, which has
OpenCV, rembg, Whisper, librosa) and the Remotion engine in `engine/`. Projects and media live outside git, by
default under `/home/user/creative-studio/` (`media-library/`, `projects/<name>/`). Run `scripts/doctor.sh` first;
`scripts/setup.sh` installs everything on a fresh Ubuntu 24.04 host.

Companion skills (installed alongside): `fable-video-edit` (takes → EDL → ffmpeg cut, Whisper, .cube LUT grading,
Remotion cue sheets), `image-editing` (resize/convert/HEIC/watermark/batch), `analyze-video-editing` (shot-level
reference evidence), `find-broll` (provenance-first B-roll), `video-editing` (generic render-plan runner/validator),
`remotion-best-practices`, `canvas-design`, `text-to-lottie`.

**Operating rule: don't stop at a storyboard.** Every job ends with a rendered file that passed `render.py`'s
verification (frames, duration, fps, audio, loudness, full decode) and review stills you have looked at.

## Fast path (two commands)

```bash
/opt/cws-venv/bin/python scripts/project.py init NAME --reference REF.mp4 --duration 60   # analyse + scaffold
/opt/cws-venv/bin/python scripts/project.py build NAME [--width 3840 --height 2160]       # compile→render→verify→sync
```
`init` seeds BPM, palette, pacing and transition style from the measured reference; edit
`projects/NAME/storyboard.json` (words, scenes, catalogued assets), then `build`. Exit 0 only if verification and the
sync check pass. The detailed steps below are what those two commands run — use them when you need control.

## The workflow (reference video + asset links → final export)

1. **Inspect the reference** — never infer from the filename:
   `ffprobe -show_format -show_streams REF.mp4`, then
   `/opt/cws-venv/bin/python scripts/analyze_reference.py REF.mp4 projects/<p>/analysis --deep`
   → palette, purple share, cut rhythm, blur-in/out events, motion energy, BPM, contact sheet, and
   `storyboard-defaults.json`. `--deep` adds the analyze-video-editing shot timeline. Watch the contact sheet.
2. **Write the style read** — map measurements to the engine: palette → `engine/src/theme.ts` `PALETTE`;
   blur events/min → transition mix; mean shot length → scene `bars`; BPM → `meta.bpm`. See
   [references/reference-1-style.md](references/reference-1-style.md) for the lavender-luxe grammar.
3. **Inspect the source websites** — `python3 scripts/collect_mixkit.py search "<term>" --type video --check-license`.
   For other sites follow [references/asset-sourcing.md](references/asset-sourcing.md): verify reachability and
   license **per item**; never bypass bot challenges; never download film/TV clips of unknown origin.
4. **Collect permitted media** — `collect_mixkit.py fetch-video URL... --library LIB --res 1080` (refuses
   `videoRestricted` items unless `--allow-personal`), `fetch-audio sfx|music TERM`. Original assets:
   `synth_assets.py all`, `audio_synth.py sfx|music`, Blender turntables (step 6).
5. **Catalogue** — every file goes through `scripts/catalog.py` (source URL, local path, format, dims/duration,
   license, commercial flag, restrictions, sha256). `catalog.py validate LIB` must print OK; `catalog.py report LIB`
   writes `CATALOG.md`.
6. **3D assets** — `blender -b -P scripts/blender_assets.py -- --out LIB/3d-assets --kind turntable --pieces king,queen
   --material pearl|obsidian --frames 72` (transparent PNG loops), `--kind objects` (orb/ring/cube/pill),
   `--kind board-orbit` (cinematic 3D shot). Then `synth_assets.py stills` for hero cut-outs.
7. **Grade footage** — `grade.py luts DIR`, `grade.py grid CLIP DIR grid.png` (compare looks, pick one),
   `grade.py apply DIR/<look>.cube clips... --out LIB/video-clips/graded --library LIB`. The LUT is applied once.
8. **Storyboard** — `projects/<p>/storyboard.json`: scenes in musical bars, scene types, props, floating objects,
   transitions. Schema + every scene type: [references/timeline-schema.md](references/timeline-schema.md).
9. **Timeline** — `python3 scripts/timeline.py compile storyboard.json -o timeline.json` (frame-exact, transitions
   centred on downbeats, total == `targetDuration`, auto SFX cue sheet). For long runtimes:
   `timeline.py expand storyboard.json --duration 600 -o storyboard-10min.json` then compile.
10. **Review stills before rendering** — link `projects/<p>/public/lib -> media-library`, then
    `npx remotion render src/index.ts Promo out/s --props=<{"timeline":…}> --public-dir=<p>/public --frames=a,b,c`
    from `engine/`; Read the images. Fix layout/typography/timing in the storyboard, recompile.
11. **Render** — `/opt/cws-venv/bin/python scripts/render.py projects/<p> [--timeline timeline.json]
    [--chunk-seconds 60]` → chunked Remotion video (resumable), streamed music+SFX mix, measured mastering loop
    (gain → 4×-oversampled limiter → AAC → re-measure until −16 ±0.5 LUFS and ≤ −1.5 dBTP), mux, BT.709 limited-range
    video, verification report `renders/<name>.render.json` (fails if loudness is out of spec), contact sheet +
    per-scene stills in `review/<name>/`. 4K: `timeline.py compile ... --width 3840 --height 2160`.
    Fix only the audio of an existing master: `render.py <p> --timeline <t>.json --remaster renders/<file>.mp4`.
    Fix full-range/untagged colour on older masters: `scripts/conform_color.py IN OUT`.
12. **Inspect + deliver** — Read the contact sheet and stills; check `verify.passed`, frames == expected, LUFS.
    Prove sync: `/opt/cws-venv/bin/python tests/sync_check.py renders/<name>.mp4 <timeline>.json` locates every SFX
    in the master by waveform cross-correlation (sample-accurate) and every transition by its change centroid.
    Deliver the master + the editable project (`storyboard.json`, `timeline.json`, `luts/`, engine source,
    catalogue). Re-edits = edit storyboard → recompile → re-render.

## Talking-head / raw-takes projects

Use the `fable-video-edit` skill (Whisper word timestamps → take selection → `final-edit.json` → ffmpeg cuts → LUT →
Remotion overlays). `tests/fable_workflow_test.py` runs that whole chain on synthetic spoken takes and re-transcribes
the assembly to prove zero fillers and correct order. Whisper drops "um/uh" by default — measured on a take
spoken as "Um, every move matters. Uh, every move matters…": default → "Every move matters, every move matters…";
with `--initial_prompt "Umm, let me think, uh, like, hmm... Okay, um, here's what I'm, uh, thinking."` → "Um, every
move matters, uh, every move matters…". Add that prompt (edit the whisper line in fable's `scripts/transcribe.sh`)
whenever the filler count drives take selection.

## Photo & graphic production

`scripts/photo_tools.py` (venv python):
`remove-bg` (rembg u2net / isnet / u2net_human_seg), `silhouette` (solid fill + rim glow), `enhance`
(`--denoise` restoration, `--match REF` colour correction to a reference, `--clahe`/`--sharpen` stylistic,
`--upscale`), `inpaint` (object/scratch/watermark removal by rect or mask), `grade` (same .cube LUTs),
`compose SPEC.json` (layered poster/thumbnail/story with gradient/grid/image/text/glow/shadow/vignette layers,
presets `poster` 1080×1350, `thumbnail` 1280×720, `story` 1080×1920, `4k`), `parallax` (image → 2.5D video).
Format conversion, resizing, HEIC, watermarking, batch: the `image-editing` skill (`uv run image_edit.py`).
Test: `tests/photo_pipeline_test.py FRAME OUT LUT` (PSNR-scored restoration and object removal).

## Rendering performance (measured on 4 vCPU, no GPU, 1080p30)

≈ 3–6 frames/s depending on scene (footage panels are the slowest). 60 s ≈ 6–9 min; 5 min ≈ 30–45 min;
10 min ≈ 1–1.5 h. Long jobs: `render.py` chunks are resumable — re-run the same command after an
interruption. Use `--scale 0.5` for fast drafts. Details and measured runs: [references/rendering.md](references/rendering.md).

## Rules

- Assets: only use what the catalogue marks with a verified license; `personal-only` items never go into
  commercial deliverables. Logos of real companies are trademarks — nominative use only.
- Never invent sources. The movie clips seen in Reference Video 2 have no identified source — don't fetch film scenes.
- Remotion: animate with `useCurrentFrame`/`interpolate` only; no CSS animations, timers, or network fonts.
  Avoid full-frame `mix-blend-mode`/`mask-image` (slow in software rendering).
- Remotion is source-available, not MIT — free for individuals and companies ≤ 3 people; larger orgs need a license.
