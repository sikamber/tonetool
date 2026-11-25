import type { ScheduledNote, Timeline } from "./timeline";

/**
 * Walks a timeline's notes from a start position, handing out the ones that fall due.
 *
 * Starting mid-piece, notes already sounding at that moment are returned (once) by `takeHeld`, cut
 * to their remaining length and flagged without attack, as a singer joining a held note.
 */
export class PlaybackCursor {
  private readonly notes: readonly ScheduledNote[];
  private next: number;
  private held: ScheduledNote[];

  constructor(timeline: Timeline, readonly startSec: number) {
    this.notes = timeline.notes;
    const first = this.notes.findIndex((n) => n.startSec >= startSec);
    this.next = first < 0 ? this.notes.length : first;
    this.held = this.notes
      .slice(0, this.next)
      .filter((n) => n.startSec + n.durationSec > startSec + 1e-6)
      .map((n) => ({ ...n, startSec, durationSec: n.startSec + n.durationSec - startSec, attack: false }));
  }

  /** Notes already sounding at the start position (returned once). */
  takeHeld(): ScheduledNote[] {
    const held = this.held;
    this.held = [];
    return held;
  }

  /** Notes starting before `untilSec`, each returned once, in start order. */
  takeUntil(untilSec: number): ScheduledNote[] {
    const due: ScheduledNote[] = [];
    while (this.next < this.notes.length && this.notes[this.next]!.startSec < untilSec) {
      due.push(this.notes[this.next]!);
      this.next += 1;
    }
    return due;
  }
}
