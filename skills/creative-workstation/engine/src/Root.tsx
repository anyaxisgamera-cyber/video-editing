import React from 'react';
import {Composition} from 'remotion';
import {Promo} from './Promo';
import type {Timeline} from './types';
import demo from './demo-timeline.json';

// Rendering: `npx remotion render src/index.ts Promo out.mp4 --props=<project>/timeline.json --public-dir=<project>/public`
// The timeline is compiled by scripts/timeline.py; width/height/fps/duration come from it.
export const Root: React.FC = () => (
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
);
