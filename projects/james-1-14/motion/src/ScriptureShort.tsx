import {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Img,
  continueRender,
  delayRender,
  interpolate,
  random,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {cosine, segmentProgress} from './animation';
import type {FontSpec, ScriptureProps, Scene} from './scriptureTypes';

const XFADE = 0.8; // seconds of cross-dissolve between scene plates

const useFonts = (fonts: FontSpec[]) => {
  const [handle] = useState(() => delayRender('Loading fonts'));
  useEffect(() => {
    const faces = fonts.flatMap((font) =>
      font.files.map(
        (file) =>
          new FontFace(font.family, `url(${staticFile(file.src)}) format('woff2')`, {
            weight: file.weight,
            style: file.style,
          }),
      ),
    );
    Promise.all(faces.map((face) => face.load()))
      .then((loaded) => {
        loaded.forEach((face) => document.fonts.add(face));
        return document.fonts.ready;
      })
      .then(() => continueRender(handle))
      .catch((err) => {
        console.error(err);
        // Fail loudly rather than silently rendering fallback glyphs.
        throw err;
      });
  }, [fonts, handle]);
};

/** 0→1→0 visibility for an interval with soft edges, in seconds. */
const window01 = (t: number, start: number, end: number, fadeIn: number, fadeOut: number) =>
  Math.min(
    interpolate(t, [start, start + fadeIn], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: cosine}),
    interpolate(t, [end - fadeOut, end], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: cosine}),
  );

const Plate = ({scene, t, index, total}: {scene: Scene; t: number; index: number; total: number}) => {
  const first = index === 0;
  const last = index === total - 1;
  const opacity = window01(t, first ? -1 : scene.start - XFADE / 2, last ? 1e9 : scene.end + XFADE / 2, XFADE, XFADE);
  if (opacity <= 0) return null;
  const span = scene.end - scene.start + XFADE;
  const p = Math.min(Math.max((t - scene.start + XFADE / 2) / span, 0), 1);
  // Alternate gentle push-ins and drifts so consecutive scenes don't move identically.
  const scale = interpolate(p, [0, 1], index % 2 === 0 ? [1.04, 1.13] : [1.13, 1.05]);
  const driftY = interpolate(p, [0, 1], index % 2 === 0 ? [10, -24] : [-16, 14]);
  return (
    <AbsoluteFill style={{opacity}}>
      <Img
        src={staticFile(scene.image)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `translateY(${driftY}px) scale(${scale})`,
        }}
      />
    </AbsoluteFill>
  );
};

const Grade = ({palette}: Pick<ScriptureProps, 'palette'>) => (
  <>
    {/* Lavender tint and depth: keeps every plate in one color world. */}
    <AbsoluteFill style={{background: palette.lavender, mixBlendMode: 'soft-light', opacity: 0.55}} />
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${palette.deep}d9 0%, ${palette.deep}33 26%, ${palette.deep}22 52%, ${palette.deep}b3 78%, ${palette.deep}f0 100%)`,
      }}
    />
    <AbsoluteFill
      style={{background: `radial-gradient(ellipse 85% 60% at 50% 45%, transparent 40%, ${palette.deep}cc 100%)`}}
    />
    <AbsoluteFill
      style={{background: `radial-gradient(ellipse 80% 17% at 50% 39%, ${palette.deep}a6 0%, ${palette.deep}59 55%, transparent 100%)`}}
    />
  </>
);

const Motes = ({t, palette}: {t: number; palette: ScriptureProps['palette']}) => {
  const motes = Array.from({length: 26}, (_, i) => {
    const x = random(`x${i}`) * 1080;
    const speed = 14 + random(`s${i}`) * 26;
    const size = 4 + random(`r${i}`) * 14;
    const y = 1920 - ((random(`y${i}`) * 2100 + t * speed) % 2100);
    const sway = Math.sin(t * 0.6 + i) * 18;
    const twinkle = 0.25 + 0.35 * (0.5 + 0.5 * Math.sin(t * 1.3 + i * 2.1));
    return (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: x + sway,
          top: y,
          width: size,
          height: size,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${palette.glow} 0%, ${palette.glow}00 70%)`,
          opacity: twinkle,
        }}
      />
    );
  });
  return <AbsoluteFill style={{mixBlendMode: 'screen'}}>{motes}</AbsoluteFill>;
};

