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
 * Editorial-poster kinetic short (v3, Telugu). Light grey editorial pages with
 * small words, slanted green serif accents, label boxes and drawn outlines, a
 * grid + green circle badge behind objects, a chapter/verse header, vertical
 * side label and markers; occasional green and black full-bleed scenes. A
 * frosted-glass watermark stays on screen; the film ends on a circular logo.
 * Every narration word is shown exactly once at its spoken time.
 */

type Word = {text: string; start: number; end: number; key: boolean};
type EScene = {
  bg: 'light' | 'black' | 'green';
  layout?: 'badge' | 'objectBelow' | 'card' | 'verse';
  accent?: 'label' | 'outline';
  object?: string;
  grow?: boolean;
  header?: boolean;
  enter?: 'circle';
  exit?: 'tilt';
  words: Word[];
  items?: {text: string; start: number}[];
  line: string;
  start: number;
  end: number;
};
type FontRole = {family: string; files: {weight: string; style: string; src: string}[]};
export type EditorialProps = {
  canvas: {width: number; height: number; fps: number; durationInFrames: number};
  fonts: {sans: FontRole; serif: FontRole; label: FontRole; elegant: FontRole};
  sideLabel: string;
  header: {left: string; right: string; leftLabel: string; rightLabel: string};
  cardTitle: string;
  watermark: string;
  logo: {src: string; start: number};
  verse: {number: string; text: string; reference: string};
  scenes: EScene[];
  final: {lines: string[]; key: string[]; object: string; start: number};
};

const C = {
  light: '#F4F4F4',
  ink: '#121212',
  grey: '#8E8E8E',
  green: '#30B040',
  greenDeep: '#2C8F38',
  greenBright: '#43D35F',
  black: '#050505',
  marker: '#E2B33C',
  navy: '#1E2462',
};
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const CIRCLE_IN = 0.34;
const TILT_OUT = 0.4;

const useFonts = (roles: FontRole[]) => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    Promise.all(
      roles.flatMap((r) =>
        r.files.map((f) => new FontFace(r.family, `url(${staticFile(f.src)}) format('woff2')`, {weight: f.weight, style: f.style}).load()),
      ),
    )
      .then((faces) => {
        faces.forEach((face) => document.fonts.add(face));
        return document.fonts.ready;
      })
      .then(() => continueRender(handle));
  }, [roles, handle]);
};

const reveal = (t: number, start: number, dur = 0.22) => {
  const p = interpolate(t, [start - 0.05, start + dur], [0, 1], clamp);
  return 1 - Math.pow(1 - p, 3);
};

/* ---------- decorations ---------- */

const SideLabel = ({text, dark, font}: {text: string; dark: boolean; font: string}) => (
  <>
    <div style={{position: 'absolute', left: 30, top: 960, transform: 'translate(-50%, -50%) rotate(-90deg) translateY(50%)',
      transformOrigin: 'center', whiteSpace: 'nowrap', fontFamily: font, fontWeight: 600, fontSize: 22, letterSpacing: 7,
      color: dark ? 'rgba(255,255,255,0.45)' : '#9C9C9C'}}>{text}</div>
    {[230, 1130].map((y) => (
      <svg key={y} width={18} height={20} style={{position: 'absolute', right: 34, top: y}}>
        <path d="M9 0 L18 20 L0 20 Z" fill={C.marker} />
      </svg>
    ))}
    <div style={{position: 'absolute', right: 30, top: 700, fontFamily: font, fontWeight: 800, fontSize: 22,
      color: dark ? 'rgba(255,255,255,0.45)' : '#9C9C9C', transform: 'rotate(-90deg)'}}>14</div>
  </>
);

