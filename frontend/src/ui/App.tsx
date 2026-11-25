import { useState } from "react";
import { usePieces } from "../api/hooks";
import { PieceList } from "./PieceList";
import { PlayerPage } from "./PlayerPage";

export function App() {
  const pieces = usePieces();
  const [selectedId, setSelectedId] = useState<string | null>(() => location.hash.slice(1) || null);

  const select = (id: string) => {
    location.hash = id;
    setSelectedId(id);
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Tonetool</h1>
        <p className="text-sm text-zinc-400">Choir practice tracks</p>
      </header>
      {pieces.isPending && <p className="text-zinc-400">Loading pieces…</p>}
      {pieces.isError && <p className="text-red-400">Could not load pieces: {pieces.error.message}</p>}
      {pieces.data && <PieceList pieces={pieces.data} selectedId={selectedId} onSelect={select} />}
      {selectedId && <PlayerPage key={selectedId} pieceId={selectedId} />}
    </div>
  );
}
