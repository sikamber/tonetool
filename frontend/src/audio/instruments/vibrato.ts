import type { NoteEvent } from "./types";

export interface VibratoSpec {
  hz: number; // speed of the wobble
  cents: number; // how far the pitch moves either way
  delay: number; // seconds before it begins, as singers and players start a note straight
  ramp: number; // seconds it takes to grow to full depth
}

/**
 * Wobbles the pitch of `targets` (oscillator `detune` parameters). A note that joins one already
 * held has no straight start, so its vibrato is already under way.
 */
export function addVibrato(
  ctx: BaseAudioContext,
  note: NoteEvent,
  targets: AudioParam[],
  spec: VibratoSpec,
  stopAt: number,
): void {
  const lfo = ctx.createOscillator();
  lfo.frequency.value = spec.hz;
  const depth = ctx.createGain();
  const delay = note.attack ? spec.delay : 0;
  const ramp = note.attack ? spec.ramp : Math.min(spec.ramp, 0.05);
  depth.gain.setValueAtTime(0, note.when);
  depth.gain.setValueAtTime(0, note.when + delay);
  depth.gain.linearRampToValueAtTime(spec.cents, note.when + delay + ramp);
  lfo.connect(depth);
  for (const target of targets) depth.connect(target);
  lfo.start(note.when);
  lfo.stop(stopAt);
}
