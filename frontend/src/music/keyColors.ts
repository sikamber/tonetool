import type { Key } from "../api/types";
import { tonicPitchClass } from "./key";

/** How a step relates to the plain scale step above or below it: ra is a lowered re, fi a raised fa. */
export type Alteration = "lowered" | "natural" | "raised";

export interface NoteColor {
  /** Solfège name of the step ("do", "me", ...); empty when there is no key. */
  syllable: string;
  hue: number;
  saturation: number;
  lightness: number;
  /** Whether the note belongs to the key's scale. Outside notes are drawn with an outline. */
  inKey: boolean;
  /** `hsl(...)` string, ready for canvas and CSS. */
  css: string;
}

interface Step {
  syllable: string;
  hue: number;
  alteration: Alteration;
}

// Seven hues from red (do) to pink (ti), with la purple. A lowered step shares the hue of the step it lowers, but
// darker (mi and me are one colour, mi the brighter); a raised step is brighter.
const HUES = { do: 0, re: 30, mi: 55, fa: 130, sol: 190, la: 280, ti: 330 } as const;

/** The twelve semitone offsets from the tonic. */
const STEPS: readonly Step[] = [
  { syllable: "do", hue: HUES.do, alteration: "natural" },
  { syllable: "ra", hue: HUES.re, alteration: "lowered" },
  { syllable: "re", hue: HUES.re, alteration: "natural" },
  { syllable: "me", hue: HUES.mi, alteration: "lowered" },
  { syllable: "mi", hue: HUES.mi, alteration: "natural" },
  { syllable: "fa", hue: HUES.fa, alteration: "natural" },
  { syllable: "fi", hue: HUES.fa, alteration: "raised" },
  { syllable: "sol", hue: HUES.sol, alteration: "natural" },
  { syllable: "le", hue: HUES.la, alteration: "lowered" },
  { syllable: "la", hue: HUES.la, alteration: "natural" },
  { syllable: "te", hue: HUES.ti, alteration: "lowered" },
  { syllable: "ti", hue: HUES.ti, alteration: "natural" },
];

const LIGHTNESS: Record<Alteration, number> = { lowered: 38, natural: 56, raised: 72 };
const SATURATION: Record<Alteration, number> = { lowered: 70, natural: 75, raised: 80 };

const MAJOR_SCALE = new Set([0, 2, 4, 5, 7, 9, 11]);
// natural minor plus the leading tone
const MINOR_SCALE = new Set([0, 2, 3, 5, 7, 8, 10, 11]);

const NEUTRAL: NoteColor = { syllable: "", hue: 215, saturation: 15, lightness: 56, inKey: true, css: "hsl(215 15% 56%)" };

const make = (step: Step, inKey: boolean): NoteColor => {
  const saturation = SATURATION[step.alteration];
  const lightness = LIGHTNESS[step.alteration];
  return { syllable: step.syllable, hue: step.hue, saturation, lightness, inKey, css: `hsl(${step.hue} ${saturation}% ${lightness}%)` };
};

/**
 * Colours notes by their place in a key: red for do (the tonic) through to pink for ti (la is purple).
 *
 * The colour depends only on the interval from the tonic, so major and minor keys share it
 * ("do-based" minor): the minor third is a darker *mi*, i.e. *me*. The mode only decides which notes
 * count as in the key. With no key, every note is the same neutral colour.
 */
export class KeyColors {
  private readonly tonic: number | null;
  private readonly scale: ReadonlySet<number>;

  constructor(key: Key | null | undefined) {
    this.tonic = key ? tonicPitchClass(key.tonic) : null;
    this.scale = key?.mode === "minor" ? MINOR_SCALE : MAJOR_SCALE;
  }

  /** Whether there is a key to colour by. */
  get hasKey(): boolean {
    return this.tonic !== null;
  }

  /** Semitones above the tonic, 0-11, of a MIDI pitch (any octave). */
  offsetOf(pitch: number): number {
    return (((pitch - (this.tonic ?? 0)) % 12) + 12) % 12;
  }

  /** The colour of a MIDI pitch. */
  colorOf(pitch: number): NoteColor {
    if (this.tonic === null) return NEUTRAL;
    const offset = this.offsetOf(pitch);
    return make(STEPS[offset]!, this.scale.has(offset));
  }

  /** The colours of the notes in the key's scale, from the tonic up: for a legend. None without a key. */
  legend(): NoteColor[] {
    if (this.tonic === null) return [];
    return [...this.scale].sort((a, b) => a - b).map((offset) => make(STEPS[offset]!, true));
  }
}
