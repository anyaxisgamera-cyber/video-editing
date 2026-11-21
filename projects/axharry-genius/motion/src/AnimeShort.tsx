import {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Img,
  continueRender,
  delayRender,
  interpolate,
  random,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

/*
 * AXHARRY anime storytelling short. Original anime-style art per line, cut into
 * 1-2.5 s shots with crash zooms, a chromatic-aberration snap and micro-shake on
 * every cut; speed lines and halftone on intense beats; caption chunks of 1-4
 * words timed to the narration (key words glowing); a glass hook badge on top;
 * the original logo in a glass badge at bottom-centre; a crimson grade that turns
 * gold for the closing message; the logo badge rises to centre for the end card.
 */

type Word = {text: string; start: number; end: number; key: boolean};
type Chunk = {start: number; end: number; words: Word[]};
type Shot = {start: number; end: number; image: string; framing: number};
type Scene = {id: string; line: number; start: number; end: number; words: Word[]; chunks: Chunk[]; shots: Shot[]};
type FontRole = {family: string; files: {weight: string; style: string; src: string}[]};
export type AnimeProps = {
  canvas: {width: number; height: number; fps: number; durationInFrames: number};
  language: 'en' | 'te';
  fonts: {caption: FontRole; label: FontRole; labelTe: FontRole};
  hook: string;
  logo: string;
  goldFrom: number;
  endCard: number;
  intense: string[];
  scenes: Scene[];
};

const RED = '#FF2A3D';
const GOLD = '#FFC857';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const easeOut = (x: number) => 1 - Math.pow(1 - x, 3);

const useFonts = (roles: FontRole[]) => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    Promise.all(roles.flatMap((r) => r.files.map((f) =>
      new FontFace(r.family, `url(${staticFile(f.src)}) format('woff2')`, {weight: f.weight, style: f.style}).load())))
      .then((faces) => {
        faces.forEach((face) => document.fonts.add(face));
        return document.fonts.ready;
      })
      .then(() => continueRender(handle));
  }, [roles, handle]);
};

// framing presets: [start scale, end scale, start x, end x, start y, end y]
const FRAMINGS: number[][] = [
  [1.12, 1.24, 0, -14, 10, -18],
  [1.30, 1.16, -24, 18, -10, 8],
  [1.10, 1.30, 20, -6, 24, -10],
  [1.42, 1.26, 0, 0, -30, 6],
];

const ShotView = ({shot, t, intense, shake}: {shot: Shot; t: number; intense: boolean; shake: number}) => {
  const f = FRAMINGS[shot.framing];
  const life = Math.min(1, Math.max(0, (t - shot.start) / Math.max(0.4, shot.end - shot.start)));
  const crash = interpolate(t, [shot.start, shot.start + 0.22], [intense ? 0.28 : 0.16, 0], {...clamp, easing: easeOut});
  const scale = interpolate(life, [0, 1], [f[0], f[1]]) * 0.92 + crash;
  const jx = shake * (random(`sx${Math.floor(t * 30)}`) - 0.5) * 22;
  const jy = shake * (random(`sy${Math.floor(t * 30)}`) - 0.5) * 22;
  const x = interpolate(life, [0, 1], [f[2], f[3]]) + jx;
  const y = interpolate(life, [0, 1], [f[4], f[5]]) + jy;
  const src = staticFile(shot.image);
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {/* ambient fill: same art, heavily blurred and darkened */}
      <Img src={src} style={{position: 'absolute', left: -300, top: -200, width: 1680, height: 2320, objectFit: 'cover',
        filter: 'blur(46px) brightness(0.42) saturate(1.2)', transform: `scale(${1 + life * 0.05})`}} />
      {/* art panel: full width, faded at the bottom so captions sit over it */}
      <div style={{position: 'absolute', left: 0, top: 290, width: 1080, height: 1080, overflow: 'hidden',
        maskImage: 'linear-gradient(180deg, black 0%, black 72%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(180deg, black 0%, black 72%, transparent 100%)',
        transform: `translate(${jx * 0.5}px, ${jy * 0.5}px)`}}>
        <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover',
          transform: `translate(${x}px, ${y}px) scale(${scale})`, filter: 'contrast(1.12) saturate(1.05)'}} />
      </div>
    </AbsoluteFill>
  );
};

