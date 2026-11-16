import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';

// Local SIL-OFL fonts from the media library (public/lib -> media-library). No network fonts.
const FACES: Array<{family: string; file: string; weight?: string; style?: string}> = [
  {family: 'Instrument Serif', file: 'InstrumentSerif-Regular.ttf'},
  {family: 'Instrument Serif Italic', file: 'InstrumentSerif-Italic.ttf'},
  {family: 'Gloock', file: 'Gloock-Regular.ttf'},
  {family: 'Italiana', file: 'Italiana-Regular.ttf'},
  {family: 'Instrument Sans', file: 'InstrumentSans-Regular.ttf', weight: '400'},
  {family: 'Instrument Sans', file: 'InstrumentSans-Bold.ttf', weight: '700'},
  {family: 'EB Garamond', file: 'EBGaramond12-Regular.ttf'},
];

let loaded: Promise<unknown> | null = null;

export const ensureFonts = () => {
  if (!loaded) {
    loaded = Promise.all(
      FACES.map((face) =>
        loadFont({
          family: face.family,
          url: staticFile(`lib/fonts/${face.file}`),
          weight: face.weight ?? '400',
          style: face.style ?? 'normal',
        }),
      ),
    );
  }
  return loaded;
};
