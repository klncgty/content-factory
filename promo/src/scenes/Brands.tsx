import React from 'react';
import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop, Slug } from '../components/Chrome';
import { MONO, SERIF } from '../fonts';

/**
 * The claim that makes this an engine rather than a script: no brand name
 * exists anywhere in the Python package. The tree is revealed a line at a
 * time, because the argument is precisely that the list is short.
 */
const TREE = [
  { path: 'brands/oleart/scope.yaml', note: 'what may be written about' },
  { path: 'brands/oleart/brand.yaml', note: 'voice, banned claims' },
  { path: 'brands/oleart/seo.yaml', note: 'keyword clusters, link targets' },
  { path: 'brands/oleart/publish.yaml', note: 'which repo, which branch' },
  { path: 'brands/oleart/models.yaml', note: 'a model per agent' },
  { path: 'knowledge/brands/oleart/*.md', note: 'the facts themselves' },
];

const Row: React.FC<{ index: number; path: string; note: string }> = ({
  index,
  path,
  note,
}) => {
  const frame = useCurrentFrame();
  const at = 34 + index * 11;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 28,
        paddingBottom: 18,
        borderBottom: '1px solid rgba(231, 227, 218, 0.1)',
        opacity: interpolate(frame, [at, at + 14], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
        translate: interpolate(frame, [at, at + 18], ['-14px 0px', '0px 0px'], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
      }}
    >
      <span
        style={{
          fontFamily: MONO,
          fontSize: 28,
          fontWeight: 600,
          color: '#f2eee6',
          width: 520,
          flexShrink: 0,
        }}
      >
        {path}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 23, color: '#7d8588' }}>{note}</span>
    </div>
  );
};

export const Brands: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <Slug index="04" label="Second brand" />

      <AbsoluteFill
        style={{
          padding: '120px 140px',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 90,
        }}
      >
        <div style={{ width: 560, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 34 }}>
          <Interactive.Div
            name="Headline"
            style={{
              fontFamily: SERIF,
              fontSize: 104,
              lineHeight: 0.98,
              color: '#f2eee6',
              opacity: interpolate(frame, [0, 22], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
              translate: interpolate(frame, [0, 30], ['0px 16px', '0px 0px'], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            A brand is a directory.
          </Interactive.Div>

          <Interactive.Div
            name="Body"
            style={{
              fontFamily: MONO,
              fontSize: 27,
              lineHeight: 1.55,
              color: '#9aa1a3',
              opacity: interpolate(frame, [16, 40], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            No brand, product or topic is named anywhere in the engine. Adding one is
            filling these files in.
          </Interactive.Div>

          <Interactive.Div
            name="Proof"
            style={{
              fontFamily: MONO,
              fontSize: 19,
              whiteSpace: 'nowrap',
              letterSpacing: '0.02em',
              color: '#4e9c72',
              paddingTop: 10,
              opacity: interpolate(frame, [120, 144], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            ✓ test_second_brand_works_without_touching_python
          </Interactive.Div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {TREE.map((row, i) => (
            <Row key={row.path} index={i} path={row.path} note={row.note} />
          ))}
        </div>
      </AbsoluteFill>
    </Backdrop>
  );
};
