import { useMemo, useState } from "react";
import type { Piece } from "../api/types";
import type { Player } from "../audio/player";
import { usePlayerState } from "../audio/hooks";
import type { AudioFormat } from "../export/encoders";
import { downloadFile, PracticeExporter, type ExportedFile } from "../export/practiceExporter";

export function ExportPanel({ piece, player }: { piece: Piece; player: Player }) {
  const state = usePlayerState(player);
  const exporter = useMemo(() => new PracticeExporter(piece), [piece]);
  const [format, setFormat] = useState<AudioFormat>("mp3");
  const [status, setStatus] = useState<string | null>(null); // non-null while working
  const [error, setError] = useState<string | null>(null);
  const busy = status !== null;

  const run = async (label: string, job: () => Promise<ExportedFile>) => {
    setError(null);
    setStatus(label);
    try {
      downloadFile(await job());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStatus(null);
    }
  };

  const button =
    "rounded-md border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:cursor-wait disabled:opacity-50";

  return (
    <section>
      <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-400">Download</h3>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <button
          type="button"
          disabled={busy}
          className={button}
          onClick={() => run("Rendering…", () => exporter.single(state, format))}
        >
          Current mix
        </button>
        <button
          type="button"
          disabled={busy}
          className={button}
          onClick={() =>
            run("Rendering…", () =>
              exporter.zip(format, (done, total, name) =>
                setStatus(done < total ? `Rendering ${done + 1} of ${total}: ${name}` : "Zipping…"),
              ),
            )
          }
        >
          Practice set (zip)
        </button>
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          Format
          <select
            value={format}
            disabled={busy}
            onChange={(e) => setFormat(e.target.value as AudioFormat)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1"
          >
            <option value="mp3">MP3</option>
            <option value="wav">WAV (large)</option>
          </select>
        </label>
        <span role="status" className="text-sm text-zinc-400">
          {status}
        </span>
        {error && <span className="text-sm text-red-400">Export failed: {error}</span>}
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        "Current mix" uses the mixer and tempo as set now. The zip ignores them: it always has the tutti
        plus each voice alone, prominent and left-vs-right, at the notated tempo.
      </p>
    </section>
  );
}