const SpeedLines = ({t, opacity}: {t: number; opacity: number}) => {
  if (opacity <= 0) return null;
  const n = 64;
  const rot = (t * 40) % 360;
  return (
    <svg width={1080} height={1920} style={{position: 'absolute', inset: 0, opacity, mixBlendMode: 'screen'}}>
      <g transform={`translate(540 830) rotate(${rot})`}>
        {Array.from({length: n}, (_, i) => {
          const a = (i / n) * Math.PI * 2 + random(`a${i}`) * 0.05;
          const r0 = 380 + random(`r${i}`) * 220;
          const w = 2 + random(`w${i}`) * 5;
          return <line key={i} x1={Math.cos(a) * r0} y1={Math.sin(a) * r0} x2={Math.cos(a) * 1500} y2={Math.sin(a) * 1500}
            stroke="white" strokeWidth={w} strokeOpacity={0.35 + random(`o${i}`) * 0.4} />;
        })}
      </g>
    </svg>
  );
};

const Halftone = ({opacity}: {opacity: number}) => (
  <AbsoluteFill style={{opacity, backgroundImage: 'radial-gradient(rgba(0,0,0,0.55) 2.2px, transparent 2.6px)', backgroundSize: '12px 12px',
    maskImage: 'radial-gradient(ellipse 75% 60% at 50% 45%, transparent 55%, black 100%)',
    WebkitMaskImage: 'radial-gradient(ellipse 75% 60% at 50% 45%, transparent 55%, black 100%)'}} />
);

const Grain = ({frame}: {frame: number}) => (
  <svg width={1080} height={1920} style={{position: 'absolute', inset: 0, opacity: 0.09, mixBlendMode: 'overlay'}}>
    <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={frame % 12} /></filter>
    <rect width="100%" height="100%" filter="url(#grain)" />
  </svg>
);

/** Caption chunk: words pop in on their spoken time; key words glow red (gold at the end). */
const Caption = ({chunk, t, fonts, lang, gold}: {chunk: Chunk; t: number; fonts: AnimeProps['fonts']; lang: 'en' | 'te'; gold: number}) => {
  const out = interpolate(t, [chunk.end - 0.08, chunk.end], [1, 0], clamp);
  const keyColor = gold > 0.5 ? GOLD : RED;
  const size = lang === 'en' ? 82 : 62;
  return (
    <div style={{position: 'absolute', left: 60, right: 60, top: 1290, height: 310, display: 'flex', flexWrap: 'wrap',
      justifyContent: 'center', alignContent: 'center', alignItems: 'baseline', opacity: out, columnGap: 22, rowGap: 6}}>
      {chunk.words.map((w, i) => {
        const p = easeOut(interpolate(t, [w.start - 0.05, w.start + 0.14], [0, 1], clamp));
        const k = w.key;
        return (
          <span key={i} style={{
            display: 'inline-block', fontFamily: `'${fonts.caption.family}', sans-serif`, fontWeight: 800,
            fontSize: size * (k ? 1.18 : 1), lineHeight: 1.12, letterSpacing: lang === 'en' ? -1.5 : 0,
            textTransform: lang === 'en' ? 'uppercase' : 'none',
            color: k ? keyColor : '#FFFFFF',
            textShadow: k
              ? `0 0 18px ${keyColor}cc, 0 0 44px ${keyColor}88, 0 4px 14px rgba(0,0,0,0.9)`
              : '0 4px 16px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.9)',
            WebkitTextStroke: k ? undefined : '1.5px rgba(0,0,0,0.55)',
            opacity: p, transform: `translateY(${(1 - p) * 26}px) scale(${0.86 + 0.14 * p + (k ? (1 - p) * 0.25 : 0)})`,
            filter: `blur(${(1 - p) * 6}px)`,
          }}>{w.text}</span>
        );
      })}
    </div>
  );
};

