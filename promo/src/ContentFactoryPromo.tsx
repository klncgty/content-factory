import React from 'react';
import { AbsoluteFill } from 'remotion';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { Brands } from './scenes/Brands';
import { Drift } from './scenes/Drift';
import { EndCard } from './scenes/EndCard';
import { Guards } from './scenes/Guards';
import { Opening } from './scenes/Opening';
import { Pipeline } from './scenes/Pipeline';
import { Publish } from './scenes/Publish';

/**
 * The film, in the order the engine's argument is made: here is the failure
 * that motivated it, here is the line, here is the gate that stops the line,
 * here is why the line is not tied to one brand, here is what it ships.
 *
 * 80 + 165 + 240 + 230 + 165 + 195 + 145 = 1220 frames, less six 15-frame
 * dissolves = 1130 frames (37.7s at 30fps). Nothing cuts hard: the whole
 * pitch is a machine that never jumps a step.
 */
export const ContentFactoryPromo: React.FC = () => {
  return (
    <AbsoluteFill>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={80} name="Opening">
          <Opening />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={165} name="Drift">
          <Drift />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={240} name="Pipeline">
          <Pipeline />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={230} name="Guards">
          <Guards />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={165} name="Brands">
          <Brands />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={195} name="Publish">
          <Publish />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: 15 })}
        />

        <TransitionSeries.Sequence durationInFrames={145} name="End card">
          <EndCard />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