const Header = ({h, t, start, fonts}: {h: EditorialProps['header']; t: number; start: number; fonts: EditorialProps['fonts']}) => {
  const p = reveal(t, start + 0.05, 0.35);
  return (
    <div style={{position: 'absolute', top: 150, left: 70, right: 70, height: 170, opacity: p}}>
      <div style={{position: 'absolute', left: 0, top: 0, fontFamily: `'${fonts.label.family}'`, fontWeight: 800, fontSize: 150,
        letterSpacing: -6, lineHeight: 1, color: C.ink}}>{h.left}</div>
      <div style={{position: 'absolute', left: 130, top: 6, fontFamily: `'${fonts.sans.family}'`, fontSize: 22, fontWeight: 600, color: '#555'}}>{h.leftLabel}</div>
      <div style={{position: 'absolute', left: 130, right: 250, top: 62, height: 16, background: C.ink,
        transform: `scaleX(${p})`, transformOrigin: 'left'}} />
      <div style={{position: 'absolute', left: 130, top: 96, fontFamily: `'${fonts.label.family}'`, fontSize: 15, fontWeight: 600,
        color: '#666', letterSpacing: 2, lineHeight: 1.35}}>JAMES · TELUBSI<br />CHAPTER 1 · VERSE 14</div>
      <div style={{position: 'absolute', right: 0, top: 0, fontFamily: `'${fonts.label.family}'`, fontWeight: 800, fontSize: 150,
        letterSpacing: -6, lineHeight: 1, color: C.ink}}>{h.right}</div>
      <div style={{position: 'absolute', right: 190, top: 6, fontFamily: `'${fonts.sans.family}'`, fontSize: 22, fontWeight: 600, color: '#555'}}>{h.rightLabel}</div>
    </div>
  );
};

const Grid = ({t, start, cy}: {t: number; start: number; cy: number}) => {
  const p = reveal(t, start, 0.4);
  const size = 760;
  return (
    <svg width={size + 80} height={size + 80} style={{position: 'absolute', left: 540 - size / 2 - 40, top: cy - size / 2 - 40, opacity: p}}>
      {Array.from({length: 13}, (_, i) => (
        <g key={i}>
          <line x1={40 + (i * size) / 12} y1={40} x2={40 + (i * size) / 12} y2={40 + size} stroke="rgba(0,0,0,0.09)" strokeWidth={1.4} />
          <line x1={40} y1={40 + (i * size) / 12} x2={40 + size} y2={40 + (i * size) / 12} stroke="rgba(0,0,0,0.09)" strokeWidth={1.4} />
        </g>
      ))}
      <line x1={40 + size / 2} y1={0} x2={40 + size / 2} y2={size + 80} stroke="rgba(0,0,0,0.45)" strokeWidth={2} />
      <line x1={0} y1={40 + size / 2} x2={size + 80} y2={40 + size / 2} stroke="rgba(0,0,0,0.45)" strokeWidth={2} />
      {[-5, 5].map((n) => (
        <g key={n}>
          <text x={40 + size / 2 + (n * size) / 12 - 8} y={40 + size / 2 + 34} fontSize={22} fill="#555" fontFamily="sans-serif">{n}</text>
          <text x={40 + size / 2 + 10} y={40 + size / 2 - (n * size) / 12 + 8} fontSize={22} fill="#555" fontFamily="sans-serif">{n}</text>
        </g>
      ))}
    </svg>
  );
};

const Rays = () => (
  <>
    {[[-18, 300, 0.07], [-8, 560, 0.05], [6, 760, 0.06], [16, 420, 0.04]].map(([rot, x, o], i) => (
      <div key={i} style={{position: 'absolute', top: -200, left: x, width: 160, height: 2400,
        background: `linear-gradient(180deg, rgba(255,255,255,${o}) 0%, rgba(255,255,255,0) 75%)`,
        transform: `rotate(${rot}deg)`, filter: 'blur(18px)'}} />
    ))}
  </>
);

const Dust = ({t}: {t: number}) => (
  <>
    {Array.from({length: 40}, (_, i) => {
      const x = random(`dx${i}`) * 1080;
      const y = (random(`dy${i}`) * 1920 + t * (8 + random(`ds${i}`) * 16)) % 1920;
      return <div key={i} style={{position: 'absolute', left: x, top: y, width: 3, height: 3, borderRadius: 2,
        background: 'white', opacity: 0.12 + 0.25 * random(`do${i}`)}} />;
    })}
  </>
);

const GreenLight = ({t}: {t: number}) => (
  <AbsoluteFill style={{
    background: `linear-gradient(118deg, rgba(0,0,0,0) ${30 + t * 2}%, rgba(0,0,0,0.22) ${38 + t * 2}%, rgba(0,0,0,0) ${46 + t * 2}%,
      rgba(0,0,0,0) ${62 + t * 2}%, rgba(0,0,0,0.18) ${70 + t * 2}%, rgba(0,0,0,0) ${80 + t * 2}%)`,
  }} />
);

