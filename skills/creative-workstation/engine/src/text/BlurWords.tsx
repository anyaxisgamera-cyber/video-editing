import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {BLUR, FONTS, TIMING, f} from '../theme';
import {enter, leave, unit} from '../anim';

type Props = {
  text: string; // *word* = italic accent
  start: number; // frame (scene-relative) of the first word
  exitAt?: number; // frame (scene-relative) when the blur-out starts; omit to hold
  size: number; // px at 1080p
  color: string;
  accent?: string;
  font?: string;
  align?: 'left' | 'center' | 'right';
  lineHeight?: number;
  letterSpacing?: number; // em
  maxWidth?: number; // px at 1080p
  stagger?: number;
  mode?: 'words' | 'letters';
  weight?: number;
};

/**
 * Elegant serif typography with per-word (or per-letter) blur-in and blur-out — the core
 * text treatment of the reference style. Each unit rises, sharpens and fades in on a stagger.
 */
export const BlurWords: React.FC<Props> = ({
  text, start, exitAt, size, color, accent, font = FONTS.display, align = 'left', lineHeight = 1.02,
  letterSpacing = -0.01, maxWidth, stagger, mode = 'words', weight = 400,
}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const u = unit(height);
  const st = stagger ?? f(mode === 'letters' ? 2 : TIMING.stagger, fps);
  const tokens = mode === 'letters' ? Array.from(text.replace(/\*/g, '')) : text.split(/(\s+)/);
  let idx = 0;
  let italic = false;
  return (
    <div
      style={{
        fontFamily: font,
        fontSize: size * u,
        color,
        lineHeight,
        letterSpacing: `${letterSpacing}em`,
        textAlign: align,
        maxWidth: maxWidth ? maxWidth * u : undefined,
        fontWeight: weight,
      }}
    >
      {tokens.map((tok, k) => {
        if (/^\s+$/.test(tok)) return <span key={k}>{tok}</span>;
        let word = tok;
        let isAccent = italic;
        if (mode === 'words') {
          if (word.startsWith('*')) {
            italic = true;
            isAccent = true;
            word = word.slice(1);
          }
          if (word.endsWith('*')) {
            italic = false;
            word = word.slice(0, -1);
          }
        }
        const i = idx++;
        const p = enter(frame, start + i * st, f(TIMING.reveal, fps));
        const q = exitAt === undefined ? 0 : leave(frame, exitAt + i * Math.max(1, Math.round(st / 2)), f(TIMING.exit, fps));
        const blur = (1 - p) * BLUR.textIn + q * BLUR.textOut;
        return (
          <span
            key={k}
            style={{
              display: 'inline-block',
              whiteSpace: 'pre',
              opacity: p * (1 - q),
              filter: blur > 0.05 ? `blur(${blur * u}px)` : undefined,
              translate: `0 ${((1 - p) * 26 - q * 14) * u}px`,
              fontFamily: isAccent ? FONTS.displayItalic : undefined,
              color: isAccent && accent ? accent : undefined,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Small letter-spaced caps line (kicker / eyebrow), with a hairline rule that draws in. */
export const Kicker: React.FC<{text: string; start: number; exitAt?: number; color: string; align?: 'left' | 'center'}> = ({
  text, start, exitAt, color, align = 'left',
}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const u = unit(height);
  const p = enter(frame, start, f(TIMING.reveal + 8, fps));
  const q = exitAt === undefined ? 0 : leave(frame, exitAt, f(TIMING.exit, fps));
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 18 * u, justifyContent: align === 'center' ? 'center' : 'flex-start', opacity: 1 - q}}>
      <div style={{width: 64 * u * p, height: Math.max(1, 1.5 * u), background: color, opacity: 0.7}} />
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: 17 * u,
          letterSpacing: `${0.32 + (1 - p) * 0.25}em`,
          textTransform: 'uppercase',
          color,
          opacity: p,
          filter: p < 0.99 ? `blur(${(1 - p) * 8 * u}px)` : undefined,
        }}
      >
        {text}
      </div>
      {align === 'center' ? <div style={{width: 64 * u * p, height: Math.max(1, 1.5 * u), background: color, opacity: 0.7}} /> : null}
    </div>
  );
};
