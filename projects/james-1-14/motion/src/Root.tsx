import type {CalculateMetadataFunction} from 'remotion';
import {Composition} from 'remotion';
import {Edit} from './Edit';
import type {EditProps} from './types';
import {ScriptureShort} from './ScriptureShort';
import type {ScriptureProps} from './scriptureTypes';
import scriptureDefaults from '../props/en.json';
import {KineticShort} from './KineticShort';
import type {KineticProps} from './KineticShort';
import kineticDefaults from '../props/en-kinetic.json';

const defaultProps: EditProps = {
  canvas: {
    width: 1920,
    height: 1080,
    fps: 30,
    durationInFrames: 150,
    background: '#10131a',
  },
  media: {},
  title: 'A reusable motion layer',
  subtitle: 'React layout, SVG animation, local media, and alpha output',
  accent: '#72E6C1',
  transparent: false,
};

const calculateMetadata: CalculateMetadataFunction<EditProps> = ({props}) => {
  return {
    width: props.canvas.width,
    height: props.canvas.height,
    fps: props.canvas.fps,
    durationInFrames: props.canvas.durationInFrames,
  };
};

const scriptureMetadata: CalculateMetadataFunction<ScriptureProps> = ({props}) => ({
  width: props.canvas.width,
  height: props.canvas.height,
  fps: props.canvas.fps,
  durationInFrames: props.canvas.durationInFrames,
});

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="VideoEdit"
        component={Edit}
        durationInFrames={defaultProps.canvas.durationInFrames}
        fps={defaultProps.canvas.fps}
        width={defaultProps.canvas.width}
        height={defaultProps.canvas.height}
        defaultProps={defaultProps}
        calculateMetadata={calculateMetadata}
      />
      <Composition
        id="MotionOverlay"
        component={Edit}
        durationInFrames={defaultProps.canvas.durationInFrames}
        fps={defaultProps.canvas.fps}
        width={defaultProps.canvas.width}
        height={defaultProps.canvas.height}
        defaultProps={{...defaultProps, transparent: true}}
        calculateMetadata={calculateMetadata}
      />
      <Composition
        id="ScriptureShort"
        component={ScriptureShort}
        durationInFrames={900}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={scriptureDefaults as ScriptureProps}
        calculateMetadata={scriptureMetadata}
      />
      <Composition
        id="KineticShort"
        component={KineticShort}
        durationInFrames={900}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={kineticDefaults as KineticProps}
        calculateMetadata={({props}) => ({
          width: props.canvas.width,
          height: props.canvas.height,
          fps: props.canvas.fps,
          durationInFrames: props.canvas.durationInFrames,
        })}
      />
    </>
  );
};
