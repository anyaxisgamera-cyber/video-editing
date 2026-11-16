# Rendering — chunked long-form, 4K, verification, measured throughput

## How `scripts/render.py` renders

1. Writes `work/<timeline>.props.json` = `{"timeline": …}` (the composition reads `props.timeline`).
2. Mixes audio first, in 10-second blocks straight to disk: music bed (generated to the exact length, or a WAV)
   + every cue in `audio.cues` at its absolute sample. Two-pass EBU R128 `loudnorm` (linear mode) → AAC 256k 48 kHz.
3. Bundles the engine once (`npx remotion bundle`, re-used while `engine/src` is unchanged) and symlinks the
   project's `public/` (→ media library) into the bundle.
4. Renders the video in chunks (`--frames=a-b --muted`, default 60 s each) into
   `work/chunks-<name>-<hash>/`, where the hash covers the timeline, the engine build and the encode settings.
   Re-running the same command skips chunks that are already complete → **resumable**; editing the storyboard or
   the engine changes the hash, so stale chunks are never reused.
5. Joins chunks with the concat demuxer (`-c copy`, no re-encode), muxes the audio, `+faststart`.
6. Verifies: frames == expected, duration, fps, geometry, audio codec/rate, full decode, integrated LUFS / true peak,
   contact sheet + one still per scene in `review/<name>/`. Writes `renders/<name>.render.json`.

The encode/mux chain is sample-accurate: cross-correlating the pre-encode mix with the AAC in the final MP4 gives a
lag of 0 samples (tested on the 60 s master). `tests/sync_check.py` locates every SFX in the master by waveform
cross-correlation (all 20 cues of the 60 s test within 0.07 ms of plan).

## Resolution

Every size in the engine is authored at 1080p and multiplied by `height / 1080`, so `timeline.py compile
--width 3840 --height 2160` renders the same layout in 4K and `--width 960 --height 540` makes a fast draft.
Text, gradients, grid, SVG/Lottie are resolution-independent. Raster sources are not: Blender turntables are
600×800 and graded footage is 1080p, so in 4K they are upscaled — re-render `blender_assets.py --size 1200x1600`
and grade at `--size 3840x2160` for native-4K sprites/footage.

## Performance notes (4 vCPU, no GPU, Chromium headless shell, software compositing)

- Avoid full-frame `mix-blend-mode` and `mask-image`, and per-sprite `drop-shadow` filters: replacing them with plain
  alpha layers / gradient shadows gave +20–24 %.
- `@remotion/media` `<Video>` (WebCodecs) was ~10 % faster than `<OffthreadVideo>` for three simultaneous panels.
  Use its `objectFit="cover"` prop — CSS `object-fit` is ignored by it.
- Footage-panel scenes are the slowest (~2.5 fps at 1080p with 3 videos); title/statement scenes ~5 fps.
- `--scale 0.5` / 960×540 timelines render ≈ 3.3× faster (≈ 16 fps on title scenes).

## Measured renders

See the table appended by the final test run (below).
