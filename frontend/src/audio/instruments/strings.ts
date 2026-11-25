import { applyEnvelope, disconnectWhenEnded } from "./envelope";
import { midiToHz, type Instrument, type NoteEvent } from "./types";
import { addVibrato, type VibratoSpec } from "./vibrato";

const DETUNE_CENTS = [-7, 7]; // two players
const VIBRATO: VibratoSpec = { hz: 5.2, cents: 10, delay: 0.25, ramp: 0.35 };
const ATTACK = 0.1;
const RELEASE = 0.22;

/**
 * Bowed strings: two detuned sawtooths through a low-pass filter that follows the pitch (the
 * higher the note, the brighter the filter can be), with a slow bow attack and vibrato.
 */
export class StringsInstrument implements Instrument {
  readonly id = "strings";
  readonly label = "Strings";

  constructor(private readonly level: number) {}

  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void {
    const env = ctx.createGain();
    const stopAt = applyEnvelope(env.gain, note, { attack: ATTACK, release: RELEASE, peak: this.level });
    env.connect(output);

    const fundamental = midiToHz(note.pitch);
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = Math.min(Math.max(fundamental * 6, 1000), 7000);
    tone.Q.value = 0; // dB for a low-pass: no resonance peak
    const mix = ctx.createGain();
    mix.gain.value = 1 / DETUNE_CENTS.length;
    mix.connect(tone).connect(env);

    const detunes: AudioParam[] = [];
    for (const cents of DETUNE_CENTS) {
      const oscillator = ctx.createOscillator();
      oscillator.type = "sawtooth";
      oscillator.frequency.value = fundamental;
      oscillator.detune.value = cents;
      oscillator.connect(mix);
      oscillator.start(note.when);
      oscillator.stop(stopAt);
      detunes.push(oscillator.detune);
      if (detunes.length === 1) disconnectWhenEnded(oscillator, env);
    }
    addVibrato(ctx, note, detunes, VIBRATO, stopAt);
  }
}
