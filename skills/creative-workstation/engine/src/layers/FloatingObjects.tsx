import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {FloatingObject} from '../types';
import {BLUR, TIMING} from '../theme';
import {enter, unit} from '../anim';
import {Sprite} from './Sprite';

/**
 * Layered floating objects with depth: far objects are small, blurred and slow; foreground
 * objects are large, blurred (shallow depth of field) and move fastest across the frame.
 */
export const FloatingObjects: React.FC<{items?: FloatingObject[]; layer: 'back' | 'front'}> = ({items, layer}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const u = unit(height);
  if (!items?.length) return null;
  const t = frame / fps;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {items
        .filter((o) => ((o.depth ?? 1) >= 2 ? 'front' : 'back') === layer)
        .map((o, i) => {
          const depth = o.depth ?? 1;
          const startF = (o.delay ?? 0) * fps;
          const p = enter(frame, startF, TIMING.floatIn * (fps / 30));
          const speed = depth === 0 ? 0.5 : depth === 1 ? 1 : 1.8;
          const [dx, dy] = o.drift ?? [0, 0];
          const bob = (o.bob ?? 14) * u * Math.sin(t * 1.1 + i * 1.7);
          const size = o.size * u;
          const x = (o.x / 100) * width + dx * u * t * speed;
          const y = (o.y / 100) * height + dy * u * t * speed + bob + (1 - p) * 40 * u;
          const blur = depth === 0 ? BLUR.far : depth >= 2 ? BLUR.near : 0;
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: x,
                top: y,
                translate: '-50% -50%',
                rotate: `${(o.rotate ?? 0) * t}deg`,
                opacity: p * (o.opacity ?? 1),
                filter: blur ? `blur(${blur * u}px)` : undefined,
              }}
            >
              {o.shadow !== false && depth === 1 ? (
                // cheap contact shadow (gradient) instead of a per-frame drop-shadow filter
                <div style={{position: 'absolute', left: '15%', right: '15%', bottom: '13%', height: size * 0.07, borderRadius: '50%',
                  background: 'radial-gradient(closest-side, rgba(20,10,42,0.30), transparent)'}} />
              ) : null}
              <Sprite src={o.sprite} height={size} />
            </div>
          );
        })}
    </AbsoluteFill>
  );
};
