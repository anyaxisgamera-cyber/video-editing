import {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Img,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

/*
 * Kinetic-typography short: alternating cream / black frames, bold tight sans,
 * words revealed on their spoken timestamps (blur + scale settle), key words in
 * red (glowing on black), isolated objects, pinned checklist card, circle wipes,
 * arc swooshes, slow push-ins. Every narration word is shown exactly once.
 */

type Word = {text: string; start: number; end: number; key: boolean};
type KScene = {
  bg: 'cream' | 'black';
  layout?: 'objectLeft' | 'objectBelow' | 'circleHead' | 'card';
  object?: string;
  grow?: boolean;
  arc?: boolean;
  enter?: 'circle';
  exit?: 'tilt';
  words: Word[];
  items?: {text: string; start: number}[];
  start: number;
  end: number;
};
export type KineticProps = {
  canvas: {width: number; height: number; fps: number; durationInFrames: number};
  language: 'en' | 'te';
  font: {family: string; files: {weight: string; style: string; src: string}[]; scale: number; finalScale: number};
  badge: string;
  cardTitle: string;
  scenes: KScene[];
  final: {
    lines: string[];
    key: string[];
    object: string;
    start: number;
    verse: {text: string; reference: string};
  };
};

const C = {
  cream: '#F5F1EA',
  black: '#050505',
  ink: '#121212',
  red: '#E3141B',
  grey: '#8D8B88',
  arc: '#C3C0BB',
  card: '#8A8987',
};
const CIRCLE_IN = 0.32; // seconds for a circle-wipe entrance
const TILT_OUT = 0.4; // seconds for a tilt exit

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const useFonts = (font: KineticProps['font']) => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    Promise.all(
      font.files.map((f) =>
        new FontFace(font.family, `url(${staticFile(f.src)}) format('woff2')`, {weight: f.weight, style: f.style}).load(),
      ),
    )
      .then((faces) => {
        faces.forEach((face) => document.fonts.add(face));
        return document.fonts.ready;
      })
      .then(() => continueRender(handle));
  }, [font, handle]);
};

const glow = `0 0 18px ${C.red}cc, 0 0 46px ${C.red}99, 0 0 90px ${C.red}55`;

/** One word: invisible until spoken, then blurs/scales into place. */
const KWord = ({w, t, size, dark, align}: {w: Word; t: number; size: number; dark: boolean; align?: 'left' | 'center'}) => {
  const p = interpolate(t, [w.start - 0.06, w.start + 0.2], [0, 1], clamp);
  const ease = 1 - Math.pow(1 - p, 3);
  const keyScale = w.key ? 1.42 : 1;
  return (
    <span
      style={{
        display: 'inline-block',
        margin: `0 ${size * 0.13}px`,
        fontSize: size * keyScale,
        fontWeight: w.key ? 800 : 600,
        letterSpacing: -0.045 * size * keyScale,
        lineHeight: 1.08,
        color: w.key ? C.red : dark ? '#FFFFFF' : C.ink,
        textShadow: w.key && dark ? glow : dark ? '0 0 22px rgba(255,255,255,0.35)' : 'none',
        opacity: ease,
        filter: `blur(${(1 - ease) * 14}px)`,
        transform: `translateY(${(1 - ease) * 22}px) scale(${1 + (1 - ease) * (w.key ? 0.55 : 0.3)})`,
        transformOrigin: align === 'left' ? 'left bottom' : 'center bottom',
      }}
    >
      {w.text}
    </span>
  );
};

const Grid = ({opacity}: {opacity: number}) => (
  <AbsoluteFill
    style={{
      opacity,
      backgroundImage:
        'linear-gradient(rgba(0,0,0,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.07) 1px, transparent 1px)',
      backgroundSize: '64px 64px',
      maskImage: 'radial-gradient(ellipse 45% 32% at 50% 48%, black 0%, transparent 100%)',
      WebkitMaskImage: 'radial-gradient(ellipse 45% 32% at 50% 48%, black 0%, transparent 100%)',
    }}
  />
);

const Barcode = () => {
  const bars = [3, 1, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1, 1, 2, 1, 3, 2, 1, 1, 2, 3, 1, 2, 1, 1, 3];
  let x = 0;
  return (
    <svg width={150} height={46} style={{position: 'absolute', top: 210, right: 92, opacity: 0.85}}>
      {bars.map((b, i) => {
        const r = i % 2 === 0 ? <rect key={i} x={x} y={0} width={b * 2} height={46} fill={C.ink} /> : null;
        x += b * 2 + 1.6;
        return r;
      })}
    </svg>
  );
};

