import type { Piece } from "../api/types";
import { usePlaybackPosition, usePlayerState } from "../audio/hooks";
import type { Player } from "../audio/player";
import { describeSection } from "../music/sections";

export function SectionStrip({ piece, player }: { piece: Piece; player: Player }) {
  const { status } = usePlayerState(player);
  const { sectionId } = usePlaybackPosition(player);

  return (
    <section>
      <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-400">Sections</h3>
      <ul className="flex flex-wrap gap-2">
        {piece.sections.map((section) => {
          const current = status !== "stopped" && section.id === sectionId;
          return (
            <li key={section.id}>
              <button
                type="button"
                onClick={() => void player.playFromSection(section.id)}
                aria-current={current ? "true" : undefined}
                title="Play from here"
                className={`rounded-md border px-3 py-2 text-left transition ${
                  current
                    ? "border-amber-400 bg-amber-400/15 text-amber-200"
                    : "border-zinc-800 bg-zinc-900 hover:border-zinc-600"
                }`}
              >
                <div className="text-sm font-medium">{section.name}</div>
                <div className="text-xs text-zinc-400">bars {describeSection(piece, section)}</div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
