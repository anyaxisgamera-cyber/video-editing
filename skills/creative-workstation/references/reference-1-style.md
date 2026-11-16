# Reference Video 1 — "lavender-luxe" editing grammar

Status: the two reference screen recordings were **not present** in the workstation when it was built. This
grammar is built from the written brief (purple/lavender backgrounds, subtle grid, 3D chess pieces and floating
objects, large elegant serif type, animated reveals, blur-in/blur-out, moving foreground objects, layered
compositions, silhouettes, brand logos, scene-by-scene transitions, promo composition). When the video is supplied,
run `scripts/analyze_reference.py REF.mp4 OUT --deep` and adjust the numbers below to the measurements.

The analyzer was validated on a render with known edit decisions: it found all 9 blur transitions at their exact
timestamps, measured 95.7 BPM for a 96 BPM bed, reported 0 hard cuts for an all-dissolve edit, and 63 % purple share.

## Layers (back → front), every scene

1. **Background** — radial lavender gradient (`light`), lilac→violet (`dusk`) or violet→ink (`dark`); slowly
   drifting 96 px grid with intersection dots; soft bokeh orbs; film grain; vignette. (`layers/LuxeBackground.tsx`)
2. **Far objects** (depth 0) — small, blurred (6 px @1080p), slow parallax: orbs, distant pieces.
3. **Mid objects** (depth 1) — sharp 3D chess pieces turning slowly (Blender turntables, cross-faded), gentle bob,
   contact shadow.
4. **Scene content** — typography, panels, logos, silhouettes, stats, icon cards.
5. **Foreground objects** (depth 2) — large, blurred (9 px), fastest drift across frame → depth and motion.

## Typography

- Display: Instrument Serif (accent words in Instrument Serif Italic, accent colour). Alternates: Gloock, Italiana,
  Libre Baskerville, EB Garamond. Body/kicker: Instrument Sans, tracked caps (0.32 em) with a hairline rule.
- Headline sizes @1080p: 150–170 px titles, 104–112 px hero lines, 74–92 px statements, 30 px body.
- **Blur-in**: per word (or letter) — blur 18 px → 0, opacity 0 → 1, rise 26 px, 22-frame ease-out, 5-frame stagger.
- **Blur-out**: per word, blur → 14 px, opacity → 0, 14 frames, finishing ~10 frames before the scene transition.
- Accent syntax in storyboards: `Every move *matters.*`

## Scene vocabulary (engine/src/scenes/Scenes.tsx)

| Type | Use |
|---|---|
| `TitleReveal` | Opening / chapter title: kicker, big serif headline, subtitle |
| `ChessHero` | 3D piece turntable on one side, copy on the other |
| `MediaPanels` | 1–3 rounded footage panels (hero / duo / trio layouts), layered and offset, captions |
| `Silhouette` | Cut-out figure filled solid with a lavender rim glow + copy |
| `Statement` | Centered quote, quote mark, underline draw, attribution |
| `Stats` | Counting serif numerals |
| `IconFeatures` | Icon cards (Lucide icons) |
| `LogoWall` | Staggered blur-in logos |
| `EndCard` | Logo lockup, tagline, CTA, fade out |

## Motion & transitions

- Transitions (`engine/src/transitions.tsx`): `blurDissolve` (default; blur 22 px + 5 % scale), `zoomBlur`,
  `softWipe` (diagonal feathered mask), `iris`, `flash` (lavender bloom), `slideLeft`, `slideUp`, `cut`.
- Transitions are centred on musical downbeats (one beat long by default at 96 BPM = 0.625 s).
- Footage panels: enter with blur + rotate ±2° + scale 0.9 → 1, slow Ken Burns inside, lateral drift.
- Colour: footage graded with `lavender_noir.cube` (violet shadows, lilac highlights, restrained saturation).

## Sound

Pad-led minor progression (Dm9–Bbmaj7–Gm9–Asus) at 96 BPM; groove after 4 bars; kick/hats in the full section.
Whoosh peaks on every transition, impact on flash/zoom, swell resolving into each blur-in title, shimmer on logo
reveals, ticks on counting stats, riser into the end card. Master −16 LUFS integrated, −1.5 dBTP.
