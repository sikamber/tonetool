/** Instruments: how one note is turned into sound. Swappable per voice, even mid-playback. */

export interface NoteEvent {
  pitch: number; // MIDI note number
  when: number; // AudioContext time the note starts
  duration: number; // seconds
  /** False: joins a note already held, so there is no strike (and no percussive decay). */
  attack: boolean;
}

export interface Instrument {
  readonly id: string;
  readonly label: string;
  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void;
}

export interface AdditiveSpec {
  id: string;
  label: string;
  harmonics: number[]; // relative amplitude of partial 1, 2, 3, ...
  attack: number; // seconds
  release: number; // seconds
  /** Percussive instruments fall towards `sustain` (0..1 of peak) with this time constant. */
  decay?: { time: number; sustain: number };
}

/** Peak level of one note. Headroom for several voices is added by the Player's master gain. */
const NOTE_PEAK = 0.5;
/** Short fade-in when joining a held note, to avoid a click. */
const JOIN_FADE = 0.005;

export const midiToHz = (pitch: number): number => 440 * 2 ** ((pitch - 69) / 12);

/** A sum of sine partials under an attack/(decay)/release envelope. */
export class AdditiveInstrument implements Instrument {
  readonly id: string;
  readonly label: string;

  constructor(private readonly spec: AdditiveSpec) {
    this.id = spec.id;
    this.label = spec.label;
  }

  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void {
    const { harmonics, release, decay } = this.spec;
    const end = note.when + note.duration;
    const attack = note.attack ? Math.min(this.spec.attack, note.duration / 2) : JOIN_FADE;

    const envelope = ctx.createGain();
    envelope.gain.setValueAtTime(0, note.when);
    envelope.gain.linearRampToValueAtTime(NOTE_PEAK, note.when + attack);
    if (decay) {
      // A strike falls from the peak; joining a held note starts at the sustain level.
      if (note.attack) envelope.gain.setTargetAtTime(NOTE_PEAK * decay.sustain, note.when + attack, decay.time);
      else envelope.gain.setValueAtTime(NOTE_PEAK * decay.sustain, note.when + attack);
    }
    envelope.gain.setTargetAtTime(0, end, release / 5);
    envelope.connect(output);

    const total = harmonics.reduce((a, b) => a + b, 0);
    const fundamental = midiToHz(note.pitch);
    const stopAt = end + release;
    harmonics.forEach((amplitude, i) => {
      const hz = fundamental * (i + 1);
      if (hz > ctx.sampleRate / 2) return;
      const oscillator = ctx.createOscillator();
      oscillator.frequency.value = hz;
      const partial = ctx.createGain();
      partial.gain.value = amplitude / total;
      oscillator.connect(partial).connect(envelope);
      oscillator.start(note.when);
      oscillator.stop(stopAt);
      if (i === 0) oscillator.onended = () => envelope.disconnect();
    });
  }
}

export const INSTRUMENTS: readonly Instrument[] = [
  new AdditiveInstrument({ id: "choir", label: "Choir ooh", harmonics: [1, 0.45, 0.22, 0.1], attack: 0.05, release: 0.12 }),
  new AdditiveInstrument({ id: "organ", label: "Organ", harmonics: [1, 0.6, 0.5, 0.35, 0.2], attack: 0.01, release: 0.05 }),
  new AdditiveInstrument({ id: "flute", label: "Flute", harmonics: [1, 0.2, 0.05], attack: 0.04, release: 0.1 }),
  new AdditiveInstrument({
    id: "piano",
    label: "Soft piano",
    harmonics: [1, 0.5, 0.25, 0.12, 0.06],
    attack: 0.005,
    release: 0.15,
    decay: { time: 0.9, sustain: 0.15 },
  }),
];

export const DEFAULT_INSTRUMENT_ID = "choir";

export function instrumentById(id: string): Instrument {
  const found = INSTRUMENTS.find((i) => i.id === id);
  if (!found) throw new Error(`no instrument ${JSON.stringify(id)}; have ${INSTRUMENTS.map((i) => i.id)}`);
  return found;
}
