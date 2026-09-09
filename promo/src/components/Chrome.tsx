import React from 'react';
import { AbsoluteFill } from 'remotion';
import { COLOR, GROUND } from '../brand';
import { MONO } from '../fonts';

/**
 * The ground every plate is shot on: graphite lit from a high window, with the
 * faint ruling of a proof sheet laid over it so the frame never reads as flat
 * black.
 */
export const Backdrop: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  return (
    <AbsoluteFill style={{ background: GROUND }}>
      <AbsoluteFill
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(231,227,218,0.035) 0px, rgba(231,227,218,0.035) 1px, transparent 1px, transparent 4px)',
        }}
      />
      {children}
    </AbsoluteFill>
  );
};

/**
 * The scene slug, bottom left — the way a plate is labelled on a contact
 * sheet. It carries the running order so the film reads as documentation of a
 * machine rather than an advert for one.
 */
export const Slug: React.FC<{ index: string; label: string }> = ({
  index,
  label,
}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: 96,
        bottom: 84,
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        fontFamily: MONO,
        fontSize: 22,
        fontWeight: 500,
        letterSpacing: '0.28em',
        textTransform: 'uppercase',
        color: COLOR.chalkFaint,
      }}
    >
      <span>{index}</span>
      <span style={{ width: 42, height: 1, background: COLOR.rule }} />
      <span>{label}</span>
    </div>
  );
};
