# Professional editing research and an original style

Study relevant professional work before designing the edit, then write an original style guide for this script. References inform decisions; they are never copied shot for shot, and their footage, music, logos, and typography are never reused without a licence.

## Choose references

Pick 4–8 references across at least two of these kinds, matched to the script's purpose, audience, platform, and format:

- documentaries and explainers on similar subjects;
- cinematic short films, brand films, and trailers;
- advertisements in the same category;
- creators who publish successfully in the target format (vertical short-form or widescreen long-form) and language.

Record each in `research/references.json` with the real URL, creator, title, date, format, and why it is relevant. Do not download a reference unless its terms allow it; watching or reading public pages and measuring a legitimately obtained copy are different from reusing it.

## Analyse

For references you can legitimately obtain as files, use the adjacent `analyze-video-editing` skill for measured shots, cuts, camera motion, titles, and audio. For streamed-only references, take timecoded notes and label them as observation, not measurement.

Analyse each reference for:

- **storytelling** — hook, structure, where the turn happens, how it ends, how claims are supported;
- **pacing** — average and variation of shot length, where the rhythm changes, relation to speech and music;
- **transitions** — which kinds, how long, and what change in meaning each one marks;
- **typography** — families, weights, sizes relative to frame height, line length, entrance and exit motion, caption style;
- **motion graphics** — what they explain, how restrained they are, how they enter and leave;
- **colour** — key, contrast, saturation, temperature, consistency across sources;
- **camera movement** — locked-off vs moving, push-ins, pans, handheld, speed;
- **sound design** — music role and level under speech, ambience, transition effects, silence.

Separate evidence (measured or timecoded) from interpretation.

## Write the style guide

Synthesize what fits this script and write `plan/<video>/style.json`:

```json
{
  "intent": "calm, trustworthy documentary tone for a general audience",
  "pacing": {"average_shot_seconds": 3.5, "hook_shot_seconds": 1.8, "rule": "cut on sentence boundaries; hold on scripture"},
  "transitions": [{"type": "cut", "use": "default"}, {"type": "dissolve", "frames": 15, "use": "time or place change"}],
  "camera": {"moves": ["slow push-in on emotional beats"], "max_digital_zoom": 0.08},
  "colour": {"look": "warm highlights, neutral shadows", "lut": null},
  "typography": {"titles": "serif 84px at 1080 width", "captions": "sans, 2 lines max, bottom safe area"},
  "sound": {"music": "sparse piano bed, ducked 9–12 dB under narration", "sfx": "only motivated, no whooshes on cuts"},
  "references": ["r01", "r03"],
  "originality_note": "combines r01's pacing with r03's typography restraint; no shots, titles, or music reused"
}
```

The guide must be specific enough to implement and check, and different enough from any single reference that the result is original. When the user's brand or brief conflicts with a reference, the brief wins.
