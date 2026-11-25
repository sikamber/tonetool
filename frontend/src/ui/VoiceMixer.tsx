import type { Piece } from "../api/types";
import { usePlayerState } from "../audio/hooks";
import { INSTRUMENTS } from "../audio/instruments";
import type { Player } from "../audio/player";

const panLabel = (pan: number): string =>
  Math.abs(pan) < 0.05 ? "C" : `${Math.abs(Math.round(pan * 100))}${pan < 0 ? "L" : "R"}`;

export function VoiceMixer({ piece, player }: { piece: Piece; player: Player }) {
  const { voices } = usePlayerState(player);
  const labels = new Map(piece.tracks.map((t) => [t.id, t.label]));

  return (
    <section>
      <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-400">Voices</h3>
      <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800 bg-zinc-900">
        {voices.map((voice) => {
          const label = labels.get(voice.trackId) ?? voice.trackId;
          return (
            <li key={voice.trackId} className="grid grid-cols-2 items-center gap-x-4 gap-y-2 p-3 sm:grid-cols-[8rem_1fr_1fr_9rem_4rem]">
              <span className="font-medium">{label}</span>
              <label className="flex items-center gap-2 text-xs text-zinc-400">
                Vol
                <input
                  type="range"
                  aria-label={`${label} volume`}
                  min={0}
                  max={1}
                  step={0.01}
                  value={voice.volume}
                  onChange={(e) => player.setVoice(voice.trackId, { volume: Number(e.target.value) })}
                  className="flex-1"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-zinc-400">
                Pan
                <input
                  type="range"
                  aria-label={`${label} pan`}
                  min={-1}
                  max={1}
                  step={0.05}
                  value={voice.pan}
                  onChange={(e) => player.setVoice(voice.trackId, { pan: Number(e.target.value) })}
                  onDoubleClick={() => player.setVoice(voice.trackId, { pan: 0 })}
                  className="flex-1"
                />
                <span className="w-8 text-right font-mono tabular-nums">{panLabel(voice.pan)}</span>
              </label>
              <select
                aria-label={`${label} instrument`}
                value={voice.instrumentId}
                onChange={(e) => player.setVoice(voice.trackId, { instrumentId: e.target.value })}
                className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
              >
                {INSTRUMENTS.map((instrument) => (
                  <option key={instrument.id} value={instrument.id}>
                    {instrument.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-pressed={voice.muted}
                onClick={() => player.setVoice(voice.trackId, { muted: !voice.muted })}
                className={`rounded-md border px-2 py-1 text-sm ${
                  voice.muted ? "border-red-400 bg-red-400/15 text-red-200" : "border-zinc-700 hover:bg-zinc-800"
                }`}
              >
                Mute
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
