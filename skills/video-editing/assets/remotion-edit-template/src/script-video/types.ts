import type {Caption} from '@remotion/captions';

// Props written by scripts/production.py (`props` / `render`) from a per-language timing map.
// Every time is in frames of canvas.fps except captions, which use the official Caption type (milliseconds).

export type SceneMove = {
  type: 'static' | 'push_in' | 'pull_out' | 'pan_left' | 'pan_right' | 'tilt_up' | 'tilt_down';
  amount: number; // zoom fraction (0.06 = 6 %) or travel as a fraction of the frame
};

export type SceneMedia = {
  kind: 'video' | 'image' | 'none';
  src: string | null; // path inside public/, resolved with staticFile()
  trimBefore: number; // frames into the source
  playbackRate: number;
  fit: 'cover' | 'contain';
  focusX: number; // 0..1, keeps the subject in frame when cropping to 9:16 or 16:9
  focusY: number;
  width: number | null; // source pixels (after rotation), used for focus-aware cover crops
  zoom?: number; // cover only: punch-in on top of the cover scale, centred on the focus point (1 = none)
  height: number | null;
};

export type ScriptScene = {
  id: string;
  from: number;
  durationInFrames: number;
  media: SceneMedia;
  move: SceneMove;
  transitionIn: {type: 'cut' | 'fade' | 'fade_from_black' | 'dip'; durationInFrames: number};
  transitionOut?: {type: 'dip'; durationInFrames: number} | null; // fade to black before the next scene's fade-in
  onScreen: {text: string; from: number; durationInFrames: number} | null;
  onScreenStyle?: 'title' | 'lower_third' | 'top';
};

/** One look for the whole video (from plan/<video>/style.json) so footage from different sources matches. */
export type Look = {contrast: number; saturation: number; brightness: number; warmth: number; vignette: number};

export type ScriptVideoProps = {
  canvas: {width: number; height: number; fps: number; durationInFrames: number; background: string};
  format: string;
  language: {code: string; direction: 'ltr' | 'rtl'; fontFamily: string; fontSrc: string | null};
  scenes: ScriptScene[];
  narration: {id: string; src: string; from: number; durationInFrames: number}[];
  music: {src: string; keyframes: [number, number][]; loop: boolean} | null;
  sfx: {src: string; from: number; volume: number}[];
  captionTracks: {sceneId: string; captions: Caption[]}[];
  captionStyle: {
    fontSize: number;
    bottom: number; // fraction of the canvas height
    maxWidth: number; // fraction of the canvas width
    combineTokensWithinMilliseconds: number;
    highlightActiveWord: boolean;
  };
  onScreenStyle: {fontSize: number; top: number};
  look?: Look;
};
