---
name: video-editing
description: Edit arbitrary supplied video, audio, images, screen recordings, and graphics into a polished deliverable. Use for cutting and restructuring footage, multi-track compositing, picture-in-picture, transitions, captions, sound work, color and framing changes, screen demos, presenter edits, social clips, and motion graphics made with FFmpeg, HTML, React, SVG, or Remotion. Includes source inspection, timeline design, reusable media tooling, transparent overlay generation, fast review artifacts, deterministic rendering, and technical validation. Also produces finished videos from only a script, with licensed asset research and a source register, editing-reference research, approval gates, storyboard, automatic narration-synced timing and captions, Remotion compositions, multiple videos and languages, and 9:16 and 16:9 delivery at 1080p or 4K.
---

# Video Editing

Edit whatever footage the user supplies. This is a general workbench, not a preset for one visual style. Treat each edit as an editorial system with observed source facts, explicit timing, an appropriate rendering engine, rapid review artifacts, and a validated master.

Set `SKILL_DIR` to the absolute directory containing this file. Resolve bundled scripts, references, assets, and examples relative to it.

When the primary request is to reverse-engineer a finished reference film—shots, camera behavior, sound, titles, pacing, and interview/B-roll grammar—use the adjacent `analyze-video-editing` skill first. When the request is to find, vet, or place cutaways against spoken words, use the adjacent `find-broll` skill before bringing its approved manifest into this editing workflow.

