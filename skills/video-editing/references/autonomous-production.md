# Autonomous production from a script

Use this mode when the user supplies a script and basic project information and expects finished videos. Do not ask the user for clips, images, timestamps, or editing instructions. Research, decide, build, review, and deliver; stop only at the approval gates in [approvals.md](approvals.md) or when a decision genuinely belongs to the user.

The rest of this skill still applies: inspect every acquired file before using it, keep source and output time separate, review in cheap passes, render to a candidate, and validate the real payload.

## 1. Intake and deliverable matrix

Extract from the brief, without inventing requirements:

- number of videos and the script for each;
- target duration per video;
- languages per video;
- delivery formats. Unless the user says otherwise: 9:16 vertical (1080×1920) and 16:9 widescreen (1920×1080) at 1080p, plus 4K (2160×3840 / 3840×2160) where [multi-video-and-localization.md](multi-video-and-localization.md#4k-feasibility) shows it is feasible;
- audience, platform, tone, brand assets, must-keep and must-avoid content;
- whether the deliverables are commercial (this decides which licences are usable).

Create the project and its matrix (videos × languages × formats × resolutions):

```bash
python3 "$SKILL_DIR/scripts/production.py" init /path/to/production \
  --videos 2 --languages en,te --durations 60,90 \
  --formats 9:16,16:9 --resolutions 1080,2160 --commercial
```

Every cell of the matrix is a deliverable with a status. A cell is complete only when its file exists and its validation report passed.

## 2. Research

Run two research tracks and record both:

1. **Assets** — footage, photographs, illustrations, animations, music, sound effects, fonts, voices. Follow [research-and-licensing.md](research-and-licensing.md); every candidate goes into `research/source-register.json` with its real URL and licence evidence.
2. **Editing references** — professional films, documentaries, advertisements, and creators relevant to the script. Follow [editing-research.md](editing-research.md); the output is an original style guide in `plan/<video>/style.json`, not a copy of any reference.

When the script is spoken word that needs evidence-style cutaways, the adjacent `find-broll` skill's routing and placement rules apply to those beats.

## 3. Creative direction and storyboard

From the script and style guide, write per video:

- the thesis and emotional arc in one paragraph each;
- `plan/<video>/scenes.json`: scenes with purpose, narration text per language, on-screen text per language, visual asset, framing, motion, transition, and sound cues (format in [scene-planning-and-sync.md](scene-planning-and-sync.md));
- a storyboard: one representative frame or sketch description per scene, then real stills once assets exist (`video_workbench.py stills` on the chosen clips);
- a shot list: asset ID, source in-point, framing, move, and why the shot illustrates the line.

Choose visuals for meaning. A correct, plain shot beats a decorative, irrelevant one. Do not use AI-generated or staged footage to depict real events, people, or places as if it were documentary evidence.

## 4. Narration, timing, and synchronization

Produce narration per language (voice actor recordings, licensed TTS, or the user's own voice), measure every file, and derive timing from the measurements — never from word counts or another language's timing:

```bash
python3 "$SKILL_DIR/scripts/production.py" timing /path/to/production \
  --video v01 --language te
```

The timing map places scenes, narration, captions, music, and effects on one frame grid and reports the difference from the target duration. Details and fitting strategy: [scene-planning-and-sync.md](scene-planning-and-sync.md).

## 5. Build

Pick the rendering lane as usual. Script-driven productions usually use the bundled `ScriptVideo` Remotion composition, which reads a timing map converted to props per format:

```bash
python3 "$SKILL_DIR/scripts/production.py" props /path/to/production \
  --video v01 --language te --format 9:16 --resolution 1080 \
  --motion-project /path/to/production/remotion
```

Follow [remotion-integration.md](remotion-integration.md) for the official Remotion Agent Skills, previews, captions, fonts, and rendering. Use FFmpeg or the hybrid lane where they are simpler.

## 6. Preview and revise

Work in the cheap passes of the main skill: Studio preview or stills first, then a low-resolution draft per format, contact sheets, and strips around every transition and caption change. Review each language separately; a layout that fits English may overflow in another script. Log every revision (what changed, why) in `reports/revisions.md`.

## 7. Render, validate, and deliver

Render each matrix cell, validate it with `video_workbench.py validate` into `<deliverable>.validation.json` next to the file, then check the whole matrix and the register:

```bash
python3 "$SKILL_DIR/scripts/production.py" audit /path/to/production
python3 "$SKILL_DIR/scripts/production.py" status /path/to/production
```

`status` reports a cell as validated only when the file exists, its validation report passed, and the report's SHA-256 matches the file. Anything else is reported as missing, unvalidated, failed, stale, or upscaled (a 4K cell that needs upscaling the user has not accepted).

To render, master, sync-check, and validate one cell in a single step:

```bash
python3 "$SKILL_DIR/scripts/production.py" render /path/to/production \
  --video v01 --language te --format 9:16 --resolution 1080 \
  --motion-project /path/to/production/remotion
```

Deliver, organized per video and language:

- final videos for every validated matrix cell;
- caption files (SRT) per language;
- project files: `production.json`, scenes, style guide, timing maps, Remotion props, and the motion project source;
- `research/source-register.json` and a human-readable credits/licence list;
- `research/references.json` with what each editing reference contributed;
- `research/approvals.json`;
- review artifacts and validation reports;
- `reports/production-report.md`: what was made, what was verified (with numbers), what failed or was not feasible and why, and open decisions.

## Honesty rules

- Never report a download, permission, licence, render, or check as successful without the artifact that proves it: the file and its checksum, the licence page evidence, the approval record, the validation report.
- When a source is unreachable (blocked, login-only, bot challenge, paywall), record it as unavailable with the reason. Do not substitute a guess, a fabricated URL, or a bypass.
- If a deliverable cannot meet the brief (duration, 4K, a language voice), say so in the report with the measured reason and the options.
