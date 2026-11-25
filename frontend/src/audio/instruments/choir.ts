import { applyEnvelope, disconnectWhenEnded } from "./envelope";
import { noiseSource } from "./noise";
import { midiToHz, type Instrument, type NoteEvent } from "./types";
import { addVibrato, type VibratoSpec } from "./vibrato";

/** One resonance of the vocal tract: where it is, how narrow, how strong. */
export interface Formant {
  freq: number;
  q: number;
  gain: number;
}

export interface ChoirSpec {
  id: string;
  label: string;
  formants: Formant[];
  /** Loudness: the peak gain of the note. */
  level: number;
}

/** Three slightly out-of-tune "singers" make a section sound like several people. */
const VOICE_DETUNE_CENTS = [-7, 0, 7];
const VIBRATO: VibratoSpec = { hz: 5.4, cents: 14, delay: 0.3, ramp: 0.3 };
const ATTACK = 0.07;
const RELEASE = 0.16;
/** The first formant is kept at least this far above the pitch, and each later one above the one before. */
const FIRST_FORMANT_OVER_PITCH = 1.05;
const FORMANT_SPACING = 1.25;
/**
 * A formant that sits right on the note's fundamental would let it through at full strength and
 * make the note much louder than one an octave lower. So a formant never passes more than this
 * fraction of the fundamental (a pass of 1 is the formant's own centre).
 */
const FUNDAMENTAL_PASS_LIMIT = 0.4;

/** How much of a pure tone at `hz` an ideal band-pass at `centre` with quality `q` passes (1 at the centre). */
const passAt = (hz: number, centre: number, q: number): number =>
  1 / Math.sqrt(1 + (q * (hz / centre - centre / hz)) ** 2);

/** The chest and head body of the voice: low-passed source, so low notes keep their fundamental. */
const BODY = { cutoff: 800, gain: 0.3 };
/** A little breath noise around 2.5 kHz. */
const BREATH = { centre: 2500, q: 0.8, gain: 0.02 };

/**
 * A sung vowel: a sawtooth (the buzz of the vocal folds, three of them detuned) through parallel
 * band-pass filters at the vowel's formants, with vibrato that sets in after a straight start.
 * High notes pull the formants up with them, as singers do, so the vowel does not vanish.
 */
export class ChoirInstrument implements Instrument {
  readonly id: string;
  readonly label: string;

  constructor(private readonly spec: ChoirSpec) {
    this.id = spec.id;
    this.label = spec.label;
  }

  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void {
    const env = ctx.createGain();
    const stopAt = applyEnvelope(env.gain, note, { attack: ATTACK, release: RELEASE, peak: this.spec.level });
    env.connect(output);

    const fundamental = midiToHz(note.pitch);
    const source = ctx.createGain();
    source.gain.value = 1 / VOICE_DETUNE_CENTS.length;
    const detunes: AudioParam[] = [];
    for (const cents of VOICE_DETUNE_CENTS) {
      const oscillator = ctx.createOscillator();
      oscillator.type = "sawtooth";
      oscillator.frequency.value = fundamental;
      oscillator.detune.value = cents;
      oscillator.connect(source);
      oscillator.start(note.when);
      oscillator.stop(stopAt);
      detunes.push(oscillator.detune);
      if (detunes.length === 1) disconnectWhenEnded(oscillator, env);
    }

    let floor = (fundamental * FIRST_FORMANT_OVER_PITCH) / FORMANT_SPACING;
    for (const formant of this.spec.formants) {
      const centre = Math.min(Math.max(formant.freq, floor * FORMANT_SPACING), ctx.sampleRate / 2 - 200);
      floor = centre;
      const filter = ctx.createBiquadFilter();
      filter.type = "bandpass";
      filter.frequency.value = centre;
      filter.Q.value = formant.q;
      const gain = ctx.createGain();
      gain.gain.value = formant.gain * Math.min(1, FUNDAMENTAL_PASS_LIMIT / passAt(fundamental, centre, formant.q));
      source.connect(filter).connect(gain).connect(env);
    }

    const body = ctx.createBiquadFilter();
    body.type = "lowpass";
    body.frequency.value = BODY.cutoff;
    body.Q.value = 0; // dB for a low-pass: no resonance peak
    const bodyGain = ctx.createGain();
    bodyGain.gain.value = BODY.gain;
    source.connect(body).connect(bodyGain).connect(env);

    const breath = ctx.createBiquadFilter();
    breath.type = "bandpass";
    breath.frequency.value = BREATH.centre;
    breath.Q.value = BREATH.q;
    const breathGain = ctx.createGain();
    breathGain.gain.value = BREATH.gain;
    noiseSource(ctx, note.when, stopAt).connect(breath).connect(breathGain).connect(env);

    addVibrato(ctx, note, detunes, VIBRATO, stopAt);
  }
}
