import React from 'react';
import {Composition} from 'remotion';
import {Promo} from './Promo';
import {Cinematic, type CineTimeline} from './Cinematic';
import type {Timeline} from './types';
import demo from './demo-timeline.json';

const EMPTY_CINE: CineTimeline = {
  meta: {title: 'empty', width: 1920, height: 1080, fps: 30, durationInFrames: 30, composition: 'Cinematic'},
  shots: [], captions: [], cards: [],
};

// Rendering: scripts/render.py picks the composition from timeline.meta.composition ("Promo" when absent).
// Promo     — lavender-luxe motion-graphics promos (scripts/timeline.py compiles its timeline).
// Cinematic — live-action edits with real-edit transitions and Telugu subtitles (telugu-cinematic-edit/scripts/recreate.py).
export const Root: React.FC = () => (
  <>
    <Composition
      id="Promo"
      component={Promo as unknown as React.FC<Record<string, unknown>>}
      defaultProps={{timeline: demo as unknown as Timeline}}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={300}
      calculateMetadata={({props}) => {
        const t = (props as unknown as {timeline: Timeline}).timeline;
        return {width: t.meta.width, height: t.meta.height, fps: t.meta.fps, durationInFrames: t.meta.durationInFrames};
      }}
    />
    <Composition
      id="Cinematic"
      component={Cinematic as unknown as React.FC<Record<string, unknown>>}
      defaultProps={{timeline: EMPTY_CINE}}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={30}
      calculateMetadata={({props}) => {
        const t = (props as unknown as {timeline: CineTimeline}).timeline;
        return {width: t.meta.width, height: t.meta.height, fps: t.meta.fps, durationInFrames: t.meta.durationInFrames};
      }}
    />
  </>
);
