import React from 'react';
import {AbsoluteFill, Img, random, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Background} from '../types';
import {PALETTE} from '../theme';
import {unit} from '../anim';

const GRADIENTS: Record<Background['variant'], string> = {
  light: `radial-gradient(120% 95% at 50% 38%, ${PALETTE.lavender50} 0%, ${PALETTE.lavender100} 38%, ${PALETTE.lavender300} 100%)`,
  dusk: `radial-gradient(110% 100% at 28% 25%, ${PALETTE.lavender200} 0%, ${PALETTE.violet500} 48%, ${PALETTE.violet700} 100%)`,
  dark: `radial-gradient(115% 100% at 50% 35%, ${PALETTE.violet700} 0%, ${PALETTE.violet900} 52%, ${PALETTE.ink} 100%)`,
};

/** Animated grid: thin lines + intersection dots, drifting slowly (the reference's "subtle grid texture"). */
const Grid: React.FC<{dark: boolean; u: number}> = ({dark, u}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const step = 96 * u;
  const off = ((frame / fps) * 6 * u) % step;
  const line = dark ? 'rgba(233,224,255,0.07)' : 'rgba(75,45,143,0.09)';
  const dot = dark ? 'rgba(233,224,255,0.22)' : 'rgba(75,45,143,0.22)';
  return (
    <AbsoluteFill
      style={{
        backgroundImage: [
          `radial-gradient(circle, ${dot} ${1.6 * u}px, transparent ${1.8 * u}px)`,
          `linear-gradient(${line} ${u}px, transparent ${u}px)`,
          `linear-gradient(90deg, ${line} ${u}px, transparent ${u}px)`,
        ].join(','),
        backgroundSize: `${step}px ${step}px`,
        backgroundPosition: `${-step / 2 + off}px ${-step / 2 + off * 0.5}px, ${off}px ${off * 0.5}px, ${off}px ${off * 0.5}px`,
      }}
    />
  );
};

/** Soft bokeh orbs — cheap radial gradients (no CSS blur filter) so long renders stay fast. */
const Orbs: React.FC<{dark: boolean; u: number; seed: string}> = ({dark, u, seed}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const t = frame / fps;
  return (
    <AbsoluteFill>
      {new Array(7).fill(0).map((_, i) => {
        const r = (140 + random(`${seed}-r${i}`) * 260) * u;
        const x = random(`${seed}-x${i}`) * width + Math.sin(t * 0.15 + i) * 40 * u;
        const y = random(`${seed}-y${i}`) * height + Math.cos(t * 0.12 + i * 2) * 30 * u;
        const c = dark ? `rgba(187,164,242,${0.10 + random(`${seed}-a${i}`) * 0.10})` : `rgba(255,255,255,${0.35 + random(`${seed}-a${i}`) * 0.3})`;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x - r,
              top: y - r,
              width: r * 2,
              height: r * 2,
              borderRadius: '50%',
              background: `radial-gradient(circle, ${c} 0%, transparent 70%)`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

export const LuxeBackground: React.FC<{bg?: Background; seed: string}> = ({bg, seed}) => {
  const frame = useCurrentFrame();
  const {height} = useVideoConfig();
  const u = unit(height);
  const variant = bg?.variant ?? 'light';
  const dark = variant !== 'light';
  return (
    <AbsoluteFill style={{background: GRADIENTS[variant]}}>
      {bg?.image ? <Img src={staticFile(bg.image)} style={{width: '100%', height: '100%', objectFit: 'cover', opacity: 0.55}} /> : null}
      {bg?.orbs !== false ? <Orbs dark={dark} u={u} seed={seed} /> : null}
      {bg?.grid !== false ? <Grid dark={dark} u={u} /> : null}
      {bg?.grain !== false ? (
        <AbsoluteFill
          style={{
            backgroundImage: `url(${staticFile('lib/backgrounds/film-grain-tile-1024.png')})`,
            backgroundSize: `${512 * u}px ${512 * u}px`,
            backgroundPosition: `${(frame * 37) % 512}px ${(frame * 53) % 512}px`,
            opacity: dark ? 0.16 : 0.1, // plain alpha: blend modes force slow full-frame compositing on CPU
          }}
        />
      ) : null}
      <AbsoluteFill style={{background: `radial-gradient(130% 120% at 50% 45%, transparent 50%, ${dark ? 'rgba(10,4,24,0.6)' : 'rgba(75,45,143,0.22)'} 100%)`}} />
    </AbsoluteFill>
  );
};
