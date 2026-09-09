import { loadFont as loadPlexMono } from '@remotion/google-fonts/IBMPlexMono';
import { loadFont as loadInstrumentSerif } from '@remotion/google-fonts/InstrumentSerif';

/** Instrument Serif says "published"; IBM Plex Mono says "machine". */
export const { fontFamily: SERIF } = loadInstrumentSerif('normal', {
  weights: ['400'],
  subsets: ['latin'],
});

export const { fontFamily: MONO } = loadPlexMono('normal', {
  weights: ['400', '500', '600'],
  subsets: ['latin'],
});
