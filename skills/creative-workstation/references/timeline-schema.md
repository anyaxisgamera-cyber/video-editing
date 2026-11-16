# Storyboard → timeline schema

`storyboard.json` (authored) is compiled by `scripts/timeline.py compile` into `timeline.json` (frames), which is
the only input the Remotion engine and `render.py` read. Re-edit = change the storyboard, recompile, re-render.

```jsonc
{
  "meta": {"title": "…", "width": 1920, "height": 1080, "fps": 30, "bpm": 96, "targetDuration": 60},
  "audio": {
    "music": {"generate": {"style": "noir", "seed": 7}},      // or "lib/music/<file>.wav"
    "musicVolume": 0.9, "autoSfx": true,
    "loudness": {"I": -16, "TP": -1.5, "LRA": 11}
  },
  "defaults": {"transition": {"type": "blurDissolve", "beats": 1}},
  "scenes": [
    {
      "id": "open", "type": "TitleReveal", "bars": 3,            // or "seconds": 7.5
      "background": {"variant": "light|dusk|dark", "grid": true, "orbs": true, "grain": true, "image": "lib/…"},
      "floating": [
        {"sprite": {"kind": "sequence", "dir": "lib/3d-assets/chess-king-pearl", "frames": 72, "revolutionSeconds": 14},
         "x": 14, "y": 64, "size": 560, "depth": 1, "drift": [4, 0], "bob": 10, "delay": 0.4, "rotate": 0, "opacity": 1},
        {"sprite": {"kind": "image", "src": "lib/transparent-png/…png"}, "x": 80, "y": 20, "size": 200, "depth": 0}
      ],
      "props": {"kicker": "…", "title": "Every move *matters.*", "subtitle": "…"},
      "transition": {"type": "zoomBlur", "beats": 1},            // into the NEXT scene
      "sfx": [{"src": "lib/sound-effects/…wav", "at": 1.2, "volume": 0.5}]   // extra cues, seconds from slot start
    }
  ],
  "variations": { … }   // used by `timeline.py expand` to rotate content in long-form chapters
}
```

Positions (`x`, `y`) are % of the frame; sizes and drifts are px at 1080p (scaled by height/1080, so 4K is identical).

## Scene props

| Type | Props |
|---|---|
| `TitleReveal` | `kicker`, `title`, `subtitle`, `titleSize` (150), `align` (center/left), `mode` (words/letters), `maxWidth`, `exitText` |
| `ChessHero` | `piece` (sprite), `pieceSize` (820), `side` (right/left), `kicker`, `title`, `titleSize`, `body` |
| `MediaPanels` | `panels[]` = `{kind:"video",src,trimBefore,caption}` / `{kind:"image",src}` / `{kind:"sequence",dir,frames,fps}`, `layout` (hero/duo/trio), `kicker`, `title` |
| `Silhouette` | `silhouette` (PNG), `side`, `kicker`, `title`, `body` |
| `Statement` | `text`, `attribution`, `size` |
| `Stats` | `title`, `items[] = {value, prefix, suffix, decimals, label}` |
| `IconFeatures` | `kicker`, `title`, `items[] = {icon, label, text}` |
| `LogoWall` | `kicker`, `title`, `logos[]`, `columns`, `logoHeight` |
| `EndCard` | `logo`, `logoHeight`, `tagline`, `cta` |

## Compiled timing model

Boundaries `B_k` are absolute frames rounded once from absolute time (no drift on 60-minute timelines). A transition
of `T` frames (even) is centred on its boundary: `scene_i.from = B_i − T_{i−1}/2`,
`scene_i.durationInFrames = (B_{i+1} − B_i) + T_{i−1}/2 + T_i/2` — identical to `<TransitionSeries>` layout.
`audio.cues[]` holds absolute seconds: `at` (file start) and `hit` (the sync point: whoosh peak on the boundary,
swell end on the title reveal, etc.).
