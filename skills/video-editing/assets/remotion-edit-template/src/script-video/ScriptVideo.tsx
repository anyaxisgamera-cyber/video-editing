import {createTikTokStyleCaptions} from '@remotion/captions';
import type {TikTokPage} from '@remotion/captions';
import {loadFont} from '@remotion/fonts';
import {Audio, Video} from '@remotion/media';
import {useEffect, useMemo, useState} from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useDelayRender,
  useVideoConfig,
} from 'remotion';
import type {ScriptScene, ScriptVideoProps, SceneMedia, SceneMove} from './types';

// Script-driven composition: scenes, narration, captions, music and effects all placed from one timing map
// (scripts/production.py). The same component renders every language, 9:16 or 16:9, 1080p or 4K.

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** Load the language's font file (from props) before any frame renders. */
const useLanguageFont = (family: string, src: string | null) => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => (src ? delayRender(`Loading font ${family}`) : null));
  useEffect(() => {
    if (!src || handle === null) return;
    loadFont({family, url: staticFile(src)})
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
  }, [family, src, handle, continueRender, cancelRender]);
};

const moveTransform = (move: SceneMove, progress: number): string => {
  const p = Easing.inOut(Easing.sin)(progress);
  const a = move.amount;
  switch (move.type) {
    case 'push_in':
      return `scale(${1 + a * p})`;
    case 'pull_out':
      return `scale(${1 + a * (1 - p)})`;
    case 'pan_right': // camera pans right: content moves left
      return `scale(${1 + a}) translateX(${((a / 2 - a * p) * 100) / (1 + a)}%)`;
    case 'pan_left':
      return `scale(${1 + a}) translateX(${((-a / 2 + a * p) * 100) / (1 + a)}%)`;
    case 'tilt_up': // camera tilts up: content moves down
      return `scale(${1 + a}) translateY(${((-a / 2 + a * p) * 100) / (1 + a)}%)`;
    case 'tilt_down':
      return `scale(${1 + a}) translateY(${((a / 2 - a * p) * 100) / (1 + a)}%)`;
    default:
      return 'none';
  }
};

/**
 * Cover-crop around a focus point. The media box keeps the source aspect ratio and is offset so that the focus
 * point stays in frame in both 9:16 and 16:9. Falls back to centred objectFit when the source size is unknown.
 */
const MediaLayer: React.FC<{media: SceneMedia}> = ({media}) => {
  const {width, height} = useVideoConfig();
  if (media.kind === 'none' || !media.src) return null;
  const src = staticFile(media.src);
  let box: React.CSSProperties = {position: 'absolute', inset: 0, width: '100%', height: '100%'};
  if (media.width && media.height && media.fit === 'cover') {
    const s = Math.max(width / media.width, height / media.height);
    const w = media.width * s;
    const h = media.height * s;
    box = {position: 'absolute', width: w, height: h, left: (width - w) * media.focusX, top: (height - h) * media.focusY};
  }
  const fit = media.width && media.height && media.fit === 'cover' ? 'fill' : media.fit;
  return (
    <div style={box}>
      {media.kind === 'video' ? (
        <Video src={src} muted objectFit={fit} trimBefore={media.trimBefore} playbackRate={media.playbackRate}
          style={{width: '100%', height: '100%'}} />
      ) : (
        <Img src={src} style={{width: '100%', height: '100%', objectFit: fit}} />
      )}
    </div>
  );
};

