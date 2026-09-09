/**
 * Design tokens for the Content Factory film — direction "Press Room".
 *
 * The engine is a publishing machine that refuses to guess, so the film is cut
 * from two materials only: graphite (the machine) and newsprint (what it
 * makes). Colour is never decoration here — green, amber and red are the three
 * verdicts a guard can return, and nothing else in the frame is allowed to use
 * them.
 */

export const COLOR = {
  /** The machine: unlit graphite the plates sit on. */
  graphite: '#101314',
  graphite2: '#171b1d',
  /** What it produces: warm newsprint, low to high. */
  paper: '#f2eee6',
  paperDim: '#ded8cc',
  /** Ink printed on the paper. */
  ink: '#14171a',
  inkMuted: '#4a5054',
  /** Type set on the graphite. */
  chalk: '#e7e3da',
  chalkDim: '#9aa1a3',
  chalkFaint: '#5d6568',
  /** The three verdicts. Nothing decorative may use these. */
  pass: '#4e9c72',
  warn: '#d2921f',
  reject: '#c4503f',
  /** Structure. */
  rule: 'rgba(231, 227, 218, 0.16)',
  ruleStrong: 'rgba(231, 227, 218, 0.34)',
} as const;

/** Daylight through a high window, falling on the plate from above. */
export const GROUND =
  'radial-gradient(120% 90% at 50% -20%, #1d2224 0%, #131719 45%, #0d1011 100%)';

/** A sheet of newsprint: the only thing in the film that is not the machine. */
export const SHEET: React.CSSProperties = {
  background: 'linear-gradient(180deg, #f4f1e9, #e9e4d9)',
  boxShadow:
    '0 1px 0 0 rgba(255,255,255,0.6) inset, 0 30px 70px -30px rgba(0,0,0,0.75)',
  borderRadius: 3,
};

/** A milled cell in the machine — an agent, a gate, a slot. */
export const CELL: React.CSSProperties = {
  background: 'linear-gradient(180deg, #1a1f21, #14181a)',
  border: '1px solid rgba(231, 227, 218, 0.14)',
  borderRadius: 3,
};

/** The one curve this film moves on. */
export const EXPO = [0.16, 1, 0.3, 1] as const;
