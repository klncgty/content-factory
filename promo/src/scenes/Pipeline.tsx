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
 * The run, in order. Ten cells light in sequence at four frames a step so the
 * eye reads a conveyor rather than a feature list; the Editor cell lights
 * amber because it is the only one that can send the line backwards.
 */
const AGENTS = [
  { name: 'TopicScout', note: 'candidate topics' },
  { name: 'Research', note: 'sourced notes' },
  { name: 'Strategist', note: 'outline + brief' },
  { name: 'Writer', note: 'the draft' },
  { name: 'SEOOptimizer', note: 'meta + slug' },
  { name: 'Linker', note: 'keyword overlap' },
  { name: 'ImageGenerator', note: 'cover · thumb · og' },
  { name: 'Editor', note: 'the gate', gate: true },
  { name: 'Publisher', note: 'markdown + images' },
  { name: 'GitAgent', note: 'commit & push' },
];

const Cell: React.FC<{
  index: number;
  name: string;
  note: string;
  gate?: boolean;
}> = ({ index, name, note, gate }) => {
  const frame = useCurrentFrame();
  const at = 24 + index * 15;

  return (
    <div
      style={{
        padding: '26px 24px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        borderRadius: 3,
        background: 'linear-gradient(180deg, #1a1f21, #14181a)',
        borderWidth: 1,
        borderStyle: 'solid',
        borderColor: interpolateColors(
          frame,
          [at, at + 14],
          ['rgba(231,227,218,0.1)', gate ? 'rgba(210,146,31,0.55)' : 'rgba(78,156,114,0.45)'],
        ),
        opacity: interpolate(frame, [at - 10, at + 6], [0.35, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
        translate: interpolate(frame, [at - 10, at + 10], ['0px 8px', '0px 0px'], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* The lamp: this step has run. */}
        <div
          style={{
            width: 9,
            height: 9,
            borderRadius: 9,
            background: interpolateColors(
              frame,
              [at, at + 14],
              ['#2a3033', gate ? '#d2921f' : '#4e9c72'],
            ),
          }}
        />
        <span
          style={{
            fontFamily: MONO,
            fontSize: 19,
            fontWeight: 500,
            letterSpacing: '0.22em',
            color: '#5d6568',
          }}
        >
          {String(index + 1).padStart(2, '0')}
        </span>
      </div>

      <span
        style={{
          fontFamily: MONO,
          fontSize: 27,
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: interpolateColors(frame, [at, at + 14], ['#5d6568', '#f2eee6']),
        }}
      >
        {name}
      </span>
      <span
        style={{
          fontFamily: MONO,
          fontSize: 19,
          letterSpacing: '0.04em',
          color: '#7d8588',
        }}
      >
        {note}
      </span>
    </div>
  );
};

export const Pipeline: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <Slug index="02" label="The run" />

      <AbsoluteFill
        style={{
          padding: '120px 140px',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 58,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 36 }}>
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
            Ten agents, one run.
          </Interactive.Div>

          <Interactive.Div
            name="Command"
            style={{
              fontFamily: MONO,
              fontSize: 26,
              letterSpacing: '0.02em',
              color: '#9aa1a3',
              paddingBottom: 16,
              opacity: interpolate(frame, [12, 34], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            content-factory --brand oleart
          </Interactive.Div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: 20,
          }}
        >
          {AGENTS.map((agent, i) => (
            <Cell
              key={agent.name}
              index={i}
              name={agent.name}
              note={agent.note}
              gate={agent.gate}
            />
          ))}
        </div>

        <Interactive.Div
          name="Caption"
          style={{
            fontFamily: MONO,
            fontSize: 28,
            letterSpacing: '0.04em',
            color: '#9aa1a3',
            opacity: interpolate(frame, [186, 210], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Nine of them produce. One of them refuses.
        </Interactive.Div>
      </AbsoluteFill>
    </Backdrop>
  );
};
