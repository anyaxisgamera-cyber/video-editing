import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useDelayRender, useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
import {loadFont} from '@remotion/fonts';
import {unit} from './anim';

/**
 * Live-action "Cinematic" composition: graded footage shots with measured camera moves and real-edit transitions
 * (cut, dissolve, dip to black/white, flash), Telugu subtitles and text cards, optional letterbox / vignette / grain.
 * No motion-graphics decoration: everything on screen is footage or typography that the reference itself uses.
 * The timeline is written by telugu-cinematic-edit/scripts/recreate.py (all times in frames).
 */

export type CineTransition = {type: 'cut' | 'dissolve' | 'dip_to_black' | 'dip_to_white' | 'flash'; durationInFrames: number};
export type CineMove = {
  type: 'static' | 'push_in' | 'pull_out' | 'pan_left' | 'pan_right' | 'tilt_up' | 'tilt_down';
  amount: number; // zoom fraction (0.08 = 8 %) or travel as a fraction of the frame
  ease?: 'linear' | 'inOut';
};
export type CineShot = {
  id: string;
  from: number;
  durationInFrames: number;
  src: string; // staticFile path of the graded clip
  trimBefore: number; // frames into the clip
  playbackRate?: number;
  move: CineMove;
  transitionIn?: CineTransition; // overlap with the previous shot
  refShot?: number; // reference shot this one recreates (informational)
};
export type CineCaption = {from: number; durationInFrames: number; lines: string; kind?: string};
export type CineCard = {
  from: number;
  durationInFrames: number;
  text: string;
  sub?: string;
  style: 'verse' | 'title' | 'reference';
  position: 'centre' | 'lower-third' | 'top' | 'bottom';
  entrance: 'fade' | 'blur' | 'cut';
  fadeFrames: number;
};
export type CineTimeline = {
  meta: {
    title: string; width: number; height: number; fps: number; durationInFrames: number; composition: 'Cinematic';
    letterbox?: number | null; // target aspect ratio, e.g. 2.39 (bars top/bottom)
    vignette?: number; // 0..1
    grain?: number; // 0..1
    captionStyle?: {size?: number; bottom?: number; font?: 'sans' | 'serif'; fade?: number};
  };
  shots: CineShot[];
  captions: CineCaption[];
  cards: CineCard[];
  audio?: unknown;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const SANS = 'Noto Sans Telugu';
const SERIF = 'Noto Serif Telugu';

let teluguFonts: Promise<unknown> | null = null;
const ensureTeluguFonts = () => {
  if (!teluguFonts) {
    teluguFonts = Promise.all([
      loadFont({family: SANS, url: staticFile('lib/fonts/NotoSansTelugu-Regular.ttf'), weight: '400'}),
      loadFont({family: SANS, url: staticFile('lib/fonts/NotoSansTelugu-Bold.ttf'), weight: '700'}),
      loadFont({family: SERIF, url: staticFile('lib/fonts/NotoSerifTelugu-Regular.ttf'), weight: '400'}),
      loadFont({family: SERIF, url: staticFile('lib/fonts/NotoSerifTelugu-Bold.ttf'), weight: '700'}),
    ]);
  }
  return teluguFonts;
};

/** Camera move as a transform of the footage layer, progress across the whole shot (continues through overlaps). */
const moveStyle = (m: CineMove, p: number): React.CSSProperties => {
  const e = m.ease === 'linear' ? p : Easing.inOut(Easing.sin)(p);
  const a = m.amount;
  switch (m.type) {
    case 'push_in':
      return {transform: `scale(${1 + a * e})`};
    case 'pull_out':
      return {transform: `scale(${1 + a * (1 - e)})`};
    case 'pan_right': // camera pans right → content moves left
      return {transform: `scale(${1 + a}) translateX(${(a / 2 - a * e) * 100 / (1 + a)}%)`};
    case 'pan_left':
      return {transform: `scale(${1 + a}) translateX(${(-a / 2 + a * e) * 100 / (1 + a)}%)`};
    case 'tilt_up': // camera tilts up → content moves down
      return {transform: `scale(${1 + a}) translateY(${(-a / 2 + a * e) * 100 / (1 + a)}%)`};
    case 'tilt_down':
      return {transform: `scale(${1 + a}) translateY(${(a / 2 - a * e) * 100 / (1 + a)}%)`};
    default:
      return {};
  }
};

const overlayColor = (t?: CineTransition) => (t?.type === 'dip_to_white' || t?.type === 'flash' ? '#FFFFFF' : '#000000');

/**
 * One shot. Transition semantics (shots overlap by the transition length; later shots are drawn on top):
 *  dissolve       incoming opacity 0→1 over the overlap; outgoing stays opaque underneath
 *  dip_to_black/white  outgoing fades to the colour over the first half, incoming is hidden until the midpoint
 *                 and fades from the colour over the second half
 *  flash          a white bloom (sin curve) peaks at the midpoint, where the picture switches
 */
const Shot: React.FC<{shot: CineShot; next?: CineShot}> = ({shot, next}) => {
  const f = useCurrentFrame();
  const D = shot.durationInFrames;
  const tin = shot.transitionIn && shot.transitionIn.type !== 'cut' ? shot.transitionIn : undefined;
  const tout = next?.transitionIn && next.transitionIn.type !== 'cut' ? next.transitionIn : undefined;
  let opacity = 1;
  let overlay = 0;
  let overlayCol = '#000000';
  if (tin && f < tin.durationInFrames) {
    const p = interpolate(f, [0, tin.durationInFrames], [0, 1], clamp);
    if (tin.type === 'dissolve') opacity = p;
    else if (tin.type === 'flash') {
      opacity = p >= 0.5 ? 1 : 0;
      overlay = p >= 0.5 ? Math.sin(Math.PI * p) : 0;
    } else {
      opacity = p >= 0.5 ? 1 : 0;
      overlay = p < 0.5 ? 1 : 1 - (p - 0.5) * 2;
    }
    overlayCol = overlayColor(tin);
  }
  if (tout && f >= D - tout.durationInFrames) {
    const q = interpolate(f, [D - tout.durationInFrames, D], [0, 1], clamp);
    if (tout.type === 'flash') overlay = Math.max(overlay, q < 0.5 ? Math.sin(Math.PI * q) : 0);
    else if (tout.type !== 'dissolve') overlay = Math.max(overlay, Math.min(1, q * 2));
    overlayCol = overlayColor(tout);
  }
  const ms = moveStyle(shot.move, D > 1 ? f / (D - 1) : 0);
  return (
    <AbsoluteFill style={{opacity}}>
      <AbsoluteFill style={{...ms, transformOrigin: '50% 50%'}}>
        <Video src={staticFile(shot.src)} muted objectFit="cover" trimBefore={shot.trimBefore}
          playbackRate={shot.playbackRate ?? 1} style={{width: '100%', height: '100%'}} />
      </AbsoluteFill>
      {overlay > 0.001 ? <AbsoluteFill style={{backgroundColor: overlayCol, opacity: overlay}} /> : null}
    </AbsoluteFill>
  );
};

const Shots: React.FC<{shots: CineShot[]}> = ({shots}) => {
  const frame = useCurrentFrame();
  const out: React.ReactNode[] = [];
  for (let i = 0; i < shots.length; i++) {
    const s = shots[i];
    if (frame < s.from || frame >= s.from + s.durationInFrames) continue;
    out.push(
      <Sequence key={s.id} name={`${s.id}${s.refShot ? ` ← ref #${s.refShot}` : ''}`} from={s.from}
        durationInFrames={s.durationInFrames} layout="absolute-fill" premountFor={0}>
        <Shot shot={s} next={shots[i + 1]} />
      </Sequence>,
    );
  }
  return <>{out}</>;
};

const fadeOpacity = (f: number, dur: number, k: number) =>
  Math.min(interpolate(f, [0, k], [0, 1], clamp), interpolate(f, [dur - k, dur], [1, 0], clamp));

const Captions: React.FC<{caps: CineCaption[]; style?: CineTimeline['meta']['captionStyle']; barPx: number}> = ({caps, style, barPx}) => {
  const frame = useCurrentFrame();
  const {height} = useVideoConfig();
  const u = unit(height);
  const c = caps.find((x) => frame >= x.from && frame < x.from + x.durationInFrames);
  if (!c) return null;
  const f = frame - c.from;
  const size = (style?.size ?? 50) * u;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: Math.max(barPx + 24 * u, (style?.bottom ?? 78) * u)}}>
      <div style={{
        fontFamily: style?.font === 'serif' ? SERIF : SANS, fontSize: size, lineHeight: 1.5, color: '#FFFFFF', textAlign: 'center',
        whiteSpace: 'pre-line', maxWidth: '82%', opacity: fadeOpacity(f, c.durationInFrames, Math.max(1, style?.fade ?? 4)),
        textShadow: `0 ${2 * u}px ${4 * u}px rgba(0,0,0,0.85), 0 0 ${14 * u}px rgba(0,0,0,0.55)`,
      }}>
        {c.lines}
      </div>
    </AbsoluteFill>
  );
};

