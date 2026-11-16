// Timeline contract shared with scripts/timeline.py (the compiler) and scripts/render.py (the renderer).
// Everything is in FRAMES once compiled; the storyboard (seconds) is compiled to this.

export type TransitionType =
  | 'blurDissolve'
  | 'zoomBlur'
  | 'slideLeft'
  | 'slideUp'
  | 'softWipe'
  | 'iris'
  | 'flash'
  | 'cut';

export type SpriteSource =
  | {kind: 'image'; src: string}
  | {kind: 'sequence'; dir: string; frames: number; pattern?: string; revolutionSeconds?: number; startOffset?: number};

export type FloatingObject = {
  sprite: SpriteSource;
  x: number; // 0..100 (% of width) — centre
  y: number; // 0..100 (% of height) — centre
  size: number; // px at 1080p (height of the sprite box)
  depth?: number; // 0 = far (small parallax, blurred), 1 = mid (sharp), 2 = foreground (fast, blurred)
  drift?: [number, number]; // px/second at 1080p
  bob?: number; // px amplitude at 1080p
  rotate?: number; // deg/second
  delay?: number; // seconds after scene start before it appears
  opacity?: number;
  shadow?: boolean;
};

export type Background = {
  variant: 'light' | 'dark' | 'dusk';
  grid?: boolean;
  orbs?: boolean;
  grain?: boolean;
  image?: string; // optional still behind everything (staticFile path)
};

export type SceneBase = {
  id: string;
  type: string;
  from: number; // absolute start frame (informational; TransitionSeries lays out)
  durationInFrames: number;
  transition?: {type: TransitionType; durationInFrames: number}; // into the NEXT scene
  background?: Background;
  floating?: FloatingObject[];
  props: Record<string, unknown>;
};

export type Timeline = {
  meta: {
    title: string;
    width: number;
    height: number;
    fps: number;
    theme?: string;
    bpm?: number;
    durationInFrames: number;
  };
  scenes: SceneBase[];
  audio?: unknown; // consumed by render.py / mix (ffmpeg), not by Remotion
};
