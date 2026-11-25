import type { PieceSummary } from "../api/types";

interface Props {
  pieces: PieceSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function PieceList({ pieces, selectedId, onSelect }: Props) {
  if (pieces.length === 0) {
    return <p className="text-zinc-400">No pieces configured. Add some to tonetool.toml.</p>;
  }
  return (
    <ul className="mb-8 grid gap-2 sm:grid-cols-2">
      {pieces.map((piece) => {
        const selected = piece.id === selectedId;
        return (
          <li key={piece.id}>
            <button
              type="button"
              disabled={piece.error != null}
              onClick={() => onSelect(piece.id)}
              aria-pressed={selected}
              className={`w-full rounded-lg border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                selected
                  ? "border-amber-400 bg-zinc-900"
                  : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-600"
              }`}
            >
              <div className="font-medium">{piece.title}</div>
              <div className="text-xs text-zinc-400">
                {piece.error
                  ? piece.error
                  : `${piece.tracks.map((t) => t.label).join(" · ")} — ${piece.section_count} sections`}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
