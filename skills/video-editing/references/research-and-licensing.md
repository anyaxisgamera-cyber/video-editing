# Asset research, comparison, and the licensing register

Find real, usable assets for every scene, compare them, and keep a register that proves where each one came from and why it may be used. Never invent an asset, URL, creator, or licence. Never download what the source does not permit.

## Search widely, then narrow

Search several kinds of source for each scene before choosing:

| Kind | Examples of where to look | Licence model to verify |
|---|---|---|
| Stock footage and photos | free stock libraries, paid stock libraries | site licence, sometimes per-item tiers (free vs restricted, editorial-only) |
| Open repositories | Wikimedia Commons, Internet Archive, Openverse, government and space-agency media libraries | per item: public domain, CC0, CC BY, CC BY-SA, or "no known restrictions" with exceptions |
| Primary sources | the subject's own site, press kits, official channels | press/media terms; often editorial use only |
| Music | free music libraries, production-music libraries, CC catalogues | per track; check broadcast, Content ID, and remix limits |
| Sound effects | SFX libraries, CC sound archives | per sound; CC BY requires credit, CC BY-NC excludes commercial use |
| Fonts | Google Fonts, Noto, foundry sites | OFL or commercial EULA; check video embedding |
| Voices | TTS services and open models, voice actors | model or service licence; commercial-use flag; voice-cloning consent |
| Animation | Lottie libraries, motion template sites | per item; check redistribution and modification |

Prefer an official API over scraping when one exists. If a site answers automated clients with a bot challenge, login wall, or block, treat it as unavailable from this environment. Do not bypass protections, rotate identities, or reuse someone else's credentials. If an API key or account would unlock the source, raise an approval request ([approvals.md](approvals.md)).

Search metadata first and download only likely winners. Inspect real search and item payloads before writing parsers.

## Compare candidates

Score each serious candidate on:

- **Relevance** — does it show what the line means, in the right place, era, and culture?
- **Quality** — resolution, bit depth, noise, compression, stabilization, exposure, focus.
- **Technical suitability** — orientation and how it crops to 9:16 and 16:9, usable duration from the in-point, frame rate, motion that fights or helps the planned move, watermarks, burned-in text.
- **Licence** — commercial use, attribution, share-alike, editorial-only, territory, duration, modification, and model/property releases for people and trademarks.
- **Availability** — direct download, API, login, cost, rate limits, regional blocks.

Pick the best candidate per scene and keep runners-up as `candidate` in the register. For subjective choices with no clear winner, present the top options with stills instead of guessing.

## Verify the licence at download time

Read the licence on the item page itself, not only the site's general licence. Some sites mark individual items with different licences. Record:

- the exact licence name and URL;
- a short quote or marker that shows the item's licence (for example the page's per-item licence label);
- the date and time you checked;
- commercial use, attribution, share-alike, and other restrictions as booleans or short notes.

If the item's licence and the site's general terms disagree, or the evidence is ambiguous, do not use the item without asking.

## The source register

`research/source-register.json` is the single source of truth. Add each downloaded or generated file with real facts measured from the local file:

```bash
python3 "$SKILL_DIR/scripts/production.py" register-add /path/to/production \
  --id a07 --kind video --file assets/a07-lake-at-dusk.mp4 \
  --title "Calm lake at dusk" --source-url "https://…/item-page/" \
  --download-url "https://…/file.mp4" --creator "…" \
  --licence "…" --licence-url "https://…" --commercial-use yes \
  --attribution-required no --evidence "item page shows licence label '…'" \
  --status downloaded
```

The command computes the SHA-256, probes duration and geometry, and timestamps the entry. It never downloads anything. Entries for user-supplied files use `--source-url user-supplied`; generated files (TTS, synthesized music, rendered graphics) use `--source-url generated` plus the generator and its licence.

Statuses: `candidate` → `approved` (when approval was needed) → `downloaded` → `used`, or `rejected` with a reason. Paid items carry `--cost` and the approval ID.

`production.py audit` fails the project when:

- a scene references an asset that is not in the register, or not downloaded;
- a downloaded file is missing or its checksum changed;
- a commercial production uses an asset whose licence forbids commercial use;
- an attribution-required asset is missing from the credits list;
- a paid asset has no approved approval record;
- licence evidence or the check date is missing.

## Credits

Generate the credits list from the register (`production.py audit --credits reports/credits.md`) and include it in the delivery and, where the licence requires, on screen or in the description.
