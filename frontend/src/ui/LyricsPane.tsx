import { useMemo, useState } from "react";
import type { Piece } from "../api/types";
import { usePlaybackPosition, usePlayerState } from "../audio/hooks";
import type { Player } from "../audio/player";
import { LyricsView, type LyricLine, type LyricSyllable } from "../music/lyrics";

export function LyricsPane({ piece, player }: { piece: Piece; player: Player }) {
  const { status, tempoScale } = usePlayerState(player);
  const { seconds } = usePlaybackPosition(player);

  // The timeline is rebuilt when the tempo changes, so the views follow it.
  const views = useMemo(
    () => piece.tracks.map((t) => new LyricsView(player.getTimeline(), t.id)).filter((v) => !v.isEmpty),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [piece, player, tempoScale],
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const view = views.find((v) => v.trackId === chosen) ?? views[0];
  if (!view) return null;

  const labels = new Map(piece.tracks.map((t) => [t.id, t.label]));
  const index = view.lineIndexAt(seconds);
  const line = view.lines[index]!;
  const previous = view.lines[index - 1];
  const next = view.lines[index + 1];
  const sung = status === "stopped" ? null : view.syllableAt(seconds);

  return (
    <section>
      <div className="mb-2 flex items-center justify-between gap-4">
        <h3 className="text-sm font-medium uppercase tracking-wide text-zinc-400">Lyrics</h3>
        {views.length > 1 && (
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            Follow
            <select
              value={view.trackId}
              onChange={(e) => setChosen(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
            >
              {views.map((v) => (
                <option key={v.trackId} value={v.trackId}>
                  {labels.get(v.trackId) ?? v.trackId}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        {previous && (
          <Line
            line={previous}
            current={null}
            onSeek={(s) => player.seek(s)}
            size="small"
            tone="past"
            showSection={previous.section.id !== line.section.id}
          />
        )}
        <Line line={line} current={sung} onSeek={(s) => player.seek(s)} size="large" showSection />
        {next && (
          <Line
            line={next}
            current={null}
            onSeek={(s) => player.seek(s)}
            size="small"
            tone="upcoming"
            showSection={next.section.id !== line.section.id}
          />
        )}
      </div>
    </section>
  );
}

function Line({
  line,
  current,
  onSeek,
  size,
  tone = "upcoming",
  showSection,
}: {
  line: LyricLine;
  current: LyricSyllable | null;
  onSeek: (seconds: number) => void;
  size: "large" | "small";
  /** For small lines: a line already sung is dimmer than one still to come. */
  tone?: "past" | "upcoming";
  showSection: boolean;
}) {
  const large = size === "large";
  return (
    <div>
      {showSection && (
        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">{line.section.name}</div>
      )}
      <p
        className={
          large
            ? "text-2xl leading-relaxed"
            : `text-base leading-relaxed ${tone === "past" ? "text-zinc-600" : "text-zinc-500"}`
        }
      >
        {line.words.map((word, w) => (
          <span key={w} className="mr-[0.4em] inline-block whitespace-nowrap">
            {word.syllables.map((syllable) => {
              const isCurrent = syllable === current;
              const done = large && current != null && syllable.startSec < current.startSec;
              return (
                <button
                  key={syllable.startSec}
                  type="button"
                  onClick={() => onSeek(syllable.startSec)}
                  title="Go here"
                  className={`rounded-sm px-px ${
                    isCurrent
                      ? "bg-amber-400 text-zinc-950"
                      : done
                        ? "text-zinc-500 hover:text-zinc-300"
                        : large
                          ? "text-zinc-100 hover:bg-zinc-800"
                          : "hover:text-zinc-300"
                  }`}
                >
                  {syllable.text}
                </button>
              );
            })}
          </span>
        ))}
      </p>
    </div>
  );
}
