import {Easing} from 'remotion';

// ONE file sets the feel. "Make it snappier" = edit these numbers (frames @ 30 fps; scaled by fps/30).
export const TIMING = {
  reveal: 22, // word/element entrance
  stagger: 5, // gap between sibling words/items
  exit: 14, // blur-out duration
  panelIn: 26, // media panel entrance
  panelStagger: 9,
  logoStagger: 4,
  floatIn: 30, // floating object fade/settle
  holdBeforeExit: 10, // frames between text exit end and the scene transition
};

export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);
export const EASE_IN = Easing.bezier(0.7, 0, 0.84, 0);

export const BLUR = {
  textIn: 18, // px at 1080p
  textOut: 14,
  far: 6, // depth 0 floating objects
  near: 9, // depth 2 foreground objects
};

export const PALETTE = {
  lavender50: '#F4EFFF',
  lavender100: '#E9E0FF',
  lavender200: '#D6C7FB',
  lavender300: '#BBA4F2',
  violet500: '#8B6CD9',
  violet700: '#4B2D8F',
  violet900: '#24124A',
  ink: '#140A2A',
  gold: '#E8C98A',
  white: '#FFFFFF',
};

export const FONTS = {
  display: '"Instrument Serif", "EB Garamond", serif',
  displayItalic: '"Instrument Serif Italic", "Instrument Serif", serif',
  heavy: 'Gloock, "Instrument Serif", serif',
  caps: 'Italiana, "Instrument Serif", serif',
  sans: '"Instrument Sans", "Work Sans", sans-serif',
};

// Scene tones: text colours per background variant.
export const TONES = {
  light: {fg: PALETTE.violet900, muted: '#5B4A86', accent: PALETTE.violet500, line: 'rgba(36,18,74,0.18)'},
  dusk: {fg: PALETTE.white, muted: '#EDE4FF', accent: PALETTE.lavender100, line: 'rgba(255,255,255,0.28)'},
  dark: {fg: PALETTE.lavender50, muted: '#C9B8F5', accent: PALETTE.lavender300, line: 'rgba(233,224,255,0.22)'},
};

export type Tone = keyof typeof TONES;

// Frames scale with fps so a 60 fps render keeps the same feel as 30 fps.
export const f = (frames30: number, fps: number) => Math.round((frames30 * fps) / 30);
