import React, {useEffect, useState} from 'react';
import {AbsoluteFill, useDelayRender} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
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

export const Promo: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Loading local fonts'));
  useEffect(() => {
    ensureFonts().then(() => continueRender(handle)).catch((err) => cancelRender(err));
  }, [handle, continueRender, cancelRender]);

  const scenes = timeline.scenes;
  return (
    <AbsoluteFill style={{backgroundColor: '#140A2A'}}>
      <TransitionSeries>
        {scenes.flatMap((s, i) => {
          const nodes = [
            <TransitionSeries.Sequence key={s.id} name={`${s.id} · ${s.type}`} durationInFrames={s.durationInFrames}>
              <SceneShell scene={s} />
            </TransitionSeries.Sequence>,
          ];
          const tr = s.transition;
          if (i < scenes.length - 1 && tr && tr.type !== 'cut' && tr.durationInFrames > 0) {
            nodes.push(
              <TransitionSeries.Transition key={`${s.id}-tr`} presentation={presentationFor(tr.type)}
                timing={linearTiming({durationInFrames: tr.durationInFrames})} />,
            );
          }
          return nodes;
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
};
