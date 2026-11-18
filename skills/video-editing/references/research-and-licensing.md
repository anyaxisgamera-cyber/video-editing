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

## Automated discovery and download

`production.py discover` searches providers and writes every hit to the register as `candidate`, with the provider's licence normalized to `commercial_use` = `yes`, `no`, `conditional` (share-alike, or a rights advisory that needs a person's check) or `unknown`. In a `--commercial` production, `no` and `unknown` are dropped at search time; `conditional` needs an approved approval record before any render.

```bash
python3 "$SKILL_DIR/scripts/production.py" discover /path/to/production \
  --query "lighthouse at night" --kind image --providers openverse:wikimedia,nasa,loc,met --scene v01/s03 --thumbs
python3 "$SKILL_DIR/scripts/production.py" fetch /path/to/production --id c1a2b3c4 --max-wait 120
```

| Provider | Media | Key | Licence handling |
|---|---|---|---|
| `openverse` (`openverse:wikimedia`, `openverse:flickr`, …) | images, audio | none | per-item CC licence; `--commercial-only` sends `license=cc0,pdm,by` |
| `wikimedia` | images, video, audio | none | per-file licence from `extmetadata` |
| `nasa` | images, video | none | NASA media guidelines; logos and identifiable people excluded |
| `met` | images | none | CC0 for Open Access objects only (`isPublicDomain`) |
| `loc` | images | none | per-item rights advisory: "No known restrictions on publication" → `yes`; U.S.-Government-work advisories → `conditional`; anything else → `unknown` |
| `mixkit` | video, music, sfx | none | read from each item page; `videoRestricted` clips are not commercial |
| `pexels` | images, video | `PEXELS_API_KEY` (sent as the bare `Authorization` header) | Pexels License |
| `pixabay` | images, video | `PIXABAY_API_KEY` (query parameter, redacted in logs) | Pixabay Content License; responses cached 24 h as its terms require |

`fetch` re-reads the licence from the provider before downloading and refuses if it no longer allows the production's use. It picks the smallest rendition that needs no upscaling, writes to a `.part` file, checks the length, decodes the file, and only then marks it `downloaded` with its SHA-256 and measured size. Every failure is recorded in `download_attempts` and the entry stays a `candidate`.

Rate limits are honoured, never evaded: `Retry-After` is waited out up to `--max-wait`, then the item fails. Wikimedia asks automated clients to fetch standard thumbnail widths (`960`, `1280`, `1920`, `3840`) instead of originals; `fetch` tries the original and then each smaller standard width, and `feasibility` reports the resulting upscale. From shared cloud egress, `upload.wikimedia.org` can answer HTTP 429 for long periods — switch to another source for that scene rather than retrying in a loop. Without a key, Pexels and Pixabay report themselves unavailable; creating those free accounts is the user's decision ([approvals.md](approvals.md)).

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
