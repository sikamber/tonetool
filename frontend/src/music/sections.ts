import type { Piece, Section } from "../api/types";

/** Printed bar numbers of a section's ranges, e.g. "1-2, 4". */
export function describeSection(piece: Piece, section: Section): string {
  return section.segments
    .map(({ start, end }) => {
      const first = piece.measures[start]?.number ?? String(start);
      const last = piece.measures[end]?.number ?? String(end);
      return first === last ? first : `${first}-${last}`;
    })
    .join(", ");
}