When the user supplies only a script and basic project information and expects finished videos, follow [Produce videos from a script](#produce-videos-from-a-script). Do not ask them for clips, images, timestamps, or editing instructions.

Initialize a neutral edit workspace when the task does not already have one:

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" init /path/to/edit-project
```

The generated `editorial-plan.json` is a human-and-agent planning artifact, not an executable timeline schema. Rendering remains explicit: an arbitrary FFmpeg graph through `render-ffmpeg`, a typed Remotion composition, or both. This avoids pretending a small schema can represent every edit.

## Produce videos from a script

Use this mode when the input is a script plus basic project information: number of videos, duration of each, and languages per video. Run the whole production yourself — research, creative direction, storyboard, asset discovery, narration, timing, editing, Remotion implementation, previews, revisions, rendering, and quality control. Read [references/autonomous-production.md](references/autonomous-production.md) for the end-to-end loop and its deliverables.

```bash
python3 "$SKILL_DIR/scripts/production.py" init /path/to/production \
  --videos 2 --languages en,te --durations 60,90 --formats 9:16,16:9 --resolutions 1080,2160
```

`production.py` keeps the production honest and reproducible. Its commands:

- `register-add`, `audit`: the source register and licence checks;
- `timing`: per-language timing maps measured from real narration;
- `props`, `render`: Remotion props, then render, master, sync check, and validation;
- `feasibility`: 4K and crop upscale factors;
- `status`: the state of every deliverable.

It never downloads assets or contacts asset services. `render` runs the Remotion CLI, which may download Remotion's own browser on first use.

- **Research and licensing.** Search widely for real footage, images, animation, music, sound effects, fonts, and voices. Compare candidates on relevance, quality, licence, availability, and technical fit, and record real links and licence evidence in the source register: [references/research-and-licensing.md](references/research-and-licensing.md).
- **Editing references.** Study professional films, documentaries, ads, and creators relevant to the script, then write an original style guide: [references/editing-research.md](references/editing-research.md).
- **Approvals.** Read-only research and downloads the licence permits need no approval. Ask explicitly — showing website, purpose, cost, permissions, and restrictions — before purchases, subscriptions, account creation, accepting terms, external uploads, publishing, or other consequential actions: [references/approvals.md](references/approvals.md).
- **Scenes and synchronization.** Split the script into scenes, match visuals to meaning, and let measured narration drive cuts, captions, music ducking, and effects: [references/scene-planning-and-sync.md](references/scene-planning-and-sync.md).
- **Remotion.** Follow the official Remotion Agent Skills through [references/remotion-integration.md](references/remotion-integration.md). The motion starter's `ScriptVideo` composition renders any language and format from the timing map.
- **Multiple videos and languages.** Treat every video × language × format × resolution as its own validated deliverable, and adapt narration, captions, on-screen text, pronunciation, cultural context, and timing per language: [references/multi-video-and-localization.md](references/multi-video-and-localization.md).

Default delivery unless the user says otherwise: 9:16 vertical and 16:9 widescreen at 1080p Full HD, plus 4K Ultra HD where `production.py feasibility` shows it is technically feasible, or the user accepts the reported upscale.

Every acquired asset still goes through [Start by observing](#start-by-observing), and every deliverable through [Validate the deliverable](#validate-the-deliverable).

## Start by observing

Never infer duration, dimensions, frame rate, stream order, rotation, color metadata, or audio from filenames. Inspect the real payloads:

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" inspect \
  --work-dir /path/to/work \
  /path/to/source-a.mp4 /path/to/source-b.mov
```

This writes raw probes, checksums, audio scans, and contact sheets. Add transcription only when speech content helps determine cuts:

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" transcribe \
  /path/to/source.mp4 /path/to/work/transcript
```

Review the sources before making an edit plan. Preserve the evidence for synchronization, speaker identity, orientation decisions, and important source defects.

## Choose the rendering lane

Use the smallest engine that comfortably expresses the edit:

- **FFmpeg:** trims, concatenation, reframing, speed, audio mixing, normalization, straightforward overlays, masks, fades, color transforms, and final encoding.
- **Remotion with React/SVG:** designed graphics, titles, captions, callouts, diagrams, data-driven scenes, browser typography, animated layouts, and mixed footage-plus-graphics work.
- **Hybrid:** render a transparent graphic overlay from Remotion, then composite it with footage in FFmpeg. This is often the cleanest lane.

Do not force a complex graphic into one unreadable FFmpeg expression. Do not create a React project for a simple cut.

Initialize the general motion project when useful:

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" init-motion /path/to/edit-motion
cd /path/to/edit-motion
npm install
npm run dev
```

The starter supports local footage, React layout, inline SVG, full-frame video, and transparent ProRes 4444 overlays. Read [references/motion-graphics.md](references/motion-graphics.md) before changing its render contract.

The starter also registers `ScriptVideo`, a props-driven composition with these parts:

- scenes with focus-aware crops and camera moves;
- crossfades;
- on-screen text;
- `@remotion/captions` caption pages;
- per-language fonts;
- narration, ducked music, and effects.

Its size, frame rate, and duration come from the props, so one component serves every language and format. `VideoEdit` and `MotionOverlay` are unchanged. For Remotion work, load the official Remotion Agent Skills (`remotion-best-practices`) where they are installed, as mapped in [references/remotion-integration.md](references/remotion-integration.md).

## Design the edit

Write down:

- delivery aspect ratio, dimensions, frame rate, duration target, and platform;
- source-time selects and output-time placement;
- track ownership: base picture, inserts, graphics, captions, music, effects, and dialogue;
- the purpose of every transition or layout change;
- audio hierarchy and loudness target;
- representative frames and transition ranges to review.

Keep source time and output time distinct. Use stable clip and beat identifiers. Derive frame numbers from one project frame rate instead of scattering timing arithmetic.

Read [references/workflow.md](references/workflow.md) for the full loop and [references/timeline-and-compositing.md](references/timeline-and-compositing.md) for reusable editorial and compositing principles.
For tested filtergraph building blocks and end-of-file choices, use [references/ffmpeg-recipes.md](references/ffmpeg-recipes.md).

In script-driven productions, the timing map from `production.py timing` is the edit map for each language. It keeps scene IDs, source in-points, and output frames separate and is derived from measured narration, so do not hand-place timestamps or reuse one language's timing for another.

## Work in cheap passes

1. Make an assembly with correct content and sync.
2. Make a low-resolution full draft.
3. Generate a contact sheet for rhythm.
4. Generate strips around every cut, transition, graphic entrance, and synchronization cue.
5. Render stills for composition, typography, safe areas, masks, and color.
6. Fix those artifacts before the master.

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" sheet draft.mp4 review/contact.jpg
python3 "$SKILL_DIR/scripts/video_workbench.py" strip \
  draft.mp4 review/transition.jpg --center 12.4 --window 1.6
python3 "$SKILL_DIR/scripts/video_workbench.py" stills \
  draft.mp4 review/stills --times 0,12.4,27.8
```

For independent quality control, give another agent the brief, source report, draft, contact sheet, and transition strips—not the implementation story—and ask it to report only concrete defects.

## Render safely

For a custom FFmpeg graph, put the graph in a file and describe the render in the generic plan format from [references/render-plan.md](references/render-plan.md):

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" render-ffmpeg render-plan.json
```

The workbench renders to a candidate, validates it, and promotes it only after it passes. Existing deliverables are archived reversibly.

For Remotion, typecheck before rendering. Use `useCurrentFrame()`, `interpolate()`, `spring()`, and `Sequence`; do not use timers, CSS keyframes, unseeded randomness, or runtime network calls. Render representative stills and ranges before a full master.

## Validate the deliverable

Run validation even when playback looks correct:

```bash
python3 "$SKILL_DIR/scripts/video_workbench.py" validate final.mp4 \
  --report /path/to/work/validation.json \
  --width 1920 --height 1080 --audio-rate 48000 --lufs -16
```

Validation checks the real output payload, full decode, expected geometry and duration when supplied, audio sample rate, loudness, and checksum. Read [references/quality-gates.md](references/quality-gates.md).

Deliver the master together with the source report, edit plan or source project, review artifacts, render command, validation report, and checksum.

For a production with several deliverables, also run `production.py audit` (source register, licences, checksums, approvals, credits) and `production.py status`. A matrix cell counts as delivered only when its file exists, its validation report passed, and the report's checksum matches the file. Report every other cell as missing, failed, stale, or upscaled, with the reason.

## General principles

- Let meaning determine transitions; motion without an attention change is decoration.
- Keep the viewer oriented. Establish spatial context before aggressive crops.
- Make text readable at delivery size, not merely on a large monitor.
- Prefer authentic interface recordings over invented screenshots.
- Preserve original dialogue unless replacement was requested.
- Normalize dialogue before the final sample-rate conversion.
- Crossfading differently scaled copies often creates ghosting; use a motivated cut or animate one continuous layer.
- When an overlay source ends early, decide explicitly whether to hold, disappear, or reveal the base.
- Use alpha-capable assets and codecs for reusable graphics; never fake transparency with a guessed background color.
- Never claim an asset, licence, permission, download, render, or check succeeded without the file, record, or report that proves it; never invent assets or sources, and never bypass access restrictions.
- Languages differ in narration length and caption fit; measure and time each language separately.

## Keep solutions general

Do not turn one successful edit into a default style. Preserve reusable mechanics—inspection, timing, compositing, motion systems, review artifacts, and validation—while choosing layouts, graphics, transitions, and sound treatment from the current material and brief.
