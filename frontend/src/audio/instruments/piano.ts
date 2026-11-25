import { applyEnvelope, disconnectWhenEnded } from "./envelope";
import { noiseSource } from "./noise";
import { midiToHz, type Instrument, type NoteEvent } from "./types";

const MAX_PARTIALS = 12;
/** Stiff strings are slightly sharp in their upper partials: f_n = n f sqrt(1 + B n^2). */
const INHARMONICITY = 0.0004;
const ATTACK = 0.004;
const RELEASE = 0.09; // the damper falling on the string
/** A note that joins one already sounding starts partway through its decay. */
const JOINED_LEVEL = 0.35;
const HAMMER = { cutoff: 2500, gain: 0.25, decay: 0.012, length: 0.12 };

/**
 * A soft piano: slightly inharmonic partials that each die away on their own schedule (the high
 * ones fast, the low ones slowly, bass notes ringing longer than treble), and a short thump of
 * noise for the hammer.
 */
export class PianoInstrument implements Instrument {
  readonly id = "piano";
  readonly label = "Soft piano";

  constructor(private readonly level: number) {}

  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void {
    const env = ctx.createGain();
    const stopAt = applyEnvelope(env.gain, note, { attack: ATTACK, release: RELEASE, peak: this.level });
    env.connect(output);

    const fundamental = midiToHz(note.pitch);
    // how long the fundamental rings: about 2 s in the middle, longer in the bass
    const ring = Math.min(Math.max(2.2 * (261.6 / fundamental) ** 0.5, 0.5), 3.5);
    const amplitudes: number[] = [];
    for (let n = 1; n <= MAX_PARTIALS; n++) amplitudes.push(n ** -1.15);
    const total = amplitudes.reduce((a, b) => a + b, 0);

    amplitudes.forEach((amplitude, i) => {
      const n = i + 1;
      const hz = n * fundamental * Math.sqrt(1 + INHARMONICITY * n * n);
      if (hz > ctx.sampleRate / 2) return;
      const oscillator = ctx.createOscillator();
      oscillator.frequency.value = hz;
      const partial = ctx.createGain();
      const start = (amplitude / total) * (note.attack ? 1 : JOINED_LEVEL);
      partial.gain.setValueAtTime(start, note.when);
      partial.gain.setTargetAtTime(0, note.when, ring / (1 + 0.8 * (n - 1)));
      oscillator.connect(partial).connect(env);
      oscillator.start(note.when);
      oscillator.stop(stopAt);
      if (n === 1) disconnectWhenEnded(oscillator, env);
    });

    if (note.attack) {
      const thump = ctx.createBiquadFilter();
      thump.type = "lowpass";
      thump.frequency.value = HAMMER.cutoff;
      thump.Q.value = 0;
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(HAMMER.gain, note.when);
      gain.gain.setTargetAtTime(0, note.when, HAMMER.decay);
      noiseSource(ctx, note.when, Math.min(stopAt, note.when + HAMMER.length)).connect(thump).connect(gain).connect(env);
    }
  }
}