const Card: React.FC<{card: CineCard}> = ({card}) => {
  const f = useCurrentFrame();
  const {height} = useVideoConfig();
  const u = unit(height);
  const k = card.entrance === 'cut' ? 1 : Math.max(1, card.fadeFrames);
  const o = fadeOpacity(f, card.durationInFrames, k);
  const blur = card.entrance === 'blur' ? interpolate(f, [0, k], [10, 0], clamp) * u : 0;
  const isTitle = card.style === 'title';
  const just = card.position === 'top' ? 'flex-start' : card.position === 'centre' ? 'center' : 'flex-end';
  const pad = card.position === 'lower-third' ? 230 * u : card.position === 'bottom' ? 140 * u : card.position === 'top' ? 150 * u : 0;
  // soft scrim behind title/verse cards so white type stays legible on bright footage (fades with the card)
  const scrimY = card.position === 'top' ? '12%' : card.position === 'centre' ? '50%' : '82%';
  return (
    <AbsoluteFill style={{justifyContent: just, alignItems: 'center', paddingTop: card.position === 'top' ? pad : 0,
      paddingBottom: card.position === 'top' ? 0 : pad}}>
      {card.style !== 'reference' ? (
        <AbsoluteFill style={{opacity: o, background: `radial-gradient(ellipse 55% 32% at 50% ${scrimY}, rgba(0,0,0,0.5), rgba(0,0,0,0) 100%)`}} />
      ) : null}
      <div style={{opacity: o, filter: blur > 0.05 ? `blur(${blur}px)` : undefined, textAlign: 'center', maxWidth: '78%',
        display: 'flex', flexDirection: 'column', gap: 26 * u, alignItems: 'center'}}>
        <div style={{fontFamily: SERIF, fontWeight: isTitle ? 700 : 400, fontSize: (isTitle ? 104 : 62) * u, lineHeight: 1.45,
          color: '#FFFFFF', letterSpacing: isTitle ? 2 * u : 0,
          textShadow: `0 ${3 * u}px ${18 * u}px rgba(0,0,0,0.6)`}}>
          {card.text}
        </div>
        {card.sub ? (
          <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 36 * u, color: '#FFFFFF', letterSpacing: 1 * u,
            textShadow: `0 ${2 * u}px ${3 * u}px rgba(0,0,0,0.9), 0 0 ${12 * u}px rgba(0,0,0,0.75)`}}>
            {card.sub}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const Cards: React.FC<{cards: CineCard[]}> = ({cards}) => (
  <>
    {cards.map((c, i) => (
      <Sequence key={i} from={c.from} durationInFrames={c.durationInFrames} layout="absolute-fill">
        <Card card={c} />
      </Sequence>
    ))}
  </>
);

/** Static film grain: a pre-rendered noise tile shifted every frame (plain alpha, no blend modes — cheap). */
const Grain: React.FC<{amount: number}> = ({amount}) => {
  const f = useCurrentFrame();
  const x = (f * 73) % 256;
  const y = (f * 151) % 256;
  return (
    <AbsoluteFill style={{opacity: amount, overflow: 'hidden'}}>
      <Img src={staticFile('lib/backgrounds/grain-256.png')} style={{position: 'absolute', left: -x, top: -y,
        width: 'calc(100% + 512px)', height: 'calc(100% + 512px)', objectFit: 'none', imageRendering: 'pixelated'}} />
    </AbsoluteFill>
  );
};

export const Cinematic: React.FC<{timeline: CineTimeline}> = ({timeline}) => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Loading Telugu fonts'));
  useEffect(() => {
    ensureTeluguFonts().then(() => continueRender(handle)).catch((err) => cancelRender(err));
  }, [handle, continueRender, cancelRender]);
  const {width, height} = useVideoConfig();
  const m = timeline.meta;
  const bar = m.letterbox ? Math.max(0, Math.round((height - width / m.letterbox) / 2)) : 0;
  return (
    <AbsoluteFill style={{backgroundColor: '#000000'}}>
      <Shots shots={timeline.shots} />
      {m.vignette ? (
        <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,${0.55 * m.vignette}) 100%)`}} />
      ) : null}
      {m.grain ? <Grain amount={m.grain} /> : null}
      <Cards cards={timeline.cards} />
      {bar > 0 ? (
        <>
          <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: bar, backgroundColor: '#000'}} />
          <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: bar, backgroundColor: '#000'}} />
        </>
      ) : null}
      <Captions caps={timeline.captions} style={m.captionStyle} barPx={bar} />
    </AbsoluteFill>
  );
};
