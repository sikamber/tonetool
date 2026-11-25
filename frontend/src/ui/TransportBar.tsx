import { usePlaybackPosition, usePlayerState } from "../audio/hooks";
import type { Player } from "../audio/player";

const format = (seconds: number): string => {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
};

export function TransportBar({ player }: { player: Player }) {
  const { status, tempoScale } = usePlayerState(player);
  const { seconds } = usePlaybackPosition(player);
  const playing = status === "playing";

  return (
    <section className="flex flex-wrap items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <button
        type="button"
        onClick={() => (playing ? player.pause() : void player.play())}
        className="w-24 rounded-md bg-amber-400 px-4 py-2 font-medium text-zinc-950 hover:bg-amber-300"
      >
        {playing ? "Pause" : "Play"}
      </button>
      <button
        type="button"
        onClick={() => player.stop()}
        disabled={status === "stopped"}
        className="rounded-md border border-zinc-700 px-4 py-2 hover:bg-zinc-800 disabled:opacity-40"
      >
        Stop
      </button>
      <input
        type="range"
        aria-label="Position"
        min={0}
        max={player.duration}
        step={0.1}
        value={seconds}
        onChange={(e) => player.seek(Number(e.target.value))}
        className="min-w-40 flex-1"
      />
      <span className="w-24 text-right font-mono text-sm tabular-nums text-zinc-300">
        {format(seconds)} / {format(player.duration)}
      </span>
      <label className="flex items-center gap-2 text-sm text-zinc-400">
        Tempo
        <input
          type="range"
          aria-label="Tempo"
          min={0.5}
          max={1.2}
          step={0.05}
          value={tempoScale}
          onChange={(e) => player.setTempoScale(Number(e.target.value))}
          className="w-28"
        />
        <span className="w-10 font-mono tabular-nums text-zinc-300">{Math.round(tempoScale * 100)}%</span>
      </label>
    </section>
  );
}