const Ornament = ({width, color, progress}: {width: number; color: string; progress: number}) => (
  <svg width={width} height={22} viewBox={`0 0 ${width} 22`} style={{display: 'block', margin: '0 auto'}}>
    <line x1={width / 2 - 14} y1={11} x2={width / 2 - 14 - (width / 2 - 20) * progress} y2={11} stroke={color} strokeWidth={1.6} />
    <line x1={width / 2 + 14} y1={11} x2={width / 2 + 14 + (width / 2 - 20) * progress} y2={11} stroke={color} strokeWidth={1.6} />
    <path d={`M ${width / 2} 3 L ${width / 2 + 7} 11 L ${width / 2} 19 L ${width / 2 - 7} 11 Z`} fill="none" stroke={color} strokeWidth={1.6} opacity={progress} />
  </svg>
);

const textGlow = (palette: ScriptureProps['palette']) =>
  `0 0 28px ${palette.plum}cc, 0 2px 10px rgba(10, 4, 24, 0.75)`;

export const ScriptureShort = (props: ScriptureProps) => {
  const {font, accentFont, palette, scenes, cues, steps, verse, final, series} = props;
  useFonts([font, accentFont]);
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const duration = durationInFrames / fps;

  const current = scenes.find((s) => t >= s.start && t < s.end) ?? scenes[scenes.length - 1];
  const stepScene = scenes.find((s) => s.id === 's5_light');
  const verseScene = scenes.find((s) => s.id === 's6_bible');
  const cue = cues.find((c) => t >= c.start - 0.12 && t <= c.end + 0.12);
  const finalIn = segmentProgress(frame, Math.round(final.start * fps), Math.round((final.start + 1.1) * fps));
  const endFade = interpolate(t, [duration - 0.5, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const introFade = interpolate(t, [0, 0.6], [0, 1], {extrapolateRight: 'clamp'});

  const base = {fontFamily: `'${font.family}', serif`, color: palette.ink, textAlign: 'center' as const};

  return (
    <AbsoluteFill style={{backgroundColor: palette.deep}}>
      <AbsoluteFill style={{opacity: introFade * endFade}}>
        {scenes.map((scene, i) => (
          <Plate key={scene.id} scene={scene} t={t} index={i} total={scenes.length} />
        ))}
        <Grade palette={palette} />
        <Motes t={t} palette={palette} />

        {/* Series label: small letterspaced caps, like a devotional series tag. */}
        <div
          style={{
            position: 'absolute',
            top: 250,
            width: '100%',
            fontFamily: `'${accentFont.family}', '${font.family}', serif`,
            fontSize: props.language === 'en' ? 30 : 34,
            letterSpacing: props.language === 'en' ? 8 : 1,
            textTransform: props.language === 'en' ? 'uppercase' : 'none',
            color: palette.lilac,
            textAlign: 'center',
            opacity: 0.9 * (1 - finalIn),
            textShadow: textGlow(palette),
                textWrap: 'balance',
          }}
        >
          {series}
          <div style={{marginTop: 14}}>
            <Ornament width={220} color={palette.lilac} progress={segmentProgress(frame, 6, 36)} />
          </div>
        </div>

        {/* Scene headline */}
        {scenes.map((scene) => {
          if (!scene.headline) return null;
          const v = window01(t, scene.start + 0.25, scene.end - 0.05, 0.7, 0.45);
          if (v <= 0) return null;
          const rise = interpolate(v, [0, 1], [26, 0]);
          return (
            <div
              key={scene.id}
              style={{
                ...base,
                position: 'absolute',
                top: 640,
                left: 90,
                right: 90,
                fontSize: font.headlineSize,
                fontWeight: 600,
                fontStyle: props.language === 'en' ? 'italic' : 'normal',
                lineHeight: font.lineHeight,
                letterSpacing: font.letterSpacing,
                opacity: v,
                transform: `translateY(${rise}px)`,
                textShadow: textGlow(palette),
                textWrap: 'balance',
              }}
            >
              {scene.headline}
            </div>
          );
        })}

        {/* Three-step call: each step lands on its spoken word. */}
        {stepScene
          ? steps.map((step, i) => {
              const inP = segmentProgress(frame, Math.round(step.start * fps - 4), Math.round(step.start * fps + 14));
              const outP = window01(t, stepScene.start, stepScene.end - 0.05, 0.01, 0.45);
              const later = steps[i + 1] && t > steps[i + 1].start ? 0.62 : 1;
              const v = inP * outP;
              if (v <= 0) return null;
              return (
                <div
                  key={step.text}
                  style={{
                    ...base,
                    position: 'absolute',
                    top: 560 + i * (font.headlineSize * 1.55),
                    left: 70,
                    right: 70,
                    fontSize: font.headlineSize * (i === 1 ? 1.08 : 0.98),
                    fontWeight: 600,
                    fontStyle: props.language === 'en' && i === 1 ? 'italic' : 'normal',
                    lineHeight: font.lineHeight,
                    opacity: v * later,
                    transform: `translateY(${interpolate(inP, [0, 1], [22, 0])}px)`,
                    textShadow: textGlow(palette),
                textWrap: 'balance',
                  }}
                >
                  {step.text}
                </div>
              );
            })
          : null}

        {/* Scripture card */}
        {verseScene
          ? (() => {
              const v = window01(t, verse.start, verseScene.end - 0.05, 0.9, 0.5);
              if (v <= 0) return null;
              return (
                <div
                  style={{
                    position: 'absolute',
                    top: 470,
                    left: 96,
                    right: 96,
                    padding: '56px 54px 50px',
                    borderRadius: 28,
                    background: `linear-gradient(180deg, ${palette.deep}8c, ${palette.plum}73)`,
                    border: `1.5px solid ${palette.lilac}66`,
                    boxShadow: `0 30px 80px ${palette.deep}99`,
                    opacity: v,
                    transform: `translateY(${interpolate(v, [0, 1], [20, 0])}px)`,
                  }}
                >
                  <div
                    style={{
                      ...base,
                      fontSize: font.verseSize,
                      fontStyle: props.language === 'en' ? 'italic' : 'normal',
                      fontWeight: 500,
                      lineHeight: font.lineHeight + 0.08,
                      textShadow: textGlow(palette),
                textWrap: 'balance',
                    }}
                  >
                    {verse.text}
                  </div>
                  <div style={{marginTop: 34}}>
                    <Ornament width={200} color={palette.lilac} progress={v} />
                  </div>
                  <div
                    style={{
                      ...base,
                      marginTop: 18,
                      fontSize: 40,
                      fontWeight: 600,
                      letterSpacing: props.language === 'en' ? 4 : 0.5,
                      color: palette.lilac,
                    }}
                  >
                    {verse.reference}
                  </div>
                </div>
              );
            })()
          : null}

        {/* Final message */}
        {finalIn > 0 ? (
          <div style={{position: 'absolute', top: 1090, left: 70, right: 70, opacity: finalIn, padding: '30px 0', background: `radial-gradient(ellipse 60% 55% at 50% 50%, ${palette.deep}99 0%, transparent 100%)`}}>
            {final.lines.map((line, i) => {
              const p = segmentProgress(frame, Math.round((final.start + i * 0.55) * fps), Math.round((final.start + i * 0.55 + 0.9) * fps));
              return (
                <div
                  key={line}
                  style={{
                    ...base,
                    fontSize: font.finalSize,
                    fontWeight: 600,
                    fontStyle: props.language === 'en' && i === 1 ? 'italic' : 'normal',
                    lineHeight: font.lineHeight,
                    opacity: p,
                    transform: `translateY(${interpolate(p, [0, 1], [24, 0])}px)`,
                    textShadow: textGlow(palette),
                textWrap: 'balance',
                    marginBottom: 18,
                  }}
                >
                  {line}
                </div>
              );
            })}
            <div style={{marginTop: 28, opacity: segmentProgress(frame, Math.round((final.start + 1.2) * fps), Math.round((final.start + 2) * fps))}}>
              <Ornament width={260} color={palette.lilac} progress={1} />
              <div
                style={{
                  ...base,
                  marginTop: 18,
                  fontSize: 40,
                  fontWeight: 600,
                  letterSpacing: props.language === 'en' ? 4 : 0.5,
                  color: palette.lilac,
                }}
              >
                {final.reference}
              </div>
            </div>
          </div>
        ) : null}

        {/* Subtitles: inside the 9:16 safe area, above platform UI. */}
        {cue ? (
          <div
            style={{
              position: 'absolute',
              top: 1330,
              left: 80,
              right: 120,
              display: 'flex',
              justifyContent: 'center',
              opacity: window01(t, cue.start - 0.12, cue.end + 0.12, 0.12, 0.12),
            }}
          >
            <div
              style={{
                ...base,
                fontSize: font.subtitleSize,
                fontWeight: 500,
                lineHeight: font.lineHeight + 0.06,
                padding: '14px 30px 16px',
                borderRadius: 18,
                background: `${palette.deep}a6`,
                boxShadow: `0 10px 30px ${palette.deep}66`,
                textShadow: '0 2px 6px rgba(10,4,24,0.8)',
                maxWidth: 880,
                textWrap: 'balance',
              }}
            >
              {cue.text}
            </div>
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
