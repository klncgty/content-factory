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
 * The gates, walked in real time. The draft clears scope, is stopped by
 * GroundingGuard over a number that appears nowhere in the knowledge base,
 * travels backwards to the Writer, and only leaves the line on the second
 * attempt. The reject is the point of the scene, so it is the slowest beat.
 */
export const Guards: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <Slug index="03" label="The gates" />

      <AbsoluteFill
        style={{
          padding: '110px 140px',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 96,
        }}
      >
        <Interactive.Div
          name="Headline"
          style={{
            fontFamily: SERIF,
            fontSize: 104,
            lineHeight: 1,
            color: '#f2eee6',
            opacity: interpolate(frame, [0, 20], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [0, 28], ['0px 16px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          The Editor is a gate, not a suggestion.
        </Interactive.Div>

        {/* The line itself. Everything below is positioned against it. */}
        <div style={{ position: 'relative', height: 360 }}>
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 200,
              width: 1640,
              height: 1,
              background: 'rgba(231, 227, 218, 0.16)',
            }}
          />

          {/* Gate 1 — ScopeGuard. Two independent checks, both deterministic-first. */}
          <div style={{ position: 'absolute', left: 420, top: 130 }}>
            <div
              style={{
                width: 3,
                height: 140,
                borderRadius: 3,
                background: interpolateColors(frame, [38, 50], ['#2a3033', '#4e9c72']),
              }}
            />
            <div
              style={{
                position: 'absolute',
                top: 156,
                left: -110,
                width: 240,
                textAlign: 'center',
                fontFamily: MONO,
                fontSize: 23,
                fontWeight: 600,
                letterSpacing: '0.16em',
                color: interpolateColors(frame, [38, 50], ['#5d6568', '#e7e3da']),
              }}
            >
              ScopeGuard
            </div>
          </div>

          {/* Gate 2 — GroundingGuard. The one that sends the line backwards. */}
          <div style={{ position: 'absolute', left: 840, top: 130 }}>
            <div
              style={{
                width: 3,
                height: 140,
                borderRadius: 3,
                background: interpolateColors(
                  frame,
                  [72, 80, 108, 118, 168, 178],
                  ['#2a3033', '#c4503f', '#c4503f', '#2a3033', '#2a3033', '#4e9c72'],
                ),
              }}
            />
            <div
              style={{
                position: 'absolute',
                top: 156,
                left: -130,
                width: 280,
                textAlign: 'center',
                fontFamily: MONO,
                fontSize: 23,
                fontWeight: 600,
                letterSpacing: '0.16em',
                color: interpolateColors(
                  frame,
                  [72, 80, 168, 178],
                  ['#5d6568', '#c4503f', '#c4503f', '#4e9c72'],
                ),
              }}
            >
              GroundingGuard
            </div>
          </div>

          {/* Gate 3 — the LLM quality read, last because it is the softest. */}
          <div style={{ position: 'absolute', left: 1260, top: 130 }}>
            <div
              style={{
                width: 3,
                height: 140,
                borderRadius: 3,
                background: interpolateColors(frame, [186, 198], ['#2a3033', '#4e9c72']),
              }}
            />
            <div
              style={{
                position: 'absolute',
                top: 156,
                left: -110,
                width: 240,
                textAlign: 'center',
                fontFamily: MONO,
                fontSize: 23,
                fontWeight: 600,
                letterSpacing: '0.16em',
                color: interpolateColors(frame, [186, 198], ['#5d6568', '#e7e3da']),
              }}
            >
              Quality
            </div>
          </div>

          {/* The reject, called out where it happens. */}
          <Interactive.Div
            name="Reject callout"
            style={{
              position: 'absolute',
              left: 580,
              top: 44,
              width: 800,
              textAlign: 'center',
              fontFamily: MONO,
              fontSize: 26,
              fontWeight: 600,
              letterSpacing: '0.12em',
              color: '#c4503f',
              opacity: interpolate(frame, [76, 92, 116, 128], [0, 1, 1, 0], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            REJECT · “14–18 °C” is not in the source
          </Interactive.Div>

          {/* Where a rejected draft actually goes. */}
          <Interactive.Div
            name="Retry callout"
            style={{
              position: 'absolute',
              left: 0,
              top: 40,
              width: 420,
              textAlign: 'center',
              fontFamily: MONO,
              fontSize: 26,
              fontWeight: 600,
              letterSpacing: '0.12em',
              color: '#d2921f',
              opacity: interpolate(frame, [112, 126, 150, 162], [0, 1, 1, 0], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            → Writer, with reasons
          </Interactive.Div>

          {/* The draft, carrying itself down the line. */}
          <Interactive.Div
            name="Draft"
            style={{
              position: 'absolute',
              left: 0,
              top: 168,
              padding: '12px 26px',
              borderRadius: 3,
              background: 'linear-gradient(180deg, #f4f1e9, #e9e4d9)',
              fontFamily: MONO,
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: '0.2em',
              color: '#14171a',
              boxShadow: '0 18px 40px -18px rgba(0,0,0,0.8)',
              opacity: interpolate(frame, [4, 20], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
              translate: interpolate(
                frame,
                [10, 44, 62, 76, 92, 116, 136, 172, 190, 214],
                [
                  '40px 0px',
                  '360px 0px',
                  '360px 0px',
                  '780px 0px',
                  '780px 0px',
                  '60px 0px',
                  '60px 0px',
                  '780px 0px',
                  '1200px 0px',
                  '1470px 0px',
                ],
                {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                },
              ),
            }}
          >
            DRAFT
          </Interactive.Div>

          {/* What clearing all three gates buys. */}
          <Interactive.Div
            name="Published stamp"
            style={{
              position: 'absolute',
              left: 1424,
              top: 246,
              fontFamily: MONO,
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: '0.2em',
              color: '#4e9c72',
              opacity: interpolate(frame, [200, 216], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            PUBLISH
          </Interactive.Div>
        </div>
      </AbsoluteFill>
    </Backdrop>
  );
};
