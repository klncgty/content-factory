import React from 'react';
import { Composition, Folder } from 'remotion';
import './index.css';
import { ContentFactoryPromo } from './ContentFactoryPromo';
import { Brands } from './scenes/Brands';
import { Drift } from './scenes/Drift';
import { EndCard } from './scenes/EndCard';
import { Guards } from './scenes/Guards';
import { Opening } from './scenes/Opening';
import { Pipeline } from './scenes/Pipeline';
import { Publish } from './scenes/Publish';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ContentFactoryPromo"
        component={ContentFactoryPromo}
        durationInFrames={1130}
        fps={30}
        width={1920}
        height={1080}
      />

      {/* Every plate is also registered on its own, so one scene can be
          re-timed in the Studio without scrubbing the whole film. */}
      <Folder name="Scenes">
        <Composition
          id="Opening"
          component={Opening}
          durationInFrames={80}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Drift"
          component={Drift}
          durationInFrames={165}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Pipeline"
          component={Pipeline}
          durationInFrames={240}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Guards"
          component={Guards}
          durationInFrames={230}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Brands"
          component={Brands}
          durationInFrames={165}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Publish"
          component={Publish}
          durationInFrames={195}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="EndCard"
          component={EndCard}
          durationInFrames={145}
          fps={30}
          width={1920}
          height={1080}
        />
      </Folder>
    </>
  );
};
