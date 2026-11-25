/**
 * Unrolling: apply a piece's sections to its measures to get absolute-time events.
 *
 * A port of `src/tonetool/timeline.py`. This is the one place on the frontend that knows how to turn
 * notated structure into performance time. Differences from the Python version: the sequence is
 * built section by section (so every span knows its section), and notes are sorted by start time.
 */
import type { Measure, Piece, Section } from "../api/types";

export interface MeasureSpan {
  position: number; // 0-based position in the performed sequence
  sourceMeasure: number; // notated measure index
  sectionId: string;
  startSec: number;
  endSec: number;
  beatSecs: number;
  beats: number;
}

export interface ScheduledNote {
  trackId: string;
  pitch: number;
  startSec: number;
  durationSec: number;
  sourceMeasure: number;
  position: number;
  sectionId: string;
  /** False: enters a note that is already held, so no re-strike is wanted. */
  attack: boolean;
}

export interface SectionSpan {
  id: string;
  name: string;
  startSec: number;
  endSec: number;
}

export class Timeline {
  constructor(
    readonly spans: readonly MeasureSpan[],
    readonly notes: readonly ScheduledNote[],
    readonly sections: readonly SectionSpan[],
  ) {}

  /** Total length in seconds. */
  get duration(): number {
    return this.spans.at(-1)?.endSec ?? 0;
  }

  /** The performed measure sounding at `seconds` (for cursor following). */
  spanAt(seconds: number): MeasureSpan {
    const index = Math.max(0, lastIndexAtOrBefore(this.spans, seconds));
    return this.spans[index]!;
  }

  /** The section sounding at `seconds`. */
  sectionAt(seconds: number): SectionSpan {
    const index = Math.max(0, lastIndexAtOrBefore(this.sections, seconds));
    return this.sections[index]!;
  }

  /** When a section starts, in seconds. */
  sectionStart(sectionId: string): number {
    const found = this.sections.find((s) => s.id === sectionId);
    if (!found) {
      throw new Error(`no section ${JSON.stringify(sectionId)}; have ${this.sections.map((s) => s.id)}`);
    }
    return found.startSec;
  }

  notesFor(trackId: string): ScheduledNote[] {
    return this.notes.filter((n) => n.trackId === trackId);
  }
}

/** Index of the last item whose `startSec` is <= `seconds` (-1 if there is none). */
function lastIndexAtOrBefore(items: readonly { startSec: number }[], seconds: number): number {
  let low = 0;
  let high = items.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (items[mid]!.startSec <= seconds) low = mid + 1;
    else high = mid;
  }
  return low - 1;
}

/** Length of one metronome beat in quarter notes (compound meters beat in dotted units). */
export function beatLength(measure: Pick<Measure, "beat_unit" | "beats_per_bar">): number {
  if (measure.beat_unit === 8 && measure.beats_per_bar % 3 === 0 && measure.beats_per_bar > 3) {
    return 1.5;
  }
  return 4 / measure.beat_unit;
}

/** The tempo of every measure in quarter-note BPM. A mark carries forward in *notated* order. */
export function measureBpms(piece: Piece): number[] {
  let current = 0;
  return piece.measures.map((measure) => {
    if (measure.tempo != null) current = measure.tempo;
    return current;
  });
}

const EPSILON = 1e-6;

/**
 * Builds a `Timeline` from a piece. `tempoScale` multiplies the notated tempo (0.8 = 20% slower).
 *
 * Ties are resolved in *performed* order. A note flagged `tied` extends the held note of the same
 * pitch if that note ends exactly where this one starts (any chain length, across barlines, voltas
 * and jumps). If there is nothing to continue (a jump or loop point landed mid-tie), it sounds for
 * its own duration without an attack, as a singer entering a held note.
 */
export class TimelineBuilder {
  constructor(
    private readonly piece: Piece,
    private readonly tempoScale = 1,
  ) {
    if (!(tempoScale > 0)) throw new Error("tempoScale must be positive");
  }

  build(): Timeline {
    const bpms = measureBpms(this.piece);
    const spans: MeasureSpan[] = [];
    const notes: ScheduledNote[] = [];
    const sections: SectionSpan[] = [];
    const held = new Map<string, ScheduledNote>(); // `${track}:${pitch}` -> latest note of that pitch
    let clock = 0;
    let position = 0;

    for (const section of this.piece.sections) {
      const sectionStart = clock;
      for (const index of this.measureSequence(section)) {
        const measure = this.piece.measures[index]!;
        const secondsPerQuarter = 60 / (bpms[index]! * this.tempoScale);
        const lengthSec = measure.length * secondsPerQuarter;
        const beat = beatLength(measure);
        spans.push({
          position,
          sourceMeasure: index,
          sectionId: section.id,
          startSec: clock,
          endSec: clock + lengthSec,
          beatSecs: beat * secondsPerQuarter,
          beats: Math.max(1, Math.round(measure.length / beat)),
        });
        for (const [trackId, voice] of Object.entries(measure.voices ?? {})) {
          for (const note of voice.notes ?? []) {
            const startSec = clock + note.offset * secondsPerQuarter;
            const durationSec = note.duration * secondsPerQuarter;
            if (durationSec <= 0) continue;
            const key = `${trackId}:${note.pitch}`;
            const previous = held.get(key);
            if (note.tied && previous && Math.abs(previous.startSec + previous.durationSec - startSec) < EPSILON) {
              previous.durationSec += durationSec;
              continue;
            }
            const scheduled: ScheduledNote = {
              trackId,
              pitch: note.pitch,
              startSec,
              durationSec,
              sourceMeasure: index,
              position,
              sectionId: section.id,
              attack: !note.tied,
            };
            notes.push(scheduled);
            held.set(key, scheduled);
          }
        }
        clock += lengthSec;
        position += 1;
      }
      sections.push({ id: section.id, name: section.name, startSec: sectionStart, endSec: clock });
    }
    notes.sort((a, b) => a.startSec - b.startSec);
    return new Timeline(spans, notes, sections);
  }

  private measureSequence(section: Section): number[] {
    const count = this.piece.measures.length;
    const sequence: number[] = [];
    for (const { start, end } of section.segments) {
      if (start < 0 || end >= count) {
        throw new Error(`section ${section.id}: segment ${start}-${end} outside 0-${count - 1}`);
      }
      for (let m = start; m <= end; m++) sequence.push(m);
    }
    return sequence;
  }
}
