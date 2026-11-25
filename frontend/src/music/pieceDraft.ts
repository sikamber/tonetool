import type { Key, Piece, PieceEdits, Section, VoiceKind } from "../api/types";

export type Segment = Section["segments"][number];

export const VOICE_KINDS: readonly VoiceKind[] = ["S", "A", "T", "B", "other"];

export type RangeParse = { ok: true; segments: Segment[] } | { ok: false; error: string };

/**
 * Bar ranges as a person types them: "1-12, 15". Bars count from 1 by position in the score
 * (the first bar is 1, even if it is printed as 0), and a range includes both ends.
 */
export function parseRanges(text: string, measureCount: number): RangeParse {
  const parts = text.split(/[,;]/).map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return { ok: false, error: "Enter at least one bar range, e.g. 1-12" };
  const segments: Segment[] = [];
  for (const part of parts) {
    const match = /^(\d+)\s*(?:-\s*(\d+))?$/.exec(part);
    if (!match) return { ok: false, error: `"${part}" is not a bar or a range like 1-12` };
    const first = Number(match[1]);
    const last = match[2] === undefined ? first : Number(match[2]);
    if (first < 1 || last < 1) return { ok: false, error: "Bars start at 1" };
    if (first > last) return { ok: false, error: `"${part}" runs backwards` };
    if (last > measureCount) return { ok: false, error: `Bar ${last} is past the last bar (${measureCount})` };
    segments.push({ start: first - 1, end: last - 1 });
  }
  return { ok: true, segments };
}

/** The inverse of `parseRanges`. */
export function formatRanges(segments: readonly Segment[]): string {
  return segments.map(({ start, end }) => (start === end ? `${start + 1}` : `${start + 1}-${end + 1}`)).join(", ");
}

export function sameSegments(a: readonly Segment[], b: readonly Segment[]): boolean {
  return a.length === b.length && a.every((s, i) => s.start === b[i]!.start && s.end === b[i]!.end);
}

/**
 * A piece being edited: the saved piece plus the changes made so far. Immutable, so every operation
 * returns a new draft (which suits React state). Only what the server accepts as an edit can change:
 * title, key, track labels and voice kinds, and the sections. Notes, lyrics and tempo cannot.
 *
 * The server validates the result when it is saved; the rules about sections (ranges, ids) are not
 * repeated here beyond what is needed to turn typed input into values.
 */
export class PieceDraft {
  private constructor(
    readonly saved: Piece,
    readonly piece: Piece,
  ) {}

  static from(piece: Piece): PieceDraft {
    return new PieceDraft(piece, piece);
  }

  /** Whether the draft differs from the saved piece (changing something back clears it). */
  get dirty(): boolean {
    return JSON.stringify(PieceDraft.editsOf(this.piece)) !== JSON.stringify(PieceDraft.editsOf(this.saved));
  }

  /** The body for saving this draft. */
  toEdits(): PieceEdits {
    return PieceDraft.editsOf(this.piece);
  }

  /** Throw the changes away. */
  revert(): PieceDraft {
    return PieceDraft.from(this.saved);
  }

  /** The same draft, now based on `saved` (what the server answered when the draft was saved). */
  savedAs(saved: Piece): PieceDraft {
    return PieceDraft.from(saved);
  }

  setTitle(title: string): PieceDraft {
    return this.with({ title });
  }

  /** Sets the tonal key; null for "not set". */
  setKey(key: Key | null): PieceDraft {
    return this.with({ key });
  }

  setTrack(trackId: string, change: { label?: string; voice?: VoiceKind }): PieceDraft {
    return this.with({ tracks: this.piece.tracks.map((t) => (t.id === trackId ? { ...t, ...change } : t)) });
  }

  /** Appends a section over the whole piece (a valid starting point to narrow down). */
  addSection(): PieceDraft {
    const count = this.piece.sections.length + 1;
    const section: Section = {
      id: this.freeSectionId(),
      name: `Section ${count}`,
      segments: [{ start: 0, end: this.piece.measures.length - 1 }],
      source: "user",
      lyric_number: null,
    };
    return this.with({ sections: [...this.piece.sections, section] });
  }

  /** Removes a section. A piece needs at least one, so the last one stays. */
  removeSection(id: string): PieceDraft {
    if (this.piece.sections.length <= 1) return this;
    return this.with({ sections: this.piece.sections.filter((s) => s.id !== id) });
  }

  /** Moves a section earlier (-1) or later (+1) in the performance order. */
  moveSection(id: string, delta: -1 | 1): PieceDraft {
    const sections = [...this.piece.sections];
    const from = sections.findIndex((s) => s.id === id);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= sections.length) return this;
    [sections[from], sections[to]] = [sections[to]!, sections[from]!];
    return this.with({ sections });
  }

  renameSection(id: string, name: string): PieceDraft {
    return this.changeSection(id, { name });
  }

  setSegments(id: string, segments: Segment[]): PieceDraft {
    return this.changeSection(id, { segments });
  }

  setLyricNumber(id: string, lyricNumber: string | null): PieceDraft {
    return this.changeSection(id, { lyric_number: lyricNumber });
  }

  /** The lyric lines (as `Lyric.number`) that the bars of a section carry, lowest first. */
  availableLyricNumbers(sectionId: string): string[] {
    const section = this.piece.sections.find((s) => s.id === sectionId);
    if (!section) return [];
    const numbers = new Set<string>();
    for (const { start, end } of section.segments) {
      for (const measure of this.piece.measures.slice(start, end + 1)) {
        for (const voice of Object.values(measure.voices ?? {})) {
          for (const note of voice.notes ?? []) for (const lyric of note.lyrics ?? []) numbers.add(lyric.number);
        }
      }
    }
    return [...numbers].sort((a, b) => Number(a) - Number(b) || a.localeCompare(b));
  }

  private static editsOf(piece: Piece): PieceEdits {
    return {
      title: piece.title,
      key: piece.key ?? null,
      tracks: piece.tracks.map((t) => ({ id: t.id, label: t.label, voice: t.voice })),
      sections: piece.sections,
    };
  }

  private with(change: Partial<Piece>): PieceDraft {
    return new PieceDraft(this.saved, { ...this.piece, ...change });
  }

  private changeSection(id: string, change: Partial<Section>): PieceDraft {
    return this.with({ sections: this.piece.sections.map((s) => (s.id === id ? { ...s, ...change } : s)) });
  }

  private freeSectionId(): string {
    const taken = new Set(this.piece.sections.map((s) => s.id));
    let n = this.piece.sections.length + 1;
    while (taken.has(`s${n}`)) n += 1;
    return `s${n}`;
  }
}
