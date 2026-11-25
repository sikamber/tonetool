import { usePiece } from "../api/hooks";
import type { Piece } from "../api/types";
import { usePlayer } from "../audio/hooks";
import { ExportPanel } from "./ExportPanel";
import { LyricsPane } from "./LyricsPane";
import { SectionStrip } from "./SectionStrip";
import { TransportBar } from "./TransportBar";
import { VoiceMixer } from "./VoiceMixer";

export function PlayerPage({ pieceId }: { pieceId: string }) {
  const piece = usePiece(pieceId);
  if (piece.isPending) return <p className="text-zinc-400">Loading…</p>;
  if (piece.isError) return <p className="text-red-400">Could not load piece: {piece.error.message}</p>;
  return <PieceView piece={piece.data} />;
}

function PieceView({ piece }: { piece: Piece }) {
  const player = usePlayer(piece);
  if (!player) return null;
  return (
    <main className="space-y-6">
      <h2 className="text-xl font-medium">{piece.title}</h2>
      <TransportBar player={player} />
      <SectionStrip piece={piece} player={player} />
      <LyricsPane piece={piece} player={player} />
      <VoiceMixer piece={piece} player={player} />
      <ExportPanel piece={piece} player={player} />
      {piece.warnings && piece.warnings.length > 0 && (
        <ul className="text-xs text-amber-300/80">
          {piece.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
    </main>
  );
}
