import { useState } from "react";
import { usePieces } from "../api/hooks";
import { ImportButton } from "./ImportButton";
import { PieceList } from "./PieceList";
import { hashForPieceId, pieceIdFromHash } from "./pieceHash";
import { PlayerPage } from "./PlayerPage";

export function App() {
  const pieces = usePieces();
  const [selectedId, setSelectedId] = useState<string | null>(() => pieceIdFromHash(location.hash));

  const select = (id: string) => {
    location.hash = hashForPieceId(id);
    setSelectedId(id);
  };
  const deselect = () => {
    history.replaceState(null, "", location.pathname + location.search);
    setSelectedId(null);
  };

  // A hash can name a piece that no longer exists (renamed in the config): ignore it, and don't
  // start loading before the list is known.
  const current = pieces.data?.find((p) => p.id === selectedId && p.error == null) ?? null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Tonetool</h1>
        <p className="text-sm text-zinc-400">Choir practice tracks</p>
      </header>
      {pieces.isPending && <p className="text-zinc-400">Loading pieces…</p>}
      {pieces.isError && <p className="text-red-400">Could not load pieces: {pieces.error.message}</p>}
      {pieces.data && <PieceList pieces={pieces.data} selectedId={current?.id ?? null} onSelect={select} />}
      {pieces.data && <ImportButton onImported={select} />}
      {current && <PlayerPage key={current.id} summary={current} onDeleted={deselect} />}
    </div>
  );
}
