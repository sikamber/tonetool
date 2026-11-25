import type { Piece } from "../api/types";

/** A syllable on a lyric line: ["1", "Ju", "begin"]. */
export type LyricSpec = [number: string, text: string, syllabic?: "single" | "begin" | "middle" | "end"];

/** [pitch, offset, duration, tied?, lyrics?] in quarter notes. */
export type NoteSpec = [number, number, number, boolean?, LyricSpec[]?];

export interface BarSpec {
  notes: Record<string, NoteSpec[]>; // track id -> notes
  tempo?: number;
  beats?: [number, number]; // [beats per bar, beat unit]
}

/** Builds a Piece for tests: 4/4 bars unless a bar says otherwise; sections as [start, end][] lists. */
export function makePiece(opts: {
  tracks?: string[];
  bars: BarSpec[];
  sections: [number, number][][];
  /** The lyric line each section sings, by section index (omitted or null: none). */
  lyricNumbers?: (string | null)[];
  tempo?: number;
}): Piece {
  const tracks = opts.tracks ?? ["T0"];
  let start = 0;
  return {
    schema_version: 3,
    title: "Test",
    source_file: "test.musicxml",
    xml_sha256: "",
    tracks: tracks.map((id) => ({ id, label: id, voice: "other" })),
    sections: opts.sections.map((segments, i) => ({
      id: `s${i + 1}`,
      name: `S${i + 1}`,
      source: "auto",
      lyric_number: opts.lyricNumbers?.[i] ?? null,
      segments: segments.map(([s, e]) => ({ start: s, end: e })),
    })),
    measures: opts.bars.map((bar, index) => {
      const [beats, unit] = bar.beats ?? [4, 4];
      const length = (beats * 4) / unit;
      const measure = {
        index,
        number: String(index + 1),
        start,
        length,
        tempo: bar.tempo ?? (index === 0 ? (opts.tempo ?? 120) : null),
        beats_per_bar: beats,
        beat_unit: unit,
        voices: Object.fromEntries(
          tracks.map((id) => [
            id,
            { notes: (bar.notes[id] ?? []).map(([pitch, offset, duration, tied, lyrics]) => ({
              pitch,
              offset,
              duration,
              tied: tied ?? false,
              lyrics: (lyrics ?? []).map(([number, text, syllabic]) => ({ number, text, syllabic: syllabic ?? "single" })),
            })) },
          ]),
        ),
      };
      start += length;
      return measure;
    }),
    warnings: [],
  };
}