const HookBadge = ({text, fonts, lang, t}: {text: string; fonts: AnimeProps['fonts']; lang: 'en' | 'te'; t: number}) => {
  const p = easeOut(interpolate(t, [0.2, 0.8], [0, 1], clamp));
  return (
    <div style={{position: 'absolute', top: 150, left: 70, right: 70, display: 'flex', justifyContent: 'center', opacity: p,
      transform: `translateY(${(1 - p) * -20}px)`}}>
      <div style={{padding: '16px 30px', borderRadius: 26, background: 'rgba(10,10,14,0.42)', border: '1.5px solid rgba(255,255,255,0.22)',
        backdropFilter: 'blur(16px) saturate(140%)', WebkitBackdropFilter: 'blur(16px) saturate(140%)',
        boxShadow: '0 10px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.18)', textAlign: 'center',
        fontFamily: lang === 'en' ? `'${fonts.label.family}'` : `'${fonts.labelTe.family}', '${fonts.label.family}'`,
        fontWeight: lang === 'en' ? 800 : 600, fontSize: lang === 'en' ? 34 : 34, lineHeight: 1.35, letterSpacing: lang === 'en' ? 1.2 : 0,
        color: 'rgba(255,255,255,0.94)', maxWidth: 900}}>{text}</div>
    </div>
  );
};

/** Original logo, unmodified pixels and proportions, in a glass badge. */
const LogoBadge = ({src, t, endCard, total}: {src: string; t: number; endCard: number; total: number}) => {
  const {fps} = useVideoConfig();
  const rise = spring({frame: Math.max(0, (t - endCard) * fps), fps, config: {damping: 16, mass: 0.9}});
  const size = 150 + rise * 230; // 150 px badge -> 380 px on the end card
  const cy = interpolate(rise, [0, 1], [1725, 900]);
  const glow = 0.35 + 0.25 * Math.sin(t * 2.2);
  const ring = interpolate(t, [endCard + 0.2, endCard + 1.2], [0, 1], clamp);
  return (
    <div style={{position: 'absolute', left: 540 - size / 2, top: cy - size / 2, width: size, height: size}}>
      <div style={{position: 'absolute', inset: -10, borderRadius: size * 0.26 + 10,
        background: 'rgba(255,255,255,0.10)', border: '1.5px solid rgba(255,255,255,0.35)',
        backdropFilter: 'blur(14px) saturate(150%)', WebkitBackdropFilter: 'blur(14px) saturate(150%)',
        boxShadow: `0 18px 40px rgba(0,0,0,0.55), 0 0 ${30 + rise * 40}px rgba(255,255,255,${glow * 0.5}), inset 0 1px 0 rgba(255,255,255,0.45)`}} />
      <Img src={staticFile(src)} style={{position: 'absolute', inset: 0, width: size, height: size, objectFit: 'contain',
        borderRadius: size * 0.22, opacity: 0.96}} />
      {/* glass reflection */}
      <div style={{position: 'absolute', inset: 0, borderRadius: size * 0.22, overflow: 'hidden', pointerEvents: 'none'}}>
        <div style={{position: 'absolute', left: -size, top: -size * 0.2, width: size * 0.5, height: size * 1.6,
          background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent)',
          transform: `translateX(${((t * 0.35) % 1) * size * 3}px) rotate(20deg)`}} />
        <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(160deg, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0) 38%)'}} />
      </div>
      {ring > 0 ? (
        <svg width={size + 60} height={size + 60} style={{position: 'absolute', left: -30, top: -30, transform: 'rotate(-90deg)'}}>
          <rect x={6} y={6} width={size + 48} height={size + 48} rx={size * 0.26 + 20} fill="none" stroke={GOLD} strokeWidth={3}
            pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ring} opacity={0.9} />
        </svg>
      ) : null}
      <div style={{position: 'absolute', inset: 0, opacity: interpolate(t, [total - 0.4, total], [0, 1], clamp), background: 'black'}} />
    </div>
  );
};

