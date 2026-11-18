export type Cue = {start: number; end: number; text: string; line: number};
export type Step = {text: string; start: number};
export type Scene = {id: string; start: number; end: number; headline: string; image: string};

export type FontSpec = {
  family: string;
  files: {weight: string; style: 'normal' | 'italic'; src: string}[];
  headlineSize: number;
  subtitleSize: number;
  verseSize: number;
  finalSize: number;
  lineHeight: number;
  letterSpacing: number;
};

export type ScriptureProps = {
  canvas: {width: number; height: number; fps: number; durationInFrames: number};
  language: 'en' | 'te';
  font: FontSpec;
  /** Latin serif used for numerals/ornament labels in both languages. */
  accentFont: FontSpec;
  series: string;
  scenes: Scene[];
  cues: Cue[];
  steps: Step[];
  verse: {text: string; reference: string; start: number};
  final: {lines: string[]; reference: string; start: number};
  palette: {
    ink: string;
    lavender: string;
    lilac: string;
    plum: string;
    deep: string;
    glow: string;
  };
};
