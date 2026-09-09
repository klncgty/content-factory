import React from 'react';
import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Chrome';
import { MONO, SERIF } from '../fonts';

/**
 * The address, and the two numbers worth trusting the machine over: the test
 * count and the fact that it is already publishing.
 */
export const EndCard: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 30,
        }}
      >
        <Interactive.Div
          name="Wordmark"
          style={{
            fontFamily: SERIF,
            fontSize: 156,
            lineHeight: 1,
            color: '#f2eee6',
            opacity: interpolate(frame, [0, 24], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [0, 32], ['0px 18px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Content Factory
        </Interactive.Div>

        <Interactive.Div
          name="Rule"
          style={{
            height: 1,
            background: 'rgba(231, 227, 218, 0.34)',
            width: interpolate(frame, [16, 58], [0, 900], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        />

        <Interactive.Div
          name="Address"
          style={{
            fontFamily: MONO,
            fontSize: 34,
            fontWeight: 500,
            letterSpacing: '0.06em',
            color: '#f2eee6',
            opacity: interpolate(frame, [34, 58], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          github.com/klncgty/content-factory
        </Interactive.Div>

        <Interactive.Div
          name="Stats"
          style={{
            fontFamily: MONO,
            fontSize: 24,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: '#7d8588',
            paddingTop: 14,
            opacity: interpolate(frame, [56, 80], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          397 tests · 10 agents · live on oleart.co
        </Interactive.Div>
      </AbsoluteFill>
    </Backdrop>
  );
};
