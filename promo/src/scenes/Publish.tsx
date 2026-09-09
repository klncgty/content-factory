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
 * What actually leaves the machine: a markdown file with frontmatter and its
 * images, written into the target repo. The Publisher never touches git and
 * the GitAgent never writes content — the split is the whole reason a failed
 * push cannot leave half an article behind.
 */
const STEPS = [
  { agent: 'Publisher', line: 'content/blog/*.md + images' },
  { agent: 'GitAgent', line: 'commit → push (direct, on green)' },
  { agent: 'oleart.co', line: 'live, every three days' },
];

const Step: React.FC<{ index: number; agent: string; line: string }> = ({
  index,
  agent,
  line,
}) => {
  const frame = useCurrentFrame();
  const at = 78 + index * 26;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 26,
        opacity: interpolate(frame, [at, at + 16], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
        translate: interpolate(frame, [at, at + 20], ['0px 12px', '0px 0px'], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
      }}
    >
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: 10,
          flexShrink: 0,
          background: interpolateColors(frame, [at + 6, at + 20], ['#2a3033', '#4e9c72']),
        }}
      />
      <span
        style={{
          fontFamily: MONO,
          fontSize: 28,
          fontWeight: 600,
          letterSpacing: '0.02em',
          color: '#f2eee6',
          width: 240,
          flexShrink: 0,
        }}
      >
        {agent}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 24, color: '#9aa1a3' }}>{line}</span>
    </div>
  );
};

export const Publish: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Backdrop>
      <Slug index="05" label="The output" />

      <AbsoluteFill
        style={{
          padding: '120px 140px',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 80,
        }}
      >
        {/* The artefact itself — markdown, not HTML. Presentation is the site's job. */}
        <Interactive.Div
          name="Article sheet"
          style={{
            width: 800,
            flexShrink: 0,
            padding: '48px 52px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            background: 'linear-gradient(180deg, #f4f1e9, #e9e4d9)',
            borderRadius: 3,
            boxShadow: '0 34px 80px -34px rgba(0,0,0,0.85)',
            opacity: interpolate(frame, [0, 24], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            translate: interpolate(frame, [0, 34], ['0px 24px', '0px 0px'], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          <Interactive.Div
            name="Frontmatter"
            style={{
              fontFamily: MONO,
              fontSize: 26,
              lineHeight: 1.75,
              color: '#14171a',
              whiteSpace: 'pre',
              opacity: interpolate(frame, [18, 44], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            {`---
title: "Storing olive oil"
slug: storing-olive-oil
description: "Light, heat and air …"
cover: /blog/images/cover.webp
sources: [knowledge/oleart/oil.md]
---`}
          </Interactive.Div>

          <Interactive.Div
            name="Sheet label"
            style={{
              fontFamily: MONO,
              fontSize: 20,
              fontWeight: 600,
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: '#4a5054',
              paddingTop: 18,
              opacity: interpolate(frame, [40, 62], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            Markdown · never HTML
          </Interactive.Div>
        </Interactive.Div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 42 }}>
          <Interactive.Div
            name="Headline"
            style={{
              fontFamily: SERIF,
              fontSize: 96,
              lineHeight: 0.98,
              color: '#f2eee6',
              opacity: interpolate(frame, [10, 32], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
              translate: interpolate(frame, [10, 40], ['0px 16px', '0px 0px'], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            Then it ships itself.
          </Interactive.Div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
            {STEPS.map((step, i) => (
              <Step key={step.agent} index={i} agent={step.agent} line={step.line} />
            ))}
          </div>

          <Interactive.Div
            name="Cadence"
            style={{
              fontFamily: MONO,
              fontSize: 22,
              letterSpacing: '0.16em',
              color: '#7d8588',
              paddingTop: 12,
              opacity: interpolate(frame, [156, 178], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            cron: 59 20 3,6,9,12,15,18,21,24,27,30 * *
          </Interactive.Div>
        </div>
      </AbsoluteFill>
    </Backdrop>
  );
};
