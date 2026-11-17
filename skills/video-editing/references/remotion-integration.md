# Remotion integration with the official Remotion Agent Skills

The official Remotion Agent Skills are published at `https://github.com/remotion-dev/skills` and installed with `npx skills add remotion-dev/skills`. Their router skill is `remotion-best-practices`, which links focused references. The guidance below maps them onto this workflow; it does not replace FFmpeg work that is simpler in the FFmpeg lane. Checked against the skills at version 4.0.544 (repository state of 16 November 2026).

For anything not covered here, read the current documentation instead of relying on memory: search with the `remotion-docs` reference, then fetch the page with a `.md` suffix (for example `https://www.remotion.dev/docs/calculate-metadata.md`).

## Which official reference to load

| Task in this workflow | Official reference |
|---|---|
| New Remotion project, layout and safe areas | `remotion-create` (`video-layout.md`: safe areas and minimum text sizes per width) |
| Compositions, `calculateMetadata`, sequencing, timing, transitions, voiceover, SFX, local fonts, multi-scene and editable timelines | `remotion-markup` (`compositions.md`, `calculate-metadata.md`, `sequencing.md`, `timing.md`, `transitions.md`, `voiceover.md`, `sfx.md`, `local-fonts.md`, `multi-scene-video.md`, `video-editing.md`) |
| Captions (the `Caption` JSON type, display, SRT import, transcription) | `remotion-captions` |
| Studio preview | `remotion-studio` |
| Rendering videos, stills, frame lists, transparent video, OpenTimelineIO export | `remotion-render` |
| Media metadata in the browser | `remotion-multimedia` |
| Licensing | `remotion-license` |
| Upgrading Remotion and the skills | `remotion-upgrade` |

## How the pieces fit this workflow

- **Compositions per format.** One composition reads its width, height, fps, and duration from props through `calculateMetadata`, so the same component renders 9:16 and 16:9 at 1080p or 4K. The bundled starter's `ScriptVideo` does this. The existing `VideoEdit` and `MotionOverlay` compositions are unchanged.
- **Reusable components.** Scene media (video or image with a camera move), on-screen text, caption pages, narration, ducked music, and SFX are separate components, each reading `useCurrentFrame()` only where it is needed, as `remotion-markup` recommends.
- **Animation.** Use `interpolate()` with `Easing` and `spring()` driven by `useCurrentFrame()`; no CSS transitions, keyframes, timers, or unseeded randomness (the main skill's rule).
- **Captions.** Captions are the official `Caption` type (`text`, `startMs`, `endMs`, `timestampMs`, `confidence`), with a space before every word after the first. `ScriptVideo` pages them with `createTikTokStyleCaptions()` from `@remotion/captions`. For Studio editing of a single hand-made video, the official Basic Captions element with an inline caption array is preferable. Generated multi-language productions keep captions in props generated from the timing map, so edits are made in the timing data, not in Studio.
- **Audio and video sync.** Everything is placed in frames from the timing map: `<Sequence from durationInFrames>` per scene, narration, and effect. Music volume is a number computed with `interpolate()` over duck keyframes (the official volume guidance; the callback form is no longer recommended).
- **Fonts.** Load each language's font file with `loadFont()` from `@remotion/fonts`. When the font comes from props, load it in `useEffect` behind a `delayRender` handle, as the official `loadFont` documentation describes. Non-Latin scripts need a font that covers them (for example the Noto family); browser shaping then handles complex scripts.
- **Voiceover.** The official `voiceover.md` describes per-scene TTS with `calculateMetadata` sizing the composition to the audio. Here the same idea is done by `production.py timing`, which measures per-language narration and sizes every scene.

## Preview, render, validate

1. Typecheck (`npm run typecheck`).
2. Preview. The official skills open Studio (`npx remotion studio`) when someone is watching; in unattended runs, render stills and short ranges instead: `npx remotion still … --frame=N` and `npx remotion render … --frames=a-b`.
3. Render. The official skills render only when the user explicitly asks for an export. An autonomous production brief that asks for finished videos is that request. Always pass the composition ID and the props file.
4. Master the audio and validate each output with `video_workbench.py validate`, as the main skill requires. `production.py render` does this for one matrix cell: picture render (`--muted`), audio render (`--codec=wav`), loudness mastering with the AAC encode done by FFmpeg, a narration-sync measurement, then validation.

Rendering notes:

- Use Remotion's bundled browser. Behind an HTTP proxy, Node does not use the proxy unless `NODE_USE_ENV_PROXY=1` is set (Node 22), and the download fails with an address error. Set that variable rather than pointing Remotion at another browser. Pass `--browser-executable` only when the user asks for it or no download is possible, and record why.
- Pass `--color-space=bt709` for tagged BT.709 H.264 output.
- Render picture and sound separately when sync matters. In this workflow's measurements (Remotion 4.0.489), the AAC track of an H.264 MP4 rendered by Remotion sat 42.7 ms (2048 samples) late against the same composition rendered with `--codec=wav`, which was sample-accurate. Muxing the WAV with FFmpeg's AAC encoder gave 0.0–0.06 ms. Re-measure after upgrading Remotion instead of assuming either result still holds.
- Remotion's bundler copies `public/` into the bundle and does not follow symlinks. Place media there as real files or hard links (`production.py props` hard-links, or copies across filesystems).
- Use `--license-key` only when a key exists (see below).
- When the user wants an editable timeline for another editor, use the official OpenTimelineIO export in `remotion-render`.

## Licensing

Remotion is free for individuals and companies of up to 3 people. Larger companies need a Company License: per render for automation, or per seat for manual creation. Check the official pricing page (`https://www.remotion.dev/docs/license/pricing.md`) for current terms. If the user or their organization may need a license, treat buying one as an approval decision ([approvals.md](approvals.md)) before commercial delivery.

## Version policy

The bundled starter pins its Remotion version. Do not upgrade it silently in a user's project; follow `remotion-upgrade` when an upgrade is needed, and keep all `@remotion/*` packages on the same version as `remotion`.