export const AnimeShort = (props: AnimeProps) => {
  const {fonts, scenes, language: lang} = props;
  useFonts([fonts.caption, fonts.label, fonts.labelTe]);
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const total = durationInFrames / fps;

  const scene = scenes.find((s) => t >= s.start && t < s.end) ?? scenes[scenes.length - 1];
  const shot = scene.shots.find((s) => t >= s.start && t < s.end) ?? scene.shots[scene.shots.length - 1];
  const intense = props.intense.includes(scene.id);
  const sinceCut = t - shot.start;
  const keyHit = scene.words.filter((w) => w.key && t >= w.start && t < w.start + 0.22).length > 0;
  const shake = (sinceCut < 0.16 ? 1 : 0) * (intense ? 1 : 0.5) + (keyHit ? 0.6 : 0);
  const ca = interpolate(sinceCut, [0, 0.18], [intense ? 14 : 9, 0], clamp);
  const flash = interpolate(sinceCut, [0, 0.1], [intense ? 0.45 : 0.22, 0], clamp);
  const gold = interpolate(t, [props.goldFrom, props.goldFrom + 0.9], [0, 1], clamp);
  const ending = interpolate(t, [props.endCard, props.endCard + 0.6], [0, 1], clamp);
  const chunk = scenes.flatMap((s) => s.chunks).find((c) => t >= c.start - 0.05 && t < c.end);
  const speed = intense ? interpolate(sinceCut, [0, 0.15, 0.9], [0, 0.85, 0.35], clamp) : 0;

  return (
    <AbsoluteFill style={{backgroundColor: '#050506'}}>
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <filter id="ca" x="0" y="0" width="100%" height="100%">
          <feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r" />
          <feOffset in="r" dx={ca} dy={0} result="r2" />
          <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" result="gb" />
          <feOffset in="gb" dx={-ca} dy={0} result="gb2" />
          <feBlend in="r2" in2="gb2" mode="screen" />
        </filter>
      </svg>
      <AbsoluteFill style={{filter: ca > 0.4 ? 'url(#ca)' : undefined, opacity: 1 - ending * 0.75}}>
        <ShotView shot={shot} t={t} intense={intense} shake={shake} />
        {/* grade: crimson -> gold */}
        <AbsoluteFill style={{background: `linear-gradient(180deg, rgba(5,5,6,0.55) 0%, rgba(5,5,6,0.05) 28%, rgba(5,5,6,0.1) 52%, rgba(5,5,6,0.82) 100%)`}} />
        <AbsoluteFill style={{background: gold > 0 ? `rgba(255,170,60,${0.16 * gold})` : 'rgba(150,10,25,0.20)', mixBlendMode: 'soft-light'}} />
        <AbsoluteFill style={{background: `rgba(${Math.round(120 + 120 * gold)},${Math.round(10 + 140 * gold)},${Math.round(25 + 20 * gold)},0.16)`, mixBlendMode: 'color'}} />
        <AbsoluteFill style={{background: 'radial-gradient(ellipse 80% 60% at 50% 45%, transparent 45%, rgba(0,0,0,0.75) 100%)'}} />
        <SpeedLines t={t} opacity={speed} />
        <Halftone opacity={intense ? 0.55 : 0.25} />
        <Grain frame={frame} />
        <AbsoluteFill style={{background: gold > 0.5 ? GOLD : 'white', opacity: flash, mixBlendMode: 'overlay'}} />
      </AbsoluteFill>
      {ending > 0 ? <AbsoluteFill style={{background: `radial-gradient(circle at 50% 47%, rgba(255,200,87,${0.25 * ending}) 0%, transparent 55%)`}} /> : null}
      <HookBadge text={props.hook} fonts={fonts} lang={lang} t={t} />
      {chunk && t < props.endCard ? <Caption chunk={chunk} t={t} fonts={fonts} lang={lang} gold={gold} /> : null}
      <LogoBadge src={props.logo} t={t} endCard={props.endCard} total={total} />
    </AbsoluteFill>
  );
};
