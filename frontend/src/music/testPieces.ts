import type { Piece } from "../api/types";

/** [pitch, offset, duration, tied?] in quarter notes. */
export type NoteSpec = [number, number, number, boolean?];

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
            { notes: (bar.notes[id] ?? []).map(([pitch, offset, duration, tied]) => ({ pitch, offset, duration, tied: tied ?? false })) },
          ]),
        ),
      };
      start += length;
      return measure;
    }),
    warnings: [],
  };
}
