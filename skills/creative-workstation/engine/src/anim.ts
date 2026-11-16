import {interpolate} from 'remotion';
import {EASE_OUT, EASE_IN_OUT} from './theme';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 0→1 progress of an entrance that starts at `start` and lasts `dur` frames. */
export const enter = (frame: number, start: number, dur: number) =>
  interpolate(frame, [start, start + dur], [0, 1], {...clamp, easing: EASE_OUT});

/** 0→1 progress of an exit. */
export const leave = (frame: number, start: number, dur: number) =>
  interpolate(frame, [start, start + dur], [0, 1], {...clamp, easing: EASE_IN_OUT});

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Unit scale: every px value is authored at 1080p and multiplied by this. 4K → 2. */
export const unit = (height: number) => height / 1080;
