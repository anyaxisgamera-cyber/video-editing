# AXHARRY: footage sources, licences and credits

Every film clip in the AXHARRY FINAL videos comes from an Internet Archive item. Each item's licence field (`licenseurl` / `rights`) was read through the archive.org metadata API on 2026-11-22, before download. Only the picture is used: no source audio, music or dialogue appears in the edit. The narration, music and sound effects are the project's own.

The machine-readable list is `footage/manifest.json`, and the per-shot plan is `footage.selection.json`.

## Sources used

| Film | Internet Archive item | Licence on the item | Attribution |
|---|---|---|---|
| Superman: *The Mechanical Monsters* (Fleischer Studios, 1941) | `superman_mechanical_monsters` | CC0 1.0 | not required (credited anyway) |
| Superman: *The Mad Scientist* (Fleischer Studios, 1941) | `mad-scientist-superman-fleischer` | Public Domain Mark 1.0; the item says "fell into the U.S. public domain when its copyright wasn't renewed" | not required (credited anyway) |
| *Metropolis* (Fritz Lang, 1927) | `metropolis-1927-bdrip-1080p-x-265-dts-hd-ma-5.1-d-0ct-0r-lew-sev` | Public Domain Mark 1.0 | not required (credited anyway) |
| *The Cabinet of Dr. Caligari* (Robert Wiene, 1920) | `DasKabinettdesDoktorCaligariTheCabinetofDrCaligari` | Public domain (creativecommons.org/licenses/publicdomain) | not required (credited anyway) |
| *Tears of Steel* (Blender Foundation, 2012) | `Tears-of-Steel` | CC BY 3.0 | **required**: shown on the end card |
| *Sintel* (Blender Foundation, 2010) | `Sintel` | CC BY 3.0 | **required**: shown on the end card |
| *Spring* (Blender Animation Studio, 2019) | `springopenmovie` | CC BY 4.0 | **required**: shown on the end card |

End-card credit text (also use it in the video description when publishing):

> Footage: Sintel (CC BY 3.0) & Tears of Steel (CC BY 3.0) Blender Foundation | Spring (CC BY 4.0) Blender Studio
> Public domain: Superman (Fleischer Studios, 1941) | Metropolis (1927) | The Cabinet of Dr. Caligari (1920)

For the CC BY works, the edit changes the material: it is cropped, regraded, and has captions and effects added. Licence links:
- https://creativecommons.org/licenses/by/3.0/
- https://creativecommons.org/licenses/by/4.0/

## Cautions before publishing

- **Metropolis:** the film entered the US public domain in 2023. This file is a restoration rip. Separate rights in the restoration and the score have not been verified (the score is not used), and neither has public-domain status outside the US. If the video will be monetized or distributed outside the US, replace these shots or confirm their status first.
- **Fleischer Superman:** the cartoons themselves are public domain in the US. The *Superman* character and trademarks are still owned by DC. The edit uses no Superman, Clark Kent or Lois Lane shots and no logos or title cards: only the villains, machines, robots, jewels, a newspaper insert and a planet shot. One Clark Kent and Lois Lane desk shot was removed during selection for this reason. Even so, avoid putting Superman in titles or thumbnails.
- **Caligari:** the source is only 320×240, so its two shots look soft. That is consistent with the film-grain treatment, but it is visibly lower in resolution than the rest.

## Sources checked and not used

| Source | Result |
|---|---|
| Agent 327 (Blender Studio) | CC BY-ND 4.0: no derivatives, so excluded |
| Kodansha Licensing, Bandai Namco Filmworks | Licensing-inquiry portals only; no downloadable footage |
| Sony Pictures, MGM, Disney Studios licensing | Licensing-inquiry portals only; no downloadable footage |
| Japanese Animated Film Classics | Streaming and viewing only; no download or reuse permission found |
| Open Images (openimages.eu) | Unreachable from this environment (connection timed out) |
| OS Video / The Studio Free Videos (thestudio.io) | These pages point to the same Blender open movies (Sintel, Tears of Steel, Spring) that were used here |
| PubToons | A streaming catalogue of public-domain cartoons; the Fleischer titles were taken from the Internet Archive instead, because it states the licence on each item |
| Pixabay, Mixkit | Excluded at your request |
| Classroom of the Elite | No clips were supplied, and none are licensed for reuse, so none were used |
