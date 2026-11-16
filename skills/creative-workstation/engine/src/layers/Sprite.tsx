import React from 'react';
import {Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {SpriteSource} from '../types';

const pad = (n: number) => String(n).padStart(4, '0');

/**
 * A transparent PNG, or a looping PNG sequence (Blender turntable) played back at any speed.
 * Adjacent sequence frames are cross-faded by the fractional position so slow rotations
 * stay smooth even though the turntable only has 72 frames (5° steps).
 */
export const Sprite: React.FC<{src: SpriteSource; height: number; style?: React.CSSProperties}> = ({src, height, style}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (src.kind === 'image') {
    return <Img src={staticFile(src.src)} style={{height, width: 'auto', display: 'block', ...style}} />;
  }
  const rev = src.revolutionSeconds ?? 10;
  const pos = ((frame / fps) / rev) * src.frames + (src.startOffset ?? 0);
  const i0 = ((Math.floor(pos) % src.frames) + src.frames) % src.frames;
  const i1 = (i0 + 1) % src.frames;
  const frac = pos - Math.floor(pos);
  const file = (i: number) => staticFile(`${src.dir}/${(src.pattern ?? 'f_%04d.png').replace('%04d', pad(i))}`);
  const aspect = 0.75; // turntables are rendered 600x800
  return (
    <div style={{position: 'relative', height, width: height * aspect, ...style}}>
      <Img src={file(i0)} style={{position: 'absolute', inset: 0, height: '100%', width: '100%'}} />
      <Img src={file(i1)} style={{position: 'absolute', inset: 0, height: '100%', width: '100%', opacity: frac}} />
    </div>
  );
};
