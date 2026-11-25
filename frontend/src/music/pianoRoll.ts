import type { KeyColors, NoteColor } from "./keyColors";
import type { Timeline } from "./timeline";

export interface PianoRollOptions {
  pixelsPerSecond: number;
  rowHeight: number;
  /** Track ids to draw; all of them if omitted. The pitch range always covers every track. */
  visibleTracks?: ReadonlySet<string>;
}

export interface NoteRect {
  x: number;
  y: number;
  width: number;
  height: number;
  trackId: string;
  pitch: number;
  color: NoteColor;
}

export interface PitchRow {
  pitch: number;
  y: number;
  /** "C4" on C rows, otherwise null. */
  label: string | null;
  isBlackKey: boolean;
  isTonic: boolean;
}

export interface SectionMark {
  id: string;
  name: string;
  x: number;
}

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const BLACK_KEYS = new Set([1, 3, 6, 8, 10]);
const MIN_RANGE = 12; // at least an octave of rows
const GAP = 1; // pixels between notes that follow each other

/** Name of a MIDI pitch with its octave: 60 is "C4". */
export const pitchName = (pitch: number): string => `${NOTE_NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;

/**
 * Where everything goes in a piano roll: time runs to the right, pitch upwards, in pixels.
 *
 * Pure geometry, so it can be tested without a canvas. Rectangles are in x order, which lets the
 * view find the ones in a scrolled window by binary search instead of looking at every note.
 */
export class PianoRollLayout {
  readonly rects: readonly NoteRect[];
  readonly rows: readonly PitchRow[];
  readonly sections: readonly SectionMark[];
  readonly lowPitch: number;
  readonly highPitch: number;
  readonly width: number;
  readonly height: number;
  private readonly widest: number;

  constructor(
    timeline: Timeline,
    colors: KeyColors,
    private readonly options: PianoRollOptions,
  ) {
    const { pixelsPerSecond, rowHeight, visibleTracks } = options;
    const pitches = timeline.notes.map((n) => n.pitch);
    const low = pitches.length ? Math.min(...pitches) - 1 : 59;
    const high = pitches.length ? Math.max(...pitches) + 1 : 72;
    const missing = Math.max(0, MIN_RANGE - (high - low));
    this.lowPitch = Math.max(0, low - Math.floor(missing / 2));
    this.highPitch = Math.min(127, high + Math.ceil(missing / 2));
    this.height = (this.highPitch - this.lowPitch + 1) * rowHeight;
    this.width = Math.max(1, timeline.duration * pixelsPerSecond);

    this.rects = timeline.notes
      .filter((n) => !visibleTracks || visibleTracks.has(n.trackId))
      .map((n) => ({
        x: n.startSec * pixelsPerSecond,
        y: (this.highPitch - n.pitch) * rowHeight,
        width: Math.max(2, n.durationSec * pixelsPerSecond - GAP),
        height: rowHeight - GAP,
        trackId: n.trackId,
        pitch: n.pitch,
        color: colors.colorOf(n.pitch),
      }));
    this.widest = this.rects.reduce((w, r) => Math.max(w, r.width), 0);

    const rows: PitchRow[] = [];
    for (let pitch = this.highPitch; pitch >= this.lowPitch; pitch--) {
      rows.push({
        pitch,
        y: (this.highPitch - pitch) * rowHeight,
        label: pitch % 12 === 0 ? pitchName(pitch) : null,
        isBlackKey: BLACK_KEYS.has(pitch % 12),
        isTonic: colors.hasKey && colors.offsetOf(pitch) === 0,
      });
    }
    this.rows = rows;
    this.sections = timeline.sections.map((s) => ({ id: s.id, name: s.name, x: s.startSec * pixelsPerSecond }));
  }

  get rowHeight(): number {
    return this.options.rowHeight;
  }

  timeToX(seconds: number): number {
    return seconds * this.options.pixelsPerSecond;
  }

  xToTime(x: number): number {
    return x / this.options.pixelsPerSecond;
  }

  /** The notes that overlap the horizontal window [x0, x1]. */
  rectsBetween(x0: number, x1: number): NoteRect[] {
    const first = this.firstIndexAtOrAfter(x0 - this.widest);
    const found: NoteRect[] = [];
    for (let i = first; i < this.rects.length; i++) {
      const rect = this.rects[i]!;
      if (rect.x >= x1) break;
      if (rect.x + rect.width >= x0) found.push(rect);
    }
    return found;
  }

  private firstIndexAtOrAfter(x: number): number {
    let low = 0;
    let high = this.rects.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (this.rects[mid]!.x >= x) high = mid;
      else low = mid + 1;
    }
    return low;
  }
}
