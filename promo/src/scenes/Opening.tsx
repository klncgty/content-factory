import React from 'react';
import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Chrome';
import { MONO, SERIF } from '../fonts';

/**
 * Cold open. The legend arrives first, then the rule is drawn under the
 * wordmark — the machine states what it is before it does anything.
 */
export const Opening: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 26,
        }}
      >
        <Interactive.Div
          name="Legend"
          style={{
            fontFamily: MONO,
            fontSize: 26,
            fontWeight: 500,
            letterSpacing: '0.44em',
            textTransform: 'uppercase',
            color: '#9aa1a3',
            opacity: interpolate(frame, [4, 26], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [4, 30], ['0px 12px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Autonomous publishing engine
        </Interactive.Div>

        <Interactive.Div
          name="Wordmark"
          style={{
            fontFamily: SERIF,
            fontSize: 172,
            lineHeight: 1,
            color: '#f2eee6',
            opacity: interpolate(frame, [14, 38], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [14, 46], ['0px 22px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Content Factory
        </Interactive.Div>

        {/* The rule is drawn, not faded — the first machine movement. */}
        <Interactive.Div
          name="Rule"
          style={{
            height: 1,
            background: 'rgba(231, 227, 218, 0.34)',
            width: interpolate(frame, [24, 66], [0, 980], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        />

        <Interactive.Div
          name="Subtitle"
          style={{
            fontFamily: MONO,
            fontSize: 30,
            fontWeight: 400,
            letterSpacing: '0.16em',
            color: '#9aa1a3',
            opacity: interpolate(frame, [40, 62], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          10 agents · 0 lines of brand code · shipping live
        </Interactive.Div>
      </AbsoluteFill>
    </Backdrop>
  );
};