const ObjectImg = ({name, t, start, grow, keyStart, style}: {
  name: string; t: number; start: number; grow?: boolean; keyStart?: number; style: React.CSSProperties;
}) => {
  const {fps} = useVideoConfig();
  const s = spring({frame: Math.max(0, (t - start) * fps), fps, config: {damping: 14, mass: 0.7}});
  const g = grow && keyStart !== undefined ? interpolate(t, [keyStart - 0.05, keyStart + 0.5], [0.8, 1.1], clamp) : 1;
  return (
    <Img src={staticFile(`media/obj-${name}.png`)} style={{
      position: 'absolute', objectFit: 'contain',
      filter: 'drop-shadow(0 30px 28px rgba(0,0,0,0.25)) drop-shadow(0 6px 8px rgba(0,0,0,0.18))',
      transform: `translateY(${Math.sin((t - start) * 2) * 8}px) rotate(${interpolate(s, [0, 1], [-8, 0])}deg) scale(${interpolate(s, [0, 1], [0.84, 1]) * g})`,
      opacity: Math.min(1, s * 1.4), ...style,
    }} />
  );
};

/* ---------- words ---------- */

const EWord = ({w, t, size, tone, accent, fonts, scale = 1}: {
  w: Word; t: number; size: number; tone: 'light' | 'dark' | 'green'; accent?: 'label' | 'outline';
  fonts: EditorialProps['fonts']; scale?: number;
}) => {
  const p = reveal(t, w.start);
  const isKey = w.key;
  const keySize = size * 1.42 * scale;
  const color = isKey
    ? accent === 'label' || tone === 'green' ? '#FFFFFF' : tone === 'dark' ? C.greenBright : C.green
    : tone === 'light' ? C.ink : '#FFFFFF';
  const box = isKey && accent === 'label' ? reveal(t, w.start - 0.08, 0.3) : 0;
  const outline = isKey && accent === 'outline' ? interpolate(t, [w.start, w.start + 0.45], [0, 1], clamp) : 0;
  return (
    <span style={{position: 'relative', display: 'inline-block', margin: `0 ${size * 0.16}px`, padding: isKey && accent ? '0 18px' : 0}}>
      {isKey && accent === 'label' ? (
        <span style={{position: 'absolute', left: 0, right: 0, top: '12%', bottom: '4%', background: C.green,
          transform: `scaleX(${box})`, transformOrigin: 'left'}} />
      ) : null}
      {isKey && accent === 'outline' ? (
        <svg style={{position: 'absolute', left: -6, top: '6%', width: 'calc(100% + 12px)', height: '96%', overflow: 'visible'}}
          viewBox="0 0 100 100" preserveAspectRatio="none">
          <rect x={0} y={0} width={100} height={100} fill="none" stroke={C.green} strokeWidth={2.4} vectorEffect="non-scaling-stroke"
            pathLength={1} strokeDasharray={1} strokeDashoffset={1 - outline} />
        </svg>
      ) : null}
      <span style={{
        position: 'relative', display: 'inline-block',
        fontFamily: isKey ? `'${fonts.serif.family}'` : `'${fonts.sans.family}'`,
        fontWeight: isKey ? 700 : 600,
        fontSize: isKey ? keySize : size * scale,
        letterSpacing: isKey ? -0.01 * keySize : -0.02 * size,
        lineHeight: 1.32,
        color,
        textShadow: isKey && tone === 'dark' ? `0 0 22px ${C.green}aa` : tone === 'dark' ? '0 0 16px rgba(255,255,255,0.25)' : 'none',
        opacity: p,
        filter: `blur(${(1 - p) * 10}px)`,
        transform: `translateY(${(1 - p) * 16}px) ${isKey ? 'skewX(-9deg)' : ''}`,
      }}>{w.text}</span>
    </span>
  );
};