const Arc = ({t, start}: {t: number; start: number}) => {
  const p = interpolate(t, [start, start + 0.45], [0, 1], clamp);
  return (
    <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}}>
      <path
        d="M -120 120 C 520 260, 760 760, 470 1120 S 380 1760, 980 2080"
        fill="none"
        stroke={C.arc}
        strokeWidth={92}
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - p}
        opacity={0.75}
      />
    </svg>
  );
};

const ObjectImg = ({name, dark, t, start, words, grow, style}: {
  name: string; dark: boolean; t: number; start: number; words: Word[]; grow?: boolean; style: React.CSSProperties;
}) => {
  const {fps} = useVideoConfig();
  const s = spring({frame: Math.max(0, (t - start) * fps), fps, config: {damping: 14, mass: 0.7}});
  const keyWord = words.find((w) => w.key);
  const g = grow && keyWord ? interpolate(t, [keyWord.start - 0.05, keyWord.start + 0.5], [0.78, 1.12], clamp) : 1;
  const float = Math.sin((t - start) * 2.1) * 10;
  return (
    <Img
      src={staticFile(`media/obj-${name}.png`)}
      style={{
        position: 'absolute',
        objectFit: 'contain',
        filter: dark
          ? 'drop-shadow(0 0 30px rgba(227,20,27,0.35)) drop-shadow(0 0 4px rgba(255,255,255,0.25))'
          : 'drop-shadow(0 34px 30px rgba(0,0,0,0.22)) drop-shadow(0 6px 8px rgba(0,0,0,0.18))',
        transform: `translateY(${float}px) rotate(${interpolate(s, [0, 1], [-9, 0])}deg) scale(${interpolate(s, [0, 1], [0.82, 1]) * g})`,
        opacity: Math.min(1, s * 1.4),
        ...style,
      }}
    />
  );
};

