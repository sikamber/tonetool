import { applyEnvelope, type EnvelopeSpec } from "./envelope";
import { noiseSource } from "./noise";
import { midiToHz, type Instrument, type NoteEvent } from "./types";
import { addVibrato, type VibratoSpec } from "./vibrato";

export interface AdditiveSpec {
  id: string;
  label: string;
  harmonics: number[]; // relative amplitude of partial 1, 2, 3, ...
  envelope: Omit<EnvelopeSpec, "peak">;
  /** Loudness: the peak gain of the note. */
  level: number;
  vibrato?: VibratoSpec;
  /** Breath noise (a band of noise around `centre` times the pitch), as a fraction of the tone's level. */
  breath?: { level: number; centre: number; q: number };
}

/** A sum of sine partials under an envelope, with optional vibrato and breath noise. */
export class AdditiveInstrument implements Instrument {
  readonly id: string;
  readonly label: string;

  constructor(private readonly spec: AdditiveSpec) {
    this.id = spec.id;
    this.label = spec.label;
  }

  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void {
    const { harmonics, envelope, level, vibrato, breath } = this.spec;
    const env = ctx.createGain();
    const stopAt = applyEnvelope(env.gain, note, { ...envelope, peak: level });
    env.connect(output);

    const total = harmonics.reduce((a, b) => a + b, 0);
    const fundamental = midiToHz(note.pitch);
    const detunes: AudioParam[] = [];
    harmonics.forEach((amplitude, i) => {
      const hz = fundamental * (i + 1);
      if (hz > ctx.sampleRate / 2) return;
      const oscillator = ctx.createOscillator();
      oscillator.frequency.value = hz;
      const partial = ctx.createGain();
      partial.gain.value = amplitude / total;
      oscillator.connect(partial).connect(env);
      oscillator.start(note.when);
      oscillator.stop(stopAt);
      detunes.push(oscillator.detune);
      if (detunes.length === 1) oscillator.onended = () => env.disconnect();
    });
    if (vibrato) addVibrato(ctx, note, detunes, vibrato, stopAt);

    if (breath) {
      const band = ctx.createBiquadFilter();
      band.type = "bandpass";
      band.frequency.value = Math.min(fundamental * breath.centre, ctx.sampleRate / 2 - 100);
      band.Q.value = breath.q;
      const gain = ctx.createGain();
      gain.gain.value = breath.level;
      noiseSource(ctx, note.when, stopAt).connect(band).connect(gain).connect(env);
    }
  }
}