const WordBlock = ({words, t, size, tone, accent, fonts, style, tilt = 0, align = 'center'}: {
  words: Word[]; t: number; size: number; tone: 'light' | 'dark' | 'green'; accent?: 'label' | 'outline';
  fonts: EditorialProps['fonts']; style: React.CSSProperties; tilt?: number; align?: 'center' | 'left';
}) => (
  <div style={{position: 'absolute', display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', alignContent: 'center',
    justifyContent: align === 'left' ? 'flex-start' : 'center', rowGap: 4,
    transform: `translate(${tilt * 150}px, ${tilt * -110}px) rotate(${tilt * -14}deg)`,
    filter: tilt > 0 ? `blur(${tilt * 12}px)` : undefined, opacity: 1 - tilt * 0.9, ...style}}>
    {words.map((w, i) => <EWord key={i} w={w} t={t} size={size} tone={tone} accent={accent} fonts={fonts} />)}
  </div>
);

/* ---------- scenes ---------- */

const Card = ({scene, t, props}: {scene: EScene; t: number; props: EditorialProps}) => {
  const {fps} = useVideoConfig();
  const s = spring({frame: Math.max(0, (t - scene.start) * fps), fps, config: {damping: 13, mass: 0.8}});
  const items = scene.items ?? [];
  const current = items.filter((it) => t >= it.start - 0.05).length;
  const pop = items[current - 1] ? reveal(t, items[current - 1].start, 0.25) : 1;
  return (
    <div style={{position: 'absolute', left: 150, right: 150, top: 470, padding: '56px 54px 50px', background: '#FBFBFB',
      boxShadow: '0 40px 80px rgba(0,0,0,0.35)', transform: `translateY(${interpolate(s, [0, 1], [220, 0])}px) rotate(${interpolate(s, [0, 1], [5, -2])}deg)`,
      opacity: Math.min(1, s * 1.5)}}>
      <div style={{position: 'absolute', right: 40, top: 40, width: 120, height: 26, background: C.ink}} />
      <div style={{fontFamily: `'${props.fonts.sans.family}'`, fontWeight: 800, fontSize: 52, color: C.ink}}>{props.cardTitle}</div>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 26, marginTop: 6}}>
        <div style={{fontFamily: `'${props.fonts.label.family}'`, fontWeight: 800, fontSize: 250, lineHeight: 0.9, letterSpacing: -12,
          color: C.ink, transform: `skewX(-8deg) scale(${0.85 + 0.15 * pop})`, transformOrigin: 'left bottom', minWidth: 150}}>{Math.max(1, current)}</div>
        <div style={{fontFamily: `'${props.fonts.label.family}'`, fontWeight: 800, fontSize: 40, color: C.green, paddingBottom: 26}}>/ 3</div>
      </div>
      <div style={{height: 6, background: C.ink, margin: '22px 0 26px', width: '72%'}} />
      {items.map((item, i) => {
        const p = reveal(t, item.start - 0.04, 0.26);
        return (
          <div key={item.text} style={{display: 'flex', alignItems: 'center', gap: 18, marginBottom: 16, opacity: p * (i < current - 1 ? 0.55 : 1),
            transform: `translateX(${(1 - p) * -24}px)`, filter: `blur(${(1 - p) * 8}px)`}}>
            <svg width={38} height={38} viewBox="0 0 40 40" style={{flex: 'none'}}>
              <circle cx={20} cy={20} r={17} fill={i === current - 1 ? C.green : 'none'} stroke={C.green} strokeWidth={3.5} />
              <path d="M11 21 L18 28 L30 13" fill="none" stroke={i === current - 1 ? 'white' : C.green} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span style={{fontFamily: `'${props.fonts.sans.family}'`, fontWeight: 600, fontSize: 44, color: C.ink}}>{item.text}</span>
          </div>
        );
      })}
    </div>
  );
};

