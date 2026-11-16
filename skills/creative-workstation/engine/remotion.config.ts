import {Config} from '@remotion/cli/config';

// Use a preinstalled Chromium headless shell when REMOTION_BROWSER is set (offline/locked-down hosts),
// otherwise Remotion downloads its own.
if (process.env.REMOTION_BROWSER) {
  Config.setBrowserExecutable(process.env.REMOTION_BROWSER);
}
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setConcurrency(Number(process.env.REMOTION_CONCURRENCY ?? 4));
Config.setOffthreadVideoCacheSizeInBytes(512 * 1024 * 1024);
