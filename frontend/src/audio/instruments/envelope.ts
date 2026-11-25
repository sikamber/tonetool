import type { NoteEvent } from "./types";

export interface EnvelopeSpec {
  attack: number; // seconds
  release: number; // seconds
  /** Gain at the top of the attack. Sets how loud the instrument is. */
  peak: number;
  /** Percussive instruments fall towards `sustain` (0..1 of peak) with this time constant. */
  decay?: { time: number; sustain: number };
}

/** Short fade-in when joining a note that is already held, to avoid a click. */
export const JOIN_FADE = 0.005;

/** How many time constants the release lasts: e^-7 is -61 dB, so stopping there cannot click. */
const RELEASE_TIME_CONSTANTS = 7;

/** Disconnects a note's gain node when its first source ends, so the finished note can be collected. */
export function disconnectWhenEnded(source: AudioScheduledSourceNode, env: AudioNode): void {
  source.onended = () => env.disconnect();
}

/**
 * Schedules attack, optional decay and release on a gain parameter. Returns the time after which
 * the note is silent and its nodes can be stopped.
 */
export function applyEnvelope(param: AudioParam, note: NoteEvent, spec: EnvelopeSpec): number {
  const end = note.when + note.duration;
  const attack = note.attack ? Math.min(spec.attack, note.duration / 2) : JOIN_FADE;
  param.setValueAtTime(0, note.when);
  param.linearRampToValueAtTime(spec.peak, note.when + attack);
  if (spec.decay) {
    // A strike falls from the peak; joining a held note starts at the sustain level.
    if (note.attack) param.setTargetAtTime(spec.peak * spec.decay.sustain, note.when + attack, spec.decay.time);
    else param.setValueAtTime(spec.peak * spec.decay.sustain, note.when + attack);
  }
  param.setTargetAtTime(0, end, spec.release / RELEASE_TIME_CONSTANTS);
  return end + spec.release;
}
