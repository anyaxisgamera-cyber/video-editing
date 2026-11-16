import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
import type {SceneBase, SpriteSource} from '../types';
import {FONTS, PALETTE, TIMING, TONES, type Tone, f} from '../theme';
import {enter, leave, unit} from '../anim';
import {BlurWords, Kicker} from '../text/BlurWords';
import {Sprite} from '../layers/Sprite';

export type SceneProps = {scene: SceneBase};

const toneOf = (s: SceneBase): Tone => (s.background?.variant ?? 'light') as Tone;
const P = <T,>(s: SceneBase, k: string, d: T): T => (s.props[k] as T) ?? d;

/** Frame at which text should start blurring out so it's gone before the outgoing transition. */
const exitFrame = (s: SceneBase, fps: number) => {
  if (s.props.exitText === false) return undefined;
  const out = s.transition?.durationInFrames ?? 0;
  return Math.max(f(30, fps), s.durationInFrames - out - f(TIMING.exit + TIMING.holdBeforeExit, fps));
};

const useU = () => unit(useVideoConfig().height);

// ---------------------------------------------------------------- 1. Title reveal

export const TitleReveal: React.FC<SceneProps> = ({scene}) => {
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const align = P<'center' | 'left'>(scene, 'align', 'center');
  const sub = P<string>(scene, 'subtitle', '');
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: align === 'center' ? 'center' : 'flex-start', padding: `0 ${160 * u}px`}}>
      <div style={{display: 'flex', flexDirection: 'column', gap: 34 * u, alignItems: align === 'center' ? 'center' : 'flex-start'}}>
        {P(scene, 'kicker', '') ? <Kicker text={P(scene, 'kicker', '')} start={f(4, fps)} exitAt={ex} color={tone.muted} align={align} /> : null}
        <BlurWords text={P(scene, 'title', '')} start={f(12, fps)} exitAt={ex} size={P(scene, 'titleSize', 150)} color={tone.fg}
          accent={tone.accent} align={align} maxWidth={P(scene, 'maxWidth', 1500)} mode={P(scene, 'mode', 'words')} />
        {sub ? <BlurWords text={sub} start={f(34, fps)} exitAt={ex} size={34} color={tone.muted} font={FONTS.sans} align={align}
          letterSpacing={0.01} lineHeight={1.4} maxWidth={1100} /> : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 2. Chess hero (3D turntable + copy)

export const ChessHero: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const side = P<'left' | 'right'>(scene, 'side', 'right');
  const piece = P<SpriteSource>(scene, 'piece', {kind: 'image', src: ''});
  const size = P<number>(scene, 'pieceSize', 820);
  const p = enter(frame, 0, f(40, fps));
  const q = ex === undefined ? 0 : leave(frame, ex, f(TIMING.exit + 6, fps));
  const pieceBlock = (
    <div style={{position: 'relative', width: size * 0.75 * u, height: size * u, opacity: p * (1 - q),
      translate: `0 ${(1 - p) * 60 * u + Math.sin(frame / fps * 1.2) * 10 * u}px`, scale: String(0.94 + 0.06 * p),
      filter: q > 0.01 ? `blur(${q * 16 * u}px)` : undefined}}>
      {/* contact shadow under the base (turntable frames leave ~16% empty space below the piece) */}
      <div style={{position: 'absolute', left: '14%', right: '14%', bottom: '14%', height: 56 * u, borderRadius: '50%',
        background: 'radial-gradient(closest-side, rgba(20,10,42,0.42), transparent)'}} />
      <Sprite src={piece} height={size * u} />
    </div>
  );
  const copy = (
    <div style={{display: 'flex', flexDirection: 'column', gap: 30 * u, maxWidth: 820 * u}}>
      <Kicker text={P(scene, 'kicker', '')} start={f(10, fps)} exitAt={ex} color={tone.muted} />
      <BlurWords text={P(scene, 'title', '')} start={f(18, fps)} exitAt={ex} size={P(scene, 'titleSize', 112)} color={tone.fg} accent={tone.accent} />
      {P(scene, 'body', '') ? <BlurWords text={P(scene, 'body', '')} start={f(40, fps)} exitAt={ex} size={30} color={tone.muted}
        font={FONTS.sans} lineHeight={1.45} letterSpacing={0} stagger={2} /> : null}
    </div>
  );
  return (
    <AbsoluteFill style={{flexDirection: side === 'right' ? 'row' : 'row-reverse', alignItems: 'center', justifyContent: 'space-between',
      padding: `0 ${150 * u}px`, height}}>
      {copy}
      {pieceBlock}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 3. Media panels (cinematic footage in rectangles)

type PanelSrc = {kind: 'video'; src: string; trimBefore?: number} | {kind: 'image'; src: string} |
  {kind: 'sequence'; dir: string; frames: number; fps?: number};

const PanelMedia: React.FC<{m: PanelSrc}> = ({m}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};
  if (m.kind === 'video') {
    return <Video src={staticFile(m.src)} muted objectFit="cover" trimBefore={Math.round((m.trimBefore ?? 0) * fps)} style={{width: '100%', height: '100%'}} />;
  }
  if (m.kind === 'image') return <Img src={staticFile(m.src)} style={cover} />;
  const idx = Math.min(m.frames - 1, Math.floor((frame / fps) * (m.fps ?? 30)));
  return <Img src={staticFile(`${m.dir}/f_${String(idx).padStart(4, '0')}.png`)} style={cover} />;
};

const LAYOUTS: Record<string, Array<{x: number; y: number; w: number; h: number}>> = {
  // % of frame. Overlapping, offset rectangles = the reference's layered panel compositions.
  hero: [{x: 50, y: 52, w: 64, h: 66}],
  duo: [{x: 33, y: 50, w: 42, h: 58}, {x: 68, y: 56, w: 36, h: 50}],
  trio: [{x: 24, y: 54, w: 30, h: 48}, {x: 51, y: 46, w: 32, h: 56}, {x: 78, y: 58, w: 26, h: 42}],
};

export const MediaPanels: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const panels = P<Array<PanelSrc & {caption?: string}>>(scene, 'panels', []);
  const layout = LAYOUTS[P<string>(scene, 'layout', panels.length >= 3 ? 'trio' : panels.length === 2 ? 'duo' : 'hero')];
  const title = P<string>(scene, 'title', '');
  return (
    <AbsoluteFill>
      {panels.slice(0, layout.length).map((pn, i) => {
        const L = layout[i];
        const st = f(6 + i * TIMING.panelStagger, fps);
        const p = enter(frame, st, f(TIMING.panelIn, fps));
        const q = ex === undefined ? 0 : leave(frame, ex + i * 3, f(TIMING.exit + 4, fps));
        const drift = (frame / fps) * (i % 2 ? -6 : 6) * u;
        return (
          <div key={i} style={{position: 'absolute', left: (L.x / 100) * width, top: (L.y / 100) * height,
            width: (L.w / 100) * width, height: (L.h / 100) * height, translate: `-50% -50%`,
            opacity: p * (1 - q), scale: String(0.9 + 0.1 * p + q * 0.04),
            filter: (1 - p) + q > 0.01 ? `blur(${((1 - p) * 14 + q * 12) * u}px)` : undefined,
            rotate: `${(1 - p) * (i % 2 ? 2 : -2)}deg`}}>
            <div style={{position: 'absolute', inset: 0, borderRadius: 22 * u, overflow: 'hidden',
              boxShadow: `0 ${18 * u}px ${36 * u}px rgba(20,10,42,0.38)`, border: `${1.5 * u}px solid ${tone.line}`,
              translate: `${drift}px 0`}}>
              <div style={{position: 'absolute', inset: `-4%`, scale: String(1.06 + 0.04 * (frame / (fps * 10)))}}>
                <PanelMedia m={pn} />
              </div>
              <AbsoluteFill style={{background: 'linear-gradient(160deg, rgba(187,164,242,0.10), rgba(36,18,74,0.22))'}} />
              {pn.caption ? (
                <div style={{position: 'absolute', left: 26 * u, bottom: 22 * u, fontFamily: FONTS.sans, fontSize: 18 * u,
                  letterSpacing: '0.22em', textTransform: 'uppercase', color: PALETTE.white, opacity: enter(frame, st + f(18, fps), f(16, fps)),
                  textShadow: '0 2px 12px rgba(0,0,0,0.5)'}}>{pn.caption}</div>
              ) : null}
            </div>
          </div>
        );
      })}
      {title ? (
        <AbsoluteFill style={{justifyContent: 'flex-start', padding: `${80 * u}px ${150 * u}px`}}>
          <div style={{display: 'flex', flexDirection: 'column', gap: 18 * u}}>
            {P(scene, 'kicker', '') ? <Kicker text={P(scene, 'kicker', '')} start={f(2, fps)} exitAt={ex} color={tone.muted} /> : null}
            <BlurWords text={title} start={f(8, fps)} exitAt={ex} size={P(scene, 'titleSize', 74)} color={tone.fg} accent={tone.accent} />
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 4. Logo wall

export const LogoWall: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const logos = P<string[]>(scene, 'logos', []);
  const cols = P<number>(scene, 'columns', Math.min(4, logos.length));
  const logoH = P<number>(scene, 'logoHeight', 74);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', gap: 70 * u, flexDirection: 'column'}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24 * u}}>
        <Kicker text={P(scene, 'kicker', '')} start={f(2, fps)} exitAt={ex} color={tone.muted} align="center" />
        <BlurWords text={P(scene, 'title', '')} start={f(8, fps)} exitAt={ex} size={P(scene, 'titleSize', 84)} color={tone.fg} accent={tone.accent} align="center" />
      </div>
      <div style={{display: 'grid', gridTemplateColumns: `repeat(${cols}, ${340 * u}px)`, rowGap: 56 * u, columnGap: 40 * u, justifyItems: 'center', alignItems: 'center'}}>
        {logos.map((src, i) => {
          const p = enter(frame, f(26 + i * TIMING.logoStagger, fps), f(TIMING.reveal, fps));
          const q = ex === undefined ? 0 : leave(frame, ex + i, f(TIMING.exit, fps));
          return (
            <Img key={i} src={staticFile(src)} style={{height: logoH * u, maxWidth: 320 * u, objectFit: 'contain', opacity: p * (1 - q) * 0.92,
              filter: (1 - p) + q > 0.01 ? `blur(${((1 - p) * 12 + q * 10) * u}px)` : undefined, scale: String(0.86 + 0.14 * p)}} />
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 5. Silhouette

export const Silhouette: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const side = P<'left' | 'right'>(scene, 'side', 'left');
  const p = enter(frame, 0, f(45, fps));
  const slide = interpolate(frame, [0, scene.durationInFrames], [-30, 30]) * u * (side === 'left' ? 1 : -1);
  return (
    <AbsoluteFill style={{flexDirection: side === 'left' ? 'row' : 'row-reverse', alignItems: 'flex-end', justifyContent: 'space-between', padding: `0 ${150 * u}px`}}>
      <div style={{position: 'relative', height: '92%', display: 'flex', alignItems: 'flex-end', translate: `${slide}px 0`, opacity: p}}>
        <div style={{position: 'absolute', inset: '10% -20% -10% -20%', background: `radial-gradient(closest-side, ${tone.accent}, transparent)`, opacity: 0.55}} />
        <Img src={staticFile(P(scene, 'silhouette', ''))} style={{position: 'relative', height: '100%', width: 'auto',
          filter: `blur(${(1 - p) * 20 * u}px) drop-shadow(0 0 ${40 * u}px rgba(187,164,242,0.45))`}} />
      </div>
      <div style={{alignSelf: 'center', display: 'flex', flexDirection: 'column', gap: 28 * u, maxWidth: 820 * u}}>
        <Kicker text={P(scene, 'kicker', '')} start={f(16, fps)} exitAt={ex} color={tone.muted} />
        <BlurWords text={P(scene, 'title', '')} start={f(24, fps)} exitAt={ex} size={P(scene, 'titleSize', 104)} color={tone.fg} accent={tone.accent} />
        {P(scene, 'body', '') ? <BlurWords text={P(scene, 'body', '')} start={f(46, fps)} exitAt={ex} size={28} color={tone.muted} font={FONTS.sans} lineHeight={1.5} letterSpacing={0} stagger={2} /> : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 6. Statement / quote

export const Statement: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const text = P<string>(scene, 'text', '');
  const words = text.split(/\s+/).length;
  const lineP = enter(frame, f(14 + words * TIMING.stagger, fps), f(28, fps));
  const q = ex === undefined ? 0 : leave(frame, ex, f(TIMING.exit, fps));
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: `0 ${200 * u}px`, flexDirection: 'column', gap: 44 * u}}>
      <div style={{fontFamily: FONTS.heavy, fontSize: 160 * u, color: tone.accent, lineHeight: 0.6, opacity: enter(frame, 0, f(20, fps)) * (1 - q)}}>“</div>
      <BlurWords text={text} start={f(10, fps)} exitAt={ex} size={P(scene, 'size', 88)} color={tone.fg} accent={tone.accent} align="center" lineHeight={1.12} maxWidth={1500} />
      <div style={{width: 220 * u * lineP, height: 2 * u, background: tone.accent, opacity: 1 - q}} />
      {P(scene, 'attribution', '') ? <Kicker text={P(scene, 'attribution', '')} start={f(30 + words * 3, fps)} exitAt={ex} color={tone.muted} align="center" /> : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 7. Stats (counting numbers)

export const Stats: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const items = P<Array<{value: number; prefix?: string; suffix?: string; label: string; decimals?: number}>>(scene, 'items', []);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 80 * u}}>
      {P(scene, 'title', '') ? <BlurWords text={P(scene, 'title', '')} start={f(4, fps)} exitAt={ex} size={70} color={tone.fg} accent={tone.accent} align="center" /> : null}
      <div style={{display: 'flex', gap: 110 * u}}>
        {items.map((it, i) => {
          const st = f(16 + i * 8, fps);
          const p = enter(frame, st, f(50, fps));
          const q = ex === undefined ? 0 : leave(frame, ex + i * 2, f(TIMING.exit, fps));
          const v = (it.value * p).toFixed(it.decimals ?? 0);
          return (
            <div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 * u, opacity: Math.min(1, p * 3) * (1 - q),
              filter: (1 - p) * 0.5 + q > 0.01 ? `blur(${((1 - Math.min(1, p * 2)) * 10 + q * 12) * u}px)` : undefined}}>
              <div style={{fontFamily: FONTS.display, fontSize: 150 * u, color: tone.fg, lineHeight: 1, fontVariantNumeric: 'tabular-nums'}}>
                {it.prefix ?? ''}{v}{it.suffix ?? ''}
              </div>
              <div style={{fontFamily: FONTS.sans, fontSize: 18 * u, letterSpacing: '0.28em', textTransform: 'uppercase', color: tone.muted}}>{it.label}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 8. Icon features

export const IconFeatures: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const ex = exitFrame(scene, fps);
  const items = P<Array<{icon: string; label: string; text?: string}>>(scene, 'items', []);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 70 * u}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22 * u}}>
        <Kicker text={P(scene, 'kicker', '')} start={f(2, fps)} exitAt={ex} color={tone.muted} align="center" />
        <BlurWords text={P(scene, 'title', '')} start={f(8, fps)} exitAt={ex} size={80} color={tone.fg} accent={tone.accent} align="center" />
      </div>
      <div style={{display: 'flex', gap: 34 * u}}>
        {items.map((it, i) => {
          const p = enter(frame, f(24 + i * 7, fps), f(TIMING.reveal + 6, fps));
          const q = ex === undefined ? 0 : leave(frame, ex + i * 2, f(TIMING.exit, fps));
          return (
            <div key={i} style={{width: 330 * u, padding: `${40 * u}px ${30 * u}px`, borderRadius: 26 * u, background: 'rgba(36,18,74,0.55)',
              border: `${1.5 * u}px solid rgba(233,224,255,0.18)`, display: 'flex', flexDirection: 'column', gap: 18 * u, alignItems: 'flex-start',
              opacity: p * (1 - q), translate: `0 ${(1 - p) * 50 * u}px`, filter: (1 - p) + q > 0.01 ? `blur(${((1 - p) * 12 + q * 10) * u}px)` : undefined}}>
              <div style={{width: 74 * u, height: 74 * u, borderRadius: 20 * u, background: `linear-gradient(140deg, ${PALETTE.violet500}, ${PALETTE.violet700})`,
                display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                <Img src={staticFile(it.icon)} style={{width: 40 * u, height: 40 * u}} />
              </div>
              <div style={{fontFamily: FONTS.display, fontSize: 40 * u, color: PALETTE.lavender50, lineHeight: 1.05}}>{it.label}</div>
              {it.text ? <div style={{fontFamily: FONTS.sans, fontSize: 20 * u, color: '#C9B8F5', lineHeight: 1.45}}>{it.text}</div> : null}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 9. End card

export const EndCard: React.FC<SceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const u = useU();
  const tone = TONES[toneOf(scene)];
  const p = enter(frame, f(4, fps), f(40, fps));
  const fadeOut = interpolate(frame, [scene.durationInFrames - f(24, fps), scene.durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 46 * u, opacity: fadeOut}}>
      <Img src={staticFile(P(scene, 'logo', ''))} style={{height: P(scene, 'logoHeight', 170) * u, opacity: p, scale: String(0.92 + 0.08 * p),
        filter: p < 0.99 ? `blur(${(1 - p) * 22 * u}px)` : undefined}} />
      {P(scene, 'tagline', '') ? <BlurWords text={P(scene, 'tagline', '')} start={f(26, fps)} size={58} color={tone.fg} accent={tone.accent} align="center" /> : null}
      {P(scene, 'cta', '') ? (
        <div style={{marginTop: 10 * u, padding: `${18 * u}px ${44 * u}px`, borderRadius: 999, border: `${1.5 * u}px solid ${tone.fg}`,
          fontFamily: FONTS.sans, fontSize: 20 * u, letterSpacing: '0.24em', textTransform: 'uppercase', color: tone.fg,
          opacity: enter(frame, f(48, fps), f(20, fps))}}>{P(scene, 'cta', '')}</div>
      ) : null}
    </AbsoluteFill>
  );
};

export const SCENES: Record<string, React.FC<SceneProps>> = {
  TitleReveal, ChessHero, MediaPanels, LogoWall, Silhouette, Statement, Stats, IconFeatures, EndCard,
};
