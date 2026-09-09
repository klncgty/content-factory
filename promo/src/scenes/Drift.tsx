import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  interpolateColors,
  useCurrentFrame,
} from 'remotion';
import { Backdrop, Slug } from '../components/Chrome';
import { MONO, SERIF } from '../fonts';

/**
 * The problem the engine was built around, shown rather than claimed: the
 * knowledge base says 5–8 °C, the draft says 6–8 °C, and no amount of asking
 * the model whether it is sure will surface that one digit.
 */
export const Drift: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <Slug index="01" label="The failure" />

      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 62,
        }}
      >
        <Interactive.Div
          name="Statement"
          style={{
            fontFamily: SERIF,
            fontSize: 108,
            lineHeight: 1,
            color: '#f2eee6',
            opacity: interpolate(frame, [0, 22], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [0, 30], ['0px 18px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Models drift off the source.
        </Interactive.Div>

        {/* The sheet: what the knowledge base holds, and what came back. */}
        <Interactive.Div
          name="Comparison sheet"
          style={{
            width: 1480,
            padding: '56px 64px',
            display: 'flex',
            flexDirection: 'column',
            gap: 38,
            background: 'linear-gradient(180deg, #f4f1e9, #e9e4d9)',
            borderRadius: 3,
            boxShadow: '0 30px 70px -30px rgba(0,0,0,0.75)',
            opacity: interpolate(frame, [14, 38], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [14, 46], ['0px 26px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          <Interactive.Div
            name="Source row"
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 44,
              opacity: interpolate(frame, [28, 48], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            <span
              style={{
                fontFamily: MONO,
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: '0.26em',
                textTransform: 'uppercase',
                color: '#4a5054',
                width: 300,
                flexShrink: 0,
              }}
            >
              Knowledge base
            </span>
            <span style={{ fontFamily: MONO, fontSize: 44, color: '#14171a' }}>
              stored at <span style={{ fontWeight: 600 }}>5–8 °C</span>
            </span>
          </Interactive.Div>

          <div style={{ height: 1, background: 'rgba(20,23,26,0.14)' }} />

          <Interactive.Div
            name="Draft row"
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 44,
              opacity: interpolate(frame, [58, 78], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            <span
              style={{
                fontFamily: MONO,
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: '0.26em',
                textTransform: 'uppercase',
                color: '#4a5054',
                width: 300,
                flexShrink: 0,
              }}
            >
              Generated draft
            </span>
            <span style={{ fontFamily: MONO, fontSize: 44, color: '#14171a' }}>
              stored at{' '}
              <Interactive.Span
                name="Drifted number"
                style={{
                  fontWeight: 600,
                  padding: '4px 10px',
                  margin: '0 -4px',
                  borderWidth: 2,
                  borderStyle: 'solid',
                  borderRadius: 3,
                  /* The digit is ordinary ink until the guard marks it. */
                  color: interpolateColors(frame, [86, 104], ['#14171a', '#c4503f']),
                  borderColor: interpolateColors(frame, [86, 104], [
                    'rgba(196, 80, 63, 0)',
                    'rgba(196, 80, 63, 1)',
                  ]),
                }}
              >
                6–8 °C
              </Interactive.Span>
            </span>

            <Interactive.Div
              name="Annotation"
              style={{
                fontFamily: MONO,
                fontSize: 24,
                fontWeight: 600,
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: '#c4503f',
                opacity: interpolate(frame, [100, 120], [0, 1], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                }),
                translate: interpolate(frame, [100, 126], ['-16px 0px', '0px 0px'], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                }),
              }}
            >
              ← nowhere in the source
            </Interactive.Div>
          </Interactive.Div>
        </Interactive.Div>

        <Interactive.Div
          name="Footnote"
          style={{
            fontFamily: MONO,
            fontSize: 30,
            letterSpacing: '0.06em',
            color: '#9aa1a3',
            opacity: interpolate(frame, [118, 142], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Asking the model “is this number right?” approved it.
        </Interactive.Div>
      </AbsoluteFill>
    </Backdrop>
  );
};
