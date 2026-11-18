# Stock media through official APIs

Use `scripts/stock_media.py` when a beat is best served by licensed stock footage or photos
(concept, mood, or symbolic beats), never for receipts, products, or people-specific claims.

| Provider | Endpoint | Auth (documented) | License |
|---|---|---|---|
| Pexels | `api.pexels.com/videos/search`, `/v1/search` | `Authorization: <key>` header | [Pexels License](https://www.pexels.com/license/) |
| Pixabay | `pixabay.com/api/videos/`, `/api/` | `key=<key>` query parameter | [Pixabay Content License](https://pixabay.com/service/license-summary/) |

Both are free; get keys at <https://www.pexels.com/api/> and <https://pixabay.com/api/docs/>.

## Keys

- Never pass keys on the command line, commit them, or paste them into chat.
- The script reads `PEXELS_API_KEY` and `PIXABAY_API_KEY` from the environment. In a hosted
  agent environment, the account owner adds them in the environment's settings.
- Pexels can alternatively be supplied by a key-injecting egress proxy only if the proxy can
  send the raw `Authorization: <key>` header (no `Bearer` prefix).
- Pixabay's key travels in the query string, so a header-injecting proxy cannot supply it.
  The script redacts it from errors, cached responses, and saved raw payloads.

## Workflow

1. Write a beat plan (`id`, `narration`, `meaning`, `duration`, 2–3 `queries`, `avoid` words).
   Query for what the line *means* (e.g. "sand falling through fingers" for "temporary desires"),
   not just its nouns.
2. Inspect one real response first: `stock_media.py search "query" --raw-dir raw/`.
3. `stock_media.py fetch plan.json --out broll/ --raw-dir broll/raw` downloads one chosen
   rendition per beat (smallest that covers the delivery frame; portrait preferred), saves
   thumbnails of runners-up, and writes `stock-manifest.json` with provider, ID, page URL,
   creator, license, rendition, checksum, and retrieval time. No asset is reused across beats.
4. Review every chosen clip and thumbnail by eye; swap with `--refresh` or by editing the plan.
   Status stays `sourced` until a human approves it.
5. Strip clip audio, cover-crop to the delivery frame, and credit creators where practical
   (Pexels appreciates attribution; neither license requires it).

## Limits and etiquette

- Pexels: 200 requests/hour, 20,000/month. Pixabay: 100 requests/60 s and responses must be
  cached for 24 h; the script caches all responses for 24 h under `~/.cache/stock-media`.
- Do not redistribute unaltered files, imply endorsement by depicted people or brands, or
  use identifiable people in sensitive contexts (e.g. implying they committed a sin).
- Keep downloaded media out of version control.
