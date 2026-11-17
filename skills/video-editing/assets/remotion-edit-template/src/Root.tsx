import type {CalculateMetadataFunction} from 'remotion';
import {Composition} from 'remotion';
import {Edit} from './Edit';
import type {EditProps} from './types';
import {ScriptVideo} from './script-video/ScriptVideo';
import type {ScriptVideoProps} from './script-video/types';
import scriptExample from '../project.script.example.json';

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

// ScriptVideo: one component for every language and format; size, fps and duration come from the props written by
// scripts/production.py (see references/remotion-integration.md).
const scriptDefaultProps = scriptExample as unknown as ScriptVideoProps;
const calculateScriptMetadata: CalculateMetadataFunction<ScriptVideoProps> = ({props}) => {
  return {
    width: props.canvas.width,
    height: props.canvas.height,
    fps: props.canvas.fps,
    durationInFrames: props.canvas.durationInFrames,
  };
};

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
        id="ScriptVideo"
        component={ScriptVideo}
        durationInFrames={scriptDefaultProps.canvas.durationInFrames}
        fps={scriptDefaultProps.canvas.fps}
        width={scriptDefaultProps.canvas.width}
        height={scriptDefaultProps.canvas.height}
        defaultProps={scriptDefaultProps}
        calculateMetadata={calculateScriptMetadata}
      />
    </>
  );
};