const Verse = ({scene, t, props}: {scene: EScene; t: number; props: EditorialProps}) => {
  const p = reveal(t, scene.start + 0.05, 0.4);
  const refP = reveal(t, scene.words[scene.words.length - 1].start, 0.5);
  return (
    <div style={{position: 'absolute', left: 110, right: 110, top: 430}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 20, opacity: p, marginBottom: 34}}>
        <span style={{fontFamily: `'${props.fonts.serif.family}'`, fontWeight: 700, fontSize: 74, color: C.green, transform: 'skewX(-9deg)'}}>
          {props.verse.number}
        </span>
        <div style={{flex: 1, height: 3, background: C.ink, transform: `scaleX(${p})`, transformOrigin: 'left'}} />
      </div>
      <div style={{display: 'flex', flexWrap: 'wrap', alignItems: 'baseline'}}>
        {scene.words.map((w, i) => {
          const q = reveal(t, w.start);
          return (
            <span key={i} style={{fontFamily: `'${props.fonts.serif.family}'`, fontWeight: w.key ? 700 : 500, fontSize: 62,
              lineHeight: 1.55, marginRight: 18, color: w.key ? C.green : C.ink, opacity: q, filter: `blur(${(1 - q) * 9}px)`,
              transform: `translateY(${(1 - q) * 14}px)`}}>{w.text}</span>
          );
        })}
      </div>
      <div style={{marginTop: 40, display: 'flex', alignItems: 'center', gap: 18, opacity: refP}}>
        <div style={{width: 60, height: 3, background: C.green}} />
        <span style={{fontFamily: `'${props.fonts.sans.family}'`, fontWeight: 800, fontSize: 38, color: C.ink, letterSpacing: 1}}>
          {props.verse.reference}
        </span>
      </div>
    </div>
  );
};

const SceneView = ({scene, t, index, props}: {scene: EScene; t: number; index: number; props: EditorialProps}) => {
  const {fonts} = props;
  const tone = scene.bg === 'light' ? 'light' : scene.bg === 'green' ? 'green' : 'dark';
  const chars = scene.line.length;
  const size = Math.max(48, Math.min(66, 92 - chars * 0.55));
  const life = Math.min(1, Math.max(0, (t - scene.start) / Math.max(0.5, scene.end - scene.start)));
  const push = 1 + 0.05 * life;
  const drift = (index % 2 === 0 ? 1 : -1) * 0.5 * life;
  const circle = scene.enter === 'circle'
    ? interpolate(t, [scene.start, scene.start + CIRCLE_IN], [0, 1], {...clamp, easing: (x) => 1 - Math.pow(1 - x, 3)})
    : 1;
  const tilt = scene.exit === 'tilt' ? interpolate(t, [scene.end - TILT_OUT, scene.end], [0, 1], clamp) : 0;
  const keyWord = scene.words.find((w) => w.key);
  const bg = scene.bg === 'light' ? C.light : scene.bg === 'green' ? C.greenDeep : C.black;
  const badgeS = spring({frame: Math.max(0, (t - scene.start - 0.1) * 30), fps: 30, config: {damping: 12}});

  return (
    <AbsoluteFill style={{backgroundColor: bg, clipPath: circle < 1 ? `circle(${circle * 125}% at 50% 50%)` : undefined}}>
      <AbsoluteFill style={{transform: `scale(${push}) rotate(${drift}deg)`}}>
        {scene.bg === 'black' ? <><Rays /><Dust t={t} /></> : null}
        {scene.bg === 'green' ? <GreenLight t={t - scene.start} /> : null}
        <SideLabel text={props.sideLabel} dark={scene.bg !== 'light'} font={`'${fonts.label.family}', '${fonts.sans.family}'`} />
        {scene.header ? <Header h={props.header} t={t} start={scene.start} fonts={fonts} /> : null}

        {scene.layout === 'badge' ? (
          <>
            <Grid t={t} start={scene.start} cy={1060} />
            <div style={{position: 'absolute', left: 540 - 270, top: 1060 - 270, width: 540, height: 540, borderRadius: '50%',
              background: C.green, transform: `scale(${badgeS})`}} />
            {scene.object ? <ObjectImg name={scene.object} t={t} start={scene.start} grow={scene.grow} keyStart={keyWord?.start}
              style={{left: 540 - 300, top: 1060 - 300, width: 600, height: 600}} /> : null}
            <WordBlock words={scene.words} t={t} size={size} tone={tone} accent={scene.accent} fonts={fonts} tilt={tilt}
              style={{left: 90, right: 90, top: scene.header ? 380 : 420, minHeight: 200}} />
          </>
        ) : scene.layout === 'objectBelow' ? (
          <>
            {scene.object ? <ObjectImg name={scene.object} t={t} start={scene.start}
              style={{left: 190, top: 830, width: 700, height: 700}} /> : null}
            <WordBlock words={scene.words} t={t} size={size} tone={tone} accent={scene.accent} fonts={fonts} tilt={tilt}
              style={{left: 90, right: 90, top: 440, minHeight: 300}} />
          </>
        ) : scene.layout === 'card' ? (
          <Card scene={scene} t={t} props={props} />
        ) : scene.layout === 'verse' ? (
          <Verse scene={scene} t={t} props={props} />
        ) : (
          <WordBlock words={scene.words} t={t} size={size} tone={tone} accent={scene.accent} fonts={fonts} tilt={tilt}
            style={{left: 90, right: 90, top: 720, minHeight: 360}} />
        )}

        {/* small editorial body copy, as in the reference */}
        {scene.bg === 'light' && scene.layout !== 'verse' ? (
          <div style={{position: 'absolute', left: 230, right: 230, top: 1505, textAlign: 'center', fontFamily: `'${fonts.serif.family}'`,
            fontWeight: 500, fontSize: 24, lineHeight: 1.45, color: '#A3A3A3', opacity: reveal(t, scene.start + 0.2, 0.4)}}>{scene.line}</div>
        ) : null}
      </AbsoluteFill>
      {circle > 0 && circle < 0.98 && scene.enter === 'circle' ? (() => {
        const r = circle * 1.25 * Math.sqrt((1080 ** 2 + 1920 ** 2) / 2);
        return <div style={{position: 'absolute', left: 540 - r, top: 960 - r, width: 2 * r, height: 2 * r, borderRadius: '50%',
          boxShadow: `inset 0 0 0 ${16 * (1 - circle)}px ${C.green}`, opacity: 1 - circle}} />;
      })() : null}
    </AbsoluteFill>
  );
};

