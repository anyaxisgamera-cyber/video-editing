import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Sequence, interpolate, useCurrentFrame, useDelayRender} from 'remotion';
import type {SceneBase, Timeline} from './types';
import {LuxeBackground} from './layers/LuxeBackground';
import {FloatingObjects} from './layers/FloatingObjects';
import {SCENES} from './scenes/Scenes';
import {presentationFor} from './transitions';
import {ensureFonts} from './fonts';

/** One scene = background → far/mid floating objects → scene content → foreground objects. */
const SceneShell: React.FC<{scene: SceneBase}> = ({scene}) => {
  const Comp = SCENES[scene.type];
  return (
    <AbsoluteFill>
      <LuxeBackground bg={scene.background} seed={scene.id} />
      <FloatingObjects items={scene.floating} layer="back" />
      {Comp ? <Comp scene={scene} /> : <AbsoluteFill style={{color: 'red', fontSize: 60}}>Unknown scene type: {scene.type}</AbsoluteFill>}
      <FloatingObjects items={scene.floating} layer="front" />
    </AbsoluteFill>
  );
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
// Only HTML-in-canvas presentations use these callbacks; ours (and @remotion/transitions' slide) do not.
const noop = () => undefined;
const activeTransition = (s?: SceneBase) =>
  s?.transition && s.transition.type !== 'cut' && s.transition.durationInFrames > 0 ? s.transition : null;

/**
 * Applies the entering presentation (transition from the previous scene) during the first T_in frames and the
 * exiting presentation (transition into the next scene) during the last T_out frames, with the same linear
 * progress <TransitionSeries> uses — so the output is identical, but the tree is flat.
 */
const WithTransitions: React.FC<{scene: SceneBase; prev?: SceneBase; isLast: boolean; children: React.ReactNode}> = ({
  scene, prev, isLast, children,
}) => {
  const f = useCurrentFrame(); // scene-relative (inside <Sequence>)
  const tin = activeTransition(prev);
  const tout = isLast ? null : activeTransition(scene);
  let node = <>{children}</>;
  const entering = Boolean(tin && f < tin.durationInFrames);
  const exiting = Boolean(tout && f >= scene.durationInFrames - (tout?.durationInFrames ?? 0));
  const both = entering && exiting;
  if (tin && entering) {
    const pres = presentationFor(tin.type);
    const P = pres.component;
    node = (
      <P presentationDirection="entering" presentationProgress={interpolate(f, [0, tin.durationInFrames], [0, 1], clamp)}
        passedProps={pres.props} presentationDurationInFrames={tin.durationInFrames}
        onElementImage={noop} onUnmount={noop} bothEnteringAndExiting={both}>
        {node}
      </P>
    );
  }
  if (tout && exiting) {
    const pres = presentationFor(tout.type);
    const P = pres.component;
    const start = scene.durationInFrames - tout.durationInFrames;
    node = (
      <P presentationDirection="exiting" presentationProgress={interpolate(f, [start, scene.durationInFrames], [0, 1], clamp)}
        passedProps={pres.props} presentationDurationInFrames={tout.durationInFrames}
        onElementImage={noop} onUnmount={noop} bothEnteringAndExiting={both}>
        {node}
      </P>
    );
  }
  return <AbsoluteFill>{node}</AbsoluteFill>;
};

/**
 * Flat scene renderer. <TransitionSeries> nests every sequence inside the previous one
 * (renderSequenceAndRest), so a 588-scene, 60-minute timeline built a fiber tree hundreds of levels deep and
 * React's commit phase overflowed the call stack ("Maximum call stack size exceeded") at minute ~58.
 * Here every scene is a sibling <Sequence> at its compiled absolute `from` (timeline.py computes it exactly as
 * TransitionSeries would), and only the scenes active on the current frame are mounted — constant tree depth
 * and constant per-frame work for any duration. Later scenes are drawn on top, as in TransitionSeries.
 */
const Scenes: React.FC<{scenes: SceneBase[]}> = ({scenes}) => {
  const frame = useCurrentFrame();
  const out: React.ReactNode[] = [];
  for (let i = 0; i < scenes.length; i++) {
    const s = scenes[i];
    if (frame < s.from || frame >= s.from + s.durationInFrames) continue;
    out.push(
      <Sequence key={s.id} name={`${s.id} · ${s.type}`} from={s.from} durationInFrames={s.durationInFrames} layout="absolute-fill">
        <WithTransitions scene={s} prev={scenes[i - 1]} isLast={i === scenes.length - 1}>
          <SceneShell scene={s} />
        </WithTransitions>
      </Sequence>,
    );
  }
  return <>{out}</>;
};

export const Promo: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Loading local fonts'));
  useEffect(() => {
    ensureFonts().then(() => continueRender(handle)).catch((err) => cancelRender(err));
  }, [handle, continueRender, cancelRender]);

  return (
    <AbsoluteFill style={{backgroundColor: '#140A2A'}}>
      <Scenes scenes={timeline.scenes} />
    </AbsoluteFill>
  );
};
