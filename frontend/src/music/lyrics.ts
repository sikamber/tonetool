import type { ScheduledNote, SectionSpan, Timeline } from "./timeline";

/** One sung syllable, with when its note starts and stops (seconds, at the timeline's tempo). */
export interface LyricSyllable {
  text: string;
  startSec: number;
  endSec: number;
}

/** Syllables written together: "Ju" "le" "træ" "et" is one word. */
export interface LyricWord {
  syllables: LyricSyllable[];
}

export interface LyricLine {
  section: SectionSpan;
  words: LyricWord[];
}

export interface SectionLyrics {
  section: SectionSpan;
  lines: LyricLine[];
}

/** Sentence-ending punctuation, after which a new line begins. */
const LINE_END = /[.!?]["')»]?$/;

/**
 * The lyrics of one voice, laid out for reading: per section, in lines of words made of syllables.
 *
 * Which syllable sounds where comes from the timeline (it already knows which lyric line each
 * section sings). A score has no line breaks, so lines are guessed: a new line starts after a word
 * that ends a sentence (. ! ?) and where the voice rests for a beat or more before the next syllable.
 */
export class LyricsView {
  readonly sections: readonly SectionLyrics[];
  /** Every line of every section, in performance order. */
  readonly lines: readonly LyricLine[];
  private readonly syllables: readonly LyricSyllable[];

  constructor(
    private readonly timeline: Timeline,
    readonly trackId: string,
  ) {
    const sections: SectionLyrics[] = [];
    const all: LyricSyllable[] = [];
    for (const section of timeline.sections) {
      const notes = timeline.notes.filter((n) => n.trackId === trackId && n.sectionId === section.id && n.syllable);
      if (notes.length === 0) continue;
      sections.push({ section, lines: this.layOut(notes, section) });
      all.push(...sections.at(-1)!.lines.flatMap((l) => l.words.flatMap((w) => w.syllables)));
    }
    this.sections = sections;
    this.lines = sections.flatMap((s) => s.lines);
    this.syllables = all;
  }

  get isEmpty(): boolean {
    return this.syllables.length === 0;
  }

  /** The syllable being sung at `seconds`: the last one that has started, or null before the first. */
  syllableAt(seconds: number): LyricSyllable | null {
    let low = 0;
    let high = this.syllables.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (this.syllables[mid]!.startSec <= seconds) low = mid + 1;
      else high = mid;
    }
    return low === 0 ? null : this.syllables[low - 1]!;
  }

  /** Index in `lines` of the line being sung at `seconds`: the last one that has started (0 before the first). */
  lineIndexAt(seconds: number): number {
    let low = 0;
    let high = this.lines.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (this.lines[mid]!.words[0]!.syllables[0]!.startSec <= seconds) low = mid + 1;
      else high = mid;
    }
    return Math.max(0, low - 1);
  }

  private layOut(notes: ScheduledNote[], section: SectionSpan): LyricLine[] {
    const lines: LyricLine[] = [];
    let line: LyricLine = { section, words: [] };
    let word: LyricWord | null = null;
    let previous: ScheduledNote | null = null;
    for (const note of notes) {
      const syllable: LyricSyllable = {
        text: note.syllable!.text,
        startSec: note.startSec,
        endSec: note.startSec + note.durationSec,
      };
      if (word && previous?.syllable?.continues) {
        word.syllables.push(syllable); // the word goes on
      } else {
        if (previous && this.startsNewLine(previous, note, line)) {
          lines.push(line);
          line = { section, words: [] };
        }
        word = { syllables: [syllable] };
        line.words.push(word);
      }
      previous = note;
    }
    if (line.words.length > 0) lines.push(line);
    return lines;
  }

  private startsNewLine(previous: ScheduledNote, next: ScheduledNote, line: LyricLine): boolean {
    const lastWord = line.words.at(-1)!.syllables.map((s) => s.text).join("");
    if (LINE_END.test(lastWord)) return true;
    const rest = next.startSec - (previous.startSec + previous.durationSec);
    return rest >= this.timeline.spanAt(next.startSec).beatSecs - 1e-6;
  }
}
