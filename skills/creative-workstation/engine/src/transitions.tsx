import React from 'react';
import {AbsoluteFill, interpolate, useVideoConfig} from 'remotion';
import type {TransitionPresentation, TransitionPresentationComponentProps} from '@remotion/transitions';
import {slide} from '@remotion/transitions/slide';
import type {TransitionType} from './types';
import {unit} from './anim';

type Empty = Record<string, unknown>;

/**
 * Symmetric blur crossfade: the outgoing scene stays opaque underneath and blurs/grows, the incoming scene
 * fades in linearly on top while it sharpens. Composite = p·in + (1−p)·out, so the visual midpoint (and the
 * whoosh peak) sits exactly on the boundary. (An earlier version faded the top layer in over 65 % of the
 * transition, which put the perceived cut ~3 frames early — caught by tests/sync_check.py.)
 */
const BlurDissolve: React.FC<TransitionPresentationComponentProps<Empty>> = ({children, presentationDirection, presentationProgress: p}) => {
  const u = unit(useVideoConfig().height);
  const out = presentationDirection === 'exiting';
  const k = out ? p : 1 - p; // 0 = fully this scene, 1 = fully the other
  const blur = interpolate(k, [0, 1], [0, 22]) * u;
  return (
    <AbsoluteFill style={{opacity: out ? 1 : p, filter: blur > 0.1 ? `blur(${blur}px)` : undefined,
      scale: String(out ? 1 + p * 0.05 : 0.96 + p * 0.04)}}>
      {children}
    </AbsoluteFill>
  );
};

const ZoomBlur: React.FC<TransitionPresentationComponentProps<Empty>> = ({children, presentationDirection, presentationProgress: p}) => {
  const u = unit(useVideoConfig().height);
  const out = presentationDirection === 'exiting';
  return (
    <AbsoluteFill style={{opacity: out ? 1 : p,
      scale: String(out ? 1 + p * 0.35 : 0.8 + p * 0.2), filter: `blur(${(out ? p : 1 - p) * 26 * u}px)`}}>
      {children}
    </AbsoluteFill>
  );
};

/** Diagonal soft-edged wipe (mask gradient), entering scene revealed over the exiting one. */
const SoftWipe: React.FC<TransitionPresentationComponentProps<Empty>> = ({children, presentationDirection, presentationProgress: p}) => {
  if (presentationDirection === 'exiting' || p >= 0.999) return <AbsoluteFill>{children}</AbsoluteFill>;
  const edge = -30 + p * 160;
  const mask = `linear-gradient(115deg, black ${edge - 18}%, transparent ${edge}%)`;
  return <AbsoluteFill style={{maskImage: mask, WebkitMaskImage: mask}}>{children}</AbsoluteFill>;
};

const Iris: React.FC<TransitionPresentationComponentProps<Empty>> = ({children, presentationDirection, presentationProgress: p}) => {
  // fully open (no mask) once complete — a 75% radius would leave the corners masked for the rest of the scene
  if (presentationDirection === 'exiting' || p >= 0.999) return <AbsoluteFill>{children}</AbsoluteFill>;
  const r = p * 112;
  const mask = `radial-gradient(circle at 50% 50%, black ${r}%, transparent ${r + 6}%)`;
  return <AbsoluteFill style={{maskImage: mask, WebkitMaskImage: mask}}>{children}</AbsoluteFill>;
};

/** Lavender light flash: both scenes cross at the peak of a soft white-violet bloom. */
const Flash: React.FC<TransitionPresentationComponentProps<Empty>> = ({children, presentationDirection, presentationProgress: p}) => {
  const out = presentationDirection === 'exiting';
  const flash = Math.sin(p * Math.PI);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{opacity: out ? (p < 0.5 ? 1 : 0) : p >= 0.5 ? 1 : 0}}>{children}</AbsoluteFill>
      {out ? null : <AbsoluteFill style={{background: 'radial-gradient(circle at 50% 45%, #FFFFFF, #D6C7FB 60%, #8B6CD9)', opacity: flash * 0.92}} />}
    </AbsoluteFill>
  );
};

const custom = (component: React.FC<TransitionPresentationComponentProps<Empty>>): TransitionPresentation<Empty> => ({component, props: {}});
const asAny = (p: unknown) => p as TransitionPresentation<Empty>;

export const presentationFor = (type: TransitionType): TransitionPresentation<Empty> => {
  switch (type) {
    case 'zoomBlur':
      return custom(ZoomBlur);
    case 'slideLeft':
      return asAny(slide({direction: 'from-right'}));
    case 'slideUp':
      return asAny(slide({direction: 'from-bottom'}));
    case 'softWipe':
      return custom(SoftWipe);
    case 'iris':
      return custom(Iris);
    case 'flash':
      return custom(Flash);
    case 'blurDissolve':
    default:
      return custom(BlurDissolve);
  }
};