const Card = ({scene, t, title, size}: {scene: KScene; t: number; title: string; size: number}) => {
  const {fps} = useVideoConfig();
  const s = spring({frame: Math.max(0, (t - scene.start) * fps), fps, config: {damping: 12, mass: 0.8}});
  const items = scene.items ?? [];
  return (
    <div
      style={{
        position: 'absolute',
        left: 150,
        right: 150,
        top: 560,
        padding: '84px 56px 70px',
        background: C.card,
        boxShadow: '0 40px 70px rgba(0,0,0,0.28), 0 6px 14px rgba(0,0,0,0.18)',
        transform: `translateY(${interpolate(s, [0, 1], [-260, 0])}px) rotate(${interpolate(s, [0, 1], [-7, -1.5])}deg)`,
        opacity: Math.min(1, s * 1.5),
      }}
    >
      {/* push pin */}
      <div style={{position: 'absolute', top: -34, left: '50%', marginLeft: -30, width: 60, height: 60, borderRadius: '50%',
        background: `radial-gradient(circle at 35% 30%, #ff7a7a 0%, ${C.red} 45%, #8f070b 100%)`, boxShadow: '0 10px 14px rgba(0,0,0,0.35)'}} />
      <div style={{color: 'white', fontWeight: 800, fontSize: size * 1.35, letterSpacing: -0.04 * size * 1.35, lineHeight: 1.05}}>
        {title}
      </div>
      <div style={{height: 8, background: '#2b2b2b', margin: '26px 0 34px', borderRadius: 4}} />
      {items.map((item, i) => {
        const p = interpolate(t, [item.start - 0.08, item.start + 0.22], [0, 1], clamp);
        const later = items[i + 1] && t > items[i + 1].start ? 0.86 : 1;
        return (
          <div key={item.text} style={{display: 'flex', alignItems: 'center', gap: 22, marginBottom: 26,
            opacity: p * later, transform: `translateX(${(1 - p) * -30}px)`, filter: `blur(${(1 - p) * 8}px)`}}>
            <svg width={size * 0.95} height={size * 0.95} viewBox="0 0 40 40" style={{flex: 'none'}}>
              <circle cx={20} cy={20} r={17} fill="none" stroke="#1d1d1d" strokeWidth={4} />
              <path d="M11 21 L18 28 L30 13" fill="none" stroke={i === items.length - 1 ? C.red : '#1d1d1d'} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span style={{color: 'white', fontWeight: 600, fontSize: size * 0.86, letterSpacing: -0.03 * size, lineHeight: 1.15}}>
              {item.text}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const SceneView = ({scene, t, index, props}: {scene: KScene; t: number; index: number; props: KineticProps}) => {
  const dark = scene.bg === 'black';
  const sc = props.font.scale;
  const chars = scene.words.map((w) => w.text).join(' ').length;
  const base = Math.max(58, Math.min(112, 150 - chars * 1.9)) * sc;
  const life = (t - scene.start) / Math.max(0.5, scene.end - scene.start);
  const push = 1 + 0.07 * Math.min(1, Math.max(0, life));
  const drift = (index % 2 === 0 ? 1 : -1) * 0.6 * life;
  const punch = interpolate(t, [scene.start, scene.start + 0.18], [1.05, 1], clamp);

  // circle-wipe entrance
  const circle = scene.enter === 'circle'
    ? interpolate(t, [scene.start, scene.start + CIRCLE_IN], [0, 1], {...clamp, easing: (x) => 1 - Math.pow(1 - x, 3)})
    : 1;
  // tilt exit
  const tilt = scene.exit === 'tilt' ? interpolate(t, [scene.end - TILT_OUT, scene.end], [0, 1], clamp) : 0;

  const layout = scene.layout;
  const textBlock: React.CSSProperties =
    layout === 'objectLeft'
      ? {top: 560, left: 440, right: 70, textAlign: 'left'}
      : layout === 'objectBelow'
        ? {top: 380, left: 80, right: 80, textAlign: 'center'}
        : layout === 'circleHead'
          ? {top: 290, left: 250, right: 250, height: 480, textAlign: 'center'}
          : {top: 760, left: 80, right: 80, textAlign: 'center'};

  return (
    <AbsoluteFill
      style={{
        backgroundColor: dark ? C.black : C.cream,
        fontFamily: `'${props.font.family}', sans-serif`,
        clipPath: circle < 1 ? `circle(${circle * 125}% at 50% 50%)` : undefined,
      }}
    >
      <AbsoluteFill style={{transform: `scale(${push * punch}) rotate(${drift}deg)`}}>
        {dark ? (
          <AbsoluteFill style={{background: 'radial-gradient(ellipse 70% 50% at 50% 45%, rgba(60,10,12,0.55) 0%, transparent 70%)'}} />
        ) : (
          <>
            <Grid opacity={0.9} />
            <Barcode />
            <div style={{position: 'absolute', bottom: 300, left: 0, right: 0, textAlign: 'center', fontSize: 22,
              fontWeight: 600, letterSpacing: 6, color: C.grey}}>{props.badge}</div>
          </>
        )}
        {scene.arc ? <Arc t={t} start={scene.start} /> : null}

        {scene.object && layout === 'objectLeft' ? (
          <ObjectImg name={scene.object} dark={dark} t={t} start={scene.start} words={scene.words} grow={scene.grow}
            style={{left: -60, top: 300, width: 560, height: 760}} />
        ) : null}
        {scene.object && layout === 'objectBelow' ? (
          <ObjectImg name={scene.object} dark={dark} t={t} start={scene.start} words={scene.words} grow={scene.grow}
            style={{left: 190, top: 820, width: 700, height: 700}} />
        ) : null}
        {layout === 'circleHead' ? (
          <>
            {scene.object ? (
              <ObjectImg name={scene.object} dark t={t} start={scene.start} words={scene.words}
                style={{left: 165, top: 800, width: 750, height: 750, filter: 'contrast(1.1)'}} />
            ) : null}
            {/* halftone dot field, as in the reference's halftone figure */}
            <AbsoluteFill style={{
              backgroundImage: 'radial-gradient(rgba(255,255,255,0.22) 2.4px, transparent 2.8px)',
              backgroundSize: '14px 14px',
              maskImage: 'radial-gradient(ellipse 34% 22% at 50% 62%, black 0%, transparent 100%)',
              WebkitMaskImage: 'radial-gradient(ellipse 34% 22% at 50% 62%, black 0%, transparent 100%)',
            }} />
            <div style={{position: 'absolute', left: 200, top: 190, width: 680, height: 680, borderRadius: '50%', background: '#FAFAFA',
              boxShadow: '0 0 80px rgba(255,255,255,0.35)',
              transform: `scale(${spring({frame: Math.max(0, (t - scene.start) * 30), fps: 30, config: {damping: 13}})})`}} />
          </>
        ) : null}

        {layout === 'card' ? (
          <Card scene={scene} t={t} title={props.cardTitle} size={66 * sc} />
        ) : (
          <div
            style={{
              position: 'absolute',
              ...textBlock,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'baseline',
              justifyContent: textBlock.textAlign === 'left' ? 'flex-start' : 'center',
              alignContent: 'center',
              fontFamily: `'${props.font.family}', sans-serif`,
              transform: `translate(${tilt * 160}px, ${tilt * -120}px) rotate(${tilt * -16}deg)`,
              filter: tilt > 0 ? `blur(${tilt * 12}px)` : undefined,
              opacity: 1 - tilt * 0.9,
            }}
          >
            {scene.words.map((w, i) => (
              <KWord key={i} w={w} t={t} size={layout === 'circleHead' ? base * 0.95 : layout === 'objectLeft' ? base * 1.15 : base}
                dark={dark && layout !== 'circleHead'} align={textBlock.textAlign === 'left' ? 'left' : 'center'} />
            ))}
          </div>
        )}
      </AbsoluteFill>
      {circle > 0 && circle < 0.98 && scene.enter === 'circle' ? (() => {
        // clip-path circle(%) is relative to sqrt(w^2 + h^2) / sqrt(2)
        const r = circle * 1.25 * Math.sqrt((1080 ** 2 + 1920 ** 2) / 2);
        const ring = 16 * (1 - circle);
        return (
          <div style={{position: 'absolute', left: 540 - r, top: 960 - r, width: 2 * r, height: 2 * r, borderRadius: '50%',
            boxShadow: `inset 0 0 0 ${ring}px ${dark ? C.red : '#F3A6AE'}`, opacity: 1 - circle}} />
        );
      })() : null}
    </AbsoluteFill>
  );
};

const Final = ({props, t}: {props: KineticProps; t: number}) => {
  const {final} = props;
  const sc = props.font.scale;
  const local = t - final.start;
  const fade = interpolate(local, [0, 0.25], [0, 1], clamp);
  const endFade = interpolate(t, [props.canvas.durationInFrames / 30 - 0.35, props.canvas.durationInFrames / 30], [1, 0], clamp);
  let k = 0;
  return (
    <AbsoluteFill style={{backgroundColor: C.black, opacity: fade * endFade, fontFamily: `'${props.font.family}', sans-serif`}}>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 70% 45% at 50% 48%, rgba(70,8,12,0.6) 0%, transparent 70%)'}} />
      <ObjectImg name={final.object} dark t={t} start={final.start} words={[]}
        style={{left: 240, top: 170, width: 600, height: 600, opacity: 0.55}} />
      <div style={{position: 'absolute', top: 760, left: 60, right: 60, textAlign: 'center'}}>
        {final.lines.map((line, li) => (
          <div key={line} style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', marginBottom: 18}}>
            {line.split(' ').map((text) => {
              const start = final.start + 0.15 + li * 0.85 + (k++) * 0.12;
              return (
                <KWord key={text + li} w={{text, start, end: start + 0.3, key: final.key.includes(text)}} t={t}
                  size={104 * sc * props.font.finalScale} dark />
              );
            })}
          </div>
        ))}
      </div>
      <div style={{position: 'absolute', top: 1150, left: 0, right: 0, textAlign: 'center',
        opacity: interpolate(local, [1.5, 1.9], [0, 1], clamp)}}>
        <span style={{display: 'inline-block', padding: '12px 30px', border: `2px solid ${C.red}`, borderRadius: 999,
          color: 'white', fontWeight: 800, fontSize: 34 * Math.max(sc, 0.9), letterSpacing: 4 * sc, boxShadow: `0 0 26px ${C.red}66`}}>
          {final.verse.reference}
        </span>
      </div>
      <div style={{position: 'absolute', top: 1260, left: 120, right: 120, textAlign: 'center', color: 'rgba(255,255,255,0.72)',
        fontWeight: 600, fontSize: Math.max(34, 38 * sc), lineHeight: 1.45, opacity: interpolate(local, [1.9, 2.4], [0, 1], clamp)}}>
        {final.verse.text}
      </div>
    </AbsoluteFill>
  );
};

export const KineticShort = (props: KineticProps) => {
  useFonts(props.font);
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const scenes = props.scenes;
  return (
    <AbsoluteFill style={{backgroundColor: C.black}}>
      {scenes.map((scene, i) => {
        const next = scenes[i + 1];
        // keep this scene under the next one while the next circle-wipes in
        const until = next && next.enter === 'circle' ? scene.end + CIRCLE_IN : scene.end;
        if (t < scene.start || t >= until) return null;
        return <SceneView key={i} scene={scene} t={t} index={i} props={props} />;
      })}
      {t >= props.final.start ? <Final props={props} t={t} /> : null}
    </AbsoluteFill>
  );
};
