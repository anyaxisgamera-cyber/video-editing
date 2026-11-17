# Quality gates

## Editorial

- The opening establishes subject and context quickly.
- Every kept section advances the intended story.
- Cuts preserve continuity or make the discontinuity purposeful.
- Transitions correspond to changes in meaning or attention.
- The ending resolves cleanly and does not expose an accidental hold.

## Visual

- Framing, crops, and safe areas match the delivery format.
- Text is readable at delivery size and remains long enough to read.
- Masks and alpha edges hold against light and dark backgrounds.
- No unintended borders, matte rectangles, duplicate layers, or ghosting.
- Graphics use a coherent type, color, spacing, and motion system.
- Real product interfaces are represented authentically.

## Audio

- Dialogue is intelligible and prioritized.
- Cuts and track entrances do not click.
- Music and effects support rather than obscure.
- The final loudness and true peak fit the delivery contract.
- The delivered sample rate is explicit.

## Technical

- One intended video stream and the intended audio/subtitle streams.
- Correct dimensions, aspect ratio, frame rate, duration, and pixel format.
- Full decode returns no errors.
- The final file starts promptly and plays through its end.
- Review artifacts come from the final candidate, not a stale draft.
- Validation report and SHA-256 checksum match the delivered file.

## Research and licensing

- Every asset on screen or in the mix is in the source register with a real source URL (or `generated` / `user-supplied`), licence, evidence, and check date.
- No asset's licence conflicts with the deliverable's use (commercial, broadcast, territory, attribution, share-alike).
- Paid assets, accounts, uploads, and accepted terms have an approved record in the approvals log.
- Required attributions appear in the credits and, where the licence requires it, on screen.
- `production.py audit` passes.

## Languages and formats

- Each language has its own timing map built from its own measured narration; none reuses another language's cut points.
- Captions are the language's exact narration text, within its line-length and reading-rate limits, and in a font that covers its script.
- Names and terms are pronounced as the lexicon specifies; on-screen text fits and reads naturally in every language.
- Each format is reframed, not letterboxed; subjects survive the crop and text stays inside the format's safe area.
- 4K deliverables are native, or the user accepted the reported upscale.

## Production honesty

- Every reported download, permission, render, and check is backed by its file, record, or report.
- `production.py status` matches what is delivered; anything missing, failed, stale, or upscaled is reported with its reason.