const SceneView: React.FC<{scene: ScriptScene}> = ({scene}) => {
  const frame = useCurrentFrame(); // scene-relative inside <Sequence>
  const t = scene.transitionIn;
  const opacity = t.type === 'cut' || t.durationInFrames <= 0 ? 1 : interpolate(frame, [0, t.durationInFrames], [0, 1], clamp);
  const progress = scene.durationInFrames > 1 ? frame / (scene.durationInFrames - 1) : 0;
  const origin = `${scene.media.focusX * 100}% ${scene.media.focusY * 100}%`;
  return (
    <AbsoluteFill style={{opacity, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: moveTransform(scene.move, progress), transformOrigin: origin}}>
        <MediaLayer media={scene.media} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const OnScreenText: React.FC<{text: string; durationInFrames: number} & Pick<ScriptVideoProps, 'language' | 'onScreenStyle'>> = ({
  text, durationInFrames, language, onScreenStyle,
}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const k = Math.max(1, Math.round(0.35 * fps));
  const opacity = Math.min(interpolate(frame, [0, k], [0, 1], clamp), interpolate(frame, [durationInFrames - k, durationInFrames], [1, 0], clamp));
  const rise = interpolate(frame, [0, k], [height * 0.012, 0], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: height * onScreenStyle.top}}>
      <div style={{
        maxWidth: '84%', textAlign: 'center', direction: language.direction, fontFamily: language.fontFamily,
        fontSize: onScreenStyle.fontSize, fontWeight: 700, lineHeight: 1.3, color: '#FFFFFF', opacity,
        transform: `translateY(${rise}px)`, textShadow: '0 2px 18px rgba(0,0,0,0.55)',
      }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};

const CaptionLayer: React.FC<Pick<ScriptVideoProps, 'captionTracks' | 'captionStyle' | 'language'>> = ({captionTracks, captionStyle, language}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  // pages are built per scene so a page never spans a cut
  const pages = useMemo<TikTokPage[]>(
    () =>
      captionTracks.flatMap((t) =>
        createTikTokStyleCaptions({captions: t.captions, combineTokensWithinMilliseconds: captionStyle.combineTokensWithinMilliseconds}).pages),
    [captionTracks, captionStyle.combineTokensWithinMilliseconds],
  );
  const ms = (frame / fps) * 1000;
  const page = pages.find((p, i) => ms >= p.startMs && ms < Math.min(p.startMs + p.durationMs + 250, pages[i + 1]?.startMs ?? Infinity));
  if (!page) return null;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: height * captionStyle.bottom}}>
      <div style={{
        maxWidth: `${captionStyle.maxWidth * 100}%`, textAlign: 'center', direction: language.direction, whiteSpace: 'pre-wrap',
        fontFamily: language.fontFamily, fontSize: captionStyle.fontSize, fontWeight: 600, lineHeight: 1.35, color: '#FFFFFF',
        textShadow: '0 2px 4px rgba(0,0,0,0.85), 0 0 14px rgba(0,0,0,0.6)',
      }}>
        {page.tokens.map((tok, i) => {
          const active = captionStyle.highlightActiveWord && ms >= tok.fromMs && ms < tok.toMs;
          return (
            <span key={`${tok.fromMs}-${i}`} style={{color: active ? '#FFE27A' : '#FFFFFF'}}>
              {tok.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Music bed with the ducking keyframes computed from measured narration (numeric volume via interpolate()). */
const MusicTrack: React.FC<{music: NonNullable<ScriptVideoProps['music']>}> = ({music}) => {
  const frame = useCurrentFrame();
  const frames = music.keyframes.map((k) => k[0]);
  const volumes = music.keyframes.map((k) => k[1]);
  const volume = frames.length > 1 ? interpolate(frame, frames, volumes, clamp) : volumes[0] ?? 0;
  return <Audio src={staticFile(music.src)} volume={volume} loop={music.loop} />;
};

export const ScriptVideo: React.FC<ScriptVideoProps> = (props) => {
  useLanguageFont(props.language.fontFamily, props.language.fontSrc);
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{backgroundColor: props.canvas.background}}>
      {props.scenes.map((s) =>
        frame >= s.from && frame < s.from + s.durationInFrames ? (
          <Sequence key={s.id} name={`scene ${s.id}`} from={s.from} durationInFrames={s.durationInFrames} layout="absolute-fill">
            <SceneView scene={s} />
          </Sequence>
        ) : null,
      )}
      {props.scenes.map((s) =>
        s.onScreen ? (
          <Sequence key={`text-${s.id}`} name={`text ${s.id}`} from={s.onScreen.from} durationInFrames={s.onScreen.durationInFrames} layout="absolute-fill">
            <OnScreenText text={s.onScreen.text} durationInFrames={s.onScreen.durationInFrames} language={props.language}
              onScreenStyle={props.onScreenStyle} />
          </Sequence>
        ) : null,
      )}
      <CaptionLayer captionTracks={props.captionTracks} captionStyle={props.captionStyle} language={props.language} />
      {props.narration.map((n) => (
        <Sequence key={`vo-${n.id}`} name={`narration ${n.id}`} from={n.from} durationInFrames={n.durationInFrames} layout="none">
          <Audio src={staticFile(n.src)} />
        </Sequence>
      ))}
      {props.sfx.map((x, i) => (
        <Sequence key={`sfx-${i}`} name={`sfx ${i}`} from={x.from} layout="none">
          <Audio src={staticFile(x.src)} volume={x.volume} />
        </Sequence>
      ))}
      {props.music ? <MusicTrack music={props.music} /> : null}
    </AbsoluteFill>
  );
};