const Final = ({props, t}: {props: EditorialProps; t: number}) => {
  const {final, fonts} = props;
  const local = t - final.start;
  const toLogo = interpolate(t, [props.logo.start - 0.1, props.logo.start + 0.5], [0, 1], clamp);
  let k = 0;
  return (
    <AbsoluteFill style={{backgroundColor: C.black, opacity: interpolate(local, [0, 0.25], [0, 1], clamp)}}>
      <Rays />
      <Dust t={t} />
      <AbsoluteFill style={{transform: `scale(${1 - toLogo * 0.12})`, filter: `blur(${toLogo * 14}px)`, opacity: 1 - toLogo}}>
        <ObjectImg name={final.object} t={t} start={final.start} style={{left: 290, top: 280, width: 500, height: 500, opacity: 0.6}} />
        <div style={{position: 'absolute', top: 820, left: 80, right: 80, textAlign: 'center'}}>
          {final.lines.map((line, li) => (
            <div key={line} style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', marginBottom: 6}}>
              {line.split(' ').map((text) => {
                const start = final.start + 0.15 + li * 0.8 + (k++) * 0.12;
                return <EWord key={text + li} w={{text, start, end: start + 0.3, key: final.key.includes(text)}} t={t} size={64}
                  tone="dark" fonts={fonts} />;
              })}
            </div>
          ))}
          <div style={{marginTop: 36, opacity: reveal(t, final.start + 1.5, 0.4)}}>
            <span style={{display: 'inline-block', padding: '10px 28px', border: `2px solid ${C.green}`, borderRadius: 999,
              color: 'white', fontFamily: `'${fonts.sans.family}'`, fontWeight: 800, fontSize: 32, boxShadow: `0 0 24px ${C.green}55`}}>
              {props.verse.reference}
            </span>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const LogoEnd = ({props, t}: {props: EditorialProps; t: number}) => {
  const {fps, durationInFrames} = useVideoConfig();
  const local = t - props.logo.start;
  const open = interpolate(local, [0, 0.55], [0, 1], {...clamp, easing: (x) => 1 - Math.pow(1 - x, 3)});
  const s = spring({frame: Math.max(0, local * fps - 4), fps, config: {damping: 12, mass: 0.9}});
  const ring = interpolate(local, [0.2, 1.1], [0, 1], clamp);
  const end = interpolate(t, [durationInFrames / fps - 0.35, durationInFrames / fps], [1, 0], clamp);
  const R = 300;
  return (
    <AbsoluteFill style={{opacity: end}}>
      <AbsoluteFill style={{background: `radial-gradient(circle at 50% 46%, #1b2050 0%, #07080f 60%)`,
        clipPath: `circle(${open * 125}% at 50% 46%)`}}>
        <Dust t={t} />
        <div style={{position: 'absolute', left: 540 - R - 40, top: 880 - R - 40, width: 2 * R + 80, height: 2 * R + 80, borderRadius: '50%',
          background: `radial-gradient(circle, rgba(255,255,255,0.35) 0%, rgba(120,140,255,0.12) 45%, transparent 70%)`, opacity: s}} />
        <Img src={staticFile(props.logo.src)} style={{position: 'absolute', left: 540 - R, top: 880 - R, width: 2 * R, height: 2 * R,
          borderRadius: '50%', transform: `scale(${0.6 + 0.4 * s})`, opacity: Math.min(1, s * 1.6),
          boxShadow: '0 30px 80px rgba(0,0,0,0.55), 0 0 60px rgba(255,255,255,0.18)'}} />
        <svg width={2 * R + 60} height={2 * R + 60} style={{position: 'absolute', left: 540 - R - 30, top: 880 - R - 30,
          transform: `scale(${0.6 + 0.4 * s}) rotate(-90deg)`}}>
          <circle cx={R + 30} cy={R + 30} r={R + 18} fill="none" stroke="rgba(255,255,255,0.85)" strokeWidth={4}
            pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ring} strokeLinecap="round" />
          <circle cx={R + 30} cy={R + 30} r={R + 18} fill="none" stroke={C.green} strokeWidth={4}
            pathLength={1} strokeDasharray="0.12 0.88" strokeDashoffset={-ring * 0.9} strokeLinecap="round" opacity={ring} />
        </svg>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Frosted-glass watermark, visible for the whole film; ink adapts to the page tone. */
const Watermark = ({text, dark, fonts}: {text: string; dark: boolean; fonts: EditorialProps['fonts']}) => (
  <div style={{position: 'absolute', left: 0, right: 0, top: 1652, display: 'flex', justifyContent: 'center', pointerEvents: 'none'}}>
    <div style={{
      padding: '12px 34px 14px', borderRadius: 999,
      background: dark ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.45)',
      border: `1.5px solid ${dark ? 'rgba(255,255,255,0.32)' : 'rgba(255,255,255,0.9)'}`,
      backdropFilter: 'blur(14px) saturate(140%)', WebkitBackdropFilter: 'blur(14px) saturate(140%)',
      boxShadow: dark
        ? '0 8px 28px rgba(0,0,0,0.35), 0 0 22px rgba(255,255,255,0.10), inset 0 1px 0 rgba(255,255,255,0.25)'
        : '0 8px 26px rgba(0,0,0,0.10), 0 0 20px rgba(255,255,255,0.65), inset 0 1px 0 rgba(255,255,255,0.9)',
      fontFamily: `'${fonts.elegant.family}', serif`, fontStyle: 'italic', fontWeight: 600, fontSize: 38, letterSpacing: 1.2,
      color: dark ? 'rgba(255,255,255,0.88)' : 'rgba(20,20,20,0.72)',
      textShadow: dark ? '0 0 14px rgba(255,255,255,0.35)' : '0 0 10px rgba(255,255,255,0.9)',
    }}>{text}</div>
  </div>
);

export const EditorialShort = (props: EditorialProps) => {
  useFonts([props.fonts.sans, props.fonts.serif, props.fonts.label, props.fonts.elegant]);
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const scenes = props.scenes;
  const current = scenes.find((s) => t >= s.start && t < s.end);
  const dark = !current || current.bg !== 'light';
  return (
    <AbsoluteFill style={{backgroundColor: C.black}}>
      {scenes.map((scene, i) => {
        const next = scenes[i + 1];
        const until = next && next.enter === 'circle' ? scene.end + CIRCLE_IN : scene.end;
        if (t < scene.start || t >= until) return null;
        return <SceneView key={i} scene={scene} t={t} index={i} props={props} />;
      })}
      {t >= props.final.start && t < props.logo.start + 0.6 ? <Final props={props} t={t} /> : null}
      {t >= props.logo.start - 0.05 ? <LogoEnd props={props} t={t} /> : null}
      <Watermark text={props.watermark} dark={dark} fonts={props.fonts} />
    </AbsoluteFill>
  );
};
