import { AdditiveInstrument } from "./additive";
import { ChoirInstrument } from "./choir";
import { PianoInstrument } from "./piano";
import { StringsInstrument } from "./strings";
import type { Instrument } from "./types";

export type { Instrument, NoteEvent } from "./types";
export { midiToHz } from "./types";

/**
 * The `level` of each instrument is its peak gain, chosen so that they are about equally loud
 * (a modelled RMS of `TARGET_RMS`, see `instruments.test.ts`): switching instruments should change
 * the timbre, not the volume.
 */
export const INSTRUMENTS: readonly Instrument[] = [
  new PianoInstrument(0.729),
  new ChoirInstrument({
    id: "choir",
    label: "Choir ooh",
    level: 1.285,
    formants: [
      { freq: 300, q: 4, gain: 1 },
      { freq: 870, q: 6, gain: 0.5 },
      { freq: 2240, q: 8, gain: 0.15 },
    ],
  }),
  new ChoirInstrument({
    id: "choir-aah",
    label: "Choir aah",
    level: 1.376,
    formants: [
      { freq: 730, q: 5, gain: 1 },
      { freq: 1090, q: 6, gain: 0.7 },
      { freq: 2440, q: 8, gain: 0.25 },
    ],
  }),
  new StringsInstrument(0.443),
  new AdditiveInstrument({
    id: "organ",
    label: "Organ",
    harmonics: [1, 0.6, 0.5, 0.35, 0.2],
    envelope: { attack: 0.012, release: 0.06 },
    level: 0.507,
  }),
  new AdditiveInstrument({
    id: "flute",
    label: "Flute",
    harmonics: [1, 0.16, 0.05],
    envelope: { attack: 0.07, release: 0.12 },
    level: 0.304,
    vibrato: { hz: 5, cents: 10, delay: 0.4, ramp: 0.4 },
    breath: { level: 0.18, centre: 3, q: 1.5 },
  }),
];

/** What every voice plays until it is changed, and in the practice-set export. */
export const DEFAULT_INSTRUMENT_ID = "piano";

export function instrumentById(id: string): Instrument {
  const found = INSTRUMENTS.find((i) => i.id === id);
  if (!found) throw new Error(`no instrument ${JSON.stringify(id)}; have ${INSTRUMENTS.map((i) => i.id)}`);
  return found;
}
