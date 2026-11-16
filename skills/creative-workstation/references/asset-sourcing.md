# Asset sourcing (Reference Video 2 workflow) — status, licenses, rules

Workflow shown in Reference Video 2: transparent PNG objects from PNGEgg, SVG/PNG icons and logos from Icon-Icons,
cinematic footage placed in rectangular panels. The exact source of the movie clips in that recording is **not
identified** — do not guess it and do not download film/TV scenes.

## Site status from this workstation (tested 2026-11-16, Ubuntu container behind an egress proxy)

| Site | Reachable | What happened | Use here |
|---|---|---|---|
| https://www.pngegg.com/ | **No** | HTTP 403 `cf-mitigated: challenge` (Cloudflare JS challenge), also in headless Chromium | Not used. Licence pages unreadable from here. |
| https://icon-icons.com/ | **No** | Cloudflare "Sorry, you have been blocked" page | Not used. Replaced by Lucide (ISC) + Simple Icons (CC0) via npm. |
| https://www.pexels.com/videos/ | **No** | Cloudflare challenge | Official API needs an API key (`Authorization` header) — not configured. |
| https://pixabay.com/videos/ | **No** | Cloudflare challenge | Official API needs an API key (query parameter) — not configured. |
| https://mixkit.co/ | **Yes** | Pages + `assets.mixkit.co` downloads work | `scripts/collect_mixkit.py` with per-item licence enforcement |

Do not bypass bot challenges (no stealth browsers, no cookie replay). Ask the user for local copies or API keys.

## Mixkit licences — verified text (https://mixkit.co/license/modal/<type>/)

- **Stock Video Free License** (`videoFree`): commercial and non-commercial, YouTube, ads, broadcast; no attribution
  required; limits in Mixkit User Terms (no standalone redistribution).
- **Stock Video Restricted License** (`videoRestricted`): *personal projects only* — not commercial, advertising,
  company social media, or monetised YouTube.
- **Stock Music Free License**: web/social/VOD/podcasts/ads OK; **not** CDs/DVDs, TV/radio, video games; no remixing
  into a music-only track, no Content ID registration.
- **Sound Effects Free License**: broad (incl. games, TV, film) inside an End Product; no standalone redistribution.

Finding: on restricted clips the item's visible `data-license` says `videoRestricted` while the page's JSON-LD says
`videoFree`. The JSON-LD is generic; the collector requires both signals to agree and skips the item otherwise
(verified on "purple glow moon moves through clouds", id 45592, whose page text reads "personal use only, under the
Mixkit Restricted License"). Newer items (ids ≳ 99 000) only download through a JS modal — the collector reports them
as `failed` rather than scraping the modal.

## Open-licence replacements used

| Need | Source | Licence | Notes |
|---|---|---|---|
| UI icons (SVG/PNG) | `lucide-static@1.73.0` (npm) | ISC | Keep notice when redistributing SVG source |
| Software/brand logos | `simple-icons@16.38.0` (npm) | CC0-1.0 for path data | **Trademarks still apply** — nominative use only |
| Display/body fonts | anthropics/skills `canvas-design/canvas-fonts`, Ubuntu `fonts-ebgaramond-extra` | SIL OFL 1.1 | Embedding OK; don't sell the font alone |
| Brand logos for demos | `synth_assets.py logos` (Regalia, Aurelia, Noctis, Vanta, Lumen) | original | Fictional companies |
| 3D pieces/objects | `blender_assets.py` | original | Procedural |
| Music + SFX | `audio_synth.py` | original | Synthesised from scratch |

## Catalogue fields (catalog.json / CATALOG.md)

`source_url` (direct asset URL), `source_page`, `local_path`, `probe.format`, `probe.width/height/duration/fps/frames`,
`license`, `commercial_use` (yes / personal-only / unverified), `usage_restrictions`, `attribution`, `sha256`,
`extra.license_evidence`, `extra.derived_from` for graded clips and cut-outs (they inherit the source licence).
