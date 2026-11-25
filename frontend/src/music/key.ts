import type { Key } from "../api/types";

/** Tonics offered when choosing a key (flats and sharps spelled the way people write them). */
export const TONICS = ["C", "C#", "Db", "D", "Eb", "E", "F", "F#", "Gb", "G", "Ab", "A", "Bb", "B"] as const;

const NATURAL_PITCH_CLASSES: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

/** Pitch class (0-11, C = 0) of a tonic spelled like "Bb" or "F#". */
export function tonicPitchClass(tonic: string): number {
  const natural = NATURAL_PITCH_CLASSES[tonic[0] ?? ""];
  const accidental = tonic.slice(1);
  if (natural === undefined || !["", "#", "b"].includes(accidental)) {
    throw new Error(`not a tonic: ${JSON.stringify(tonic)}`);
  }
  const shift = accidental === "#" ? 1 : accidental === "b" ? -1 : 0;
  return (natural + shift + 12) % 12;
}

/** "Bb major", or "no key". */
export function keyLabel(key: Key | null | undefined): string {
  return key ? `${key.tonic} ${key.mode}` : "no key";
}
