import { useState } from "react";
import { ApiError } from "../api/client";
import { useDeletePiece, usePiece, useReplaceScore } from "../api/hooks";
import type { Piece, PieceSummary } from "../api/types";
import { usePlayer } from "../audio/hooks";
import { keyLabel } from "../music/key";
import { PieceDraft } from "../music/pieceDraft";
import { EditPanel } from "./EditPanel";
import { ExportPanel } from "./ExportPanel";
import { buttonClass, FilePicker } from "./FilePicker";
import { LyricsPane } from "./LyricsPane";
import { PianoRoll } from "./PianoRoll";
import { SectionStrip } from "./SectionStrip";
import { TransportBar } from "./TransportBar";
import { VoiceMixer } from "./VoiceMixer";

interface Props {
  summary: PieceSummary;
  /** Called after the piece was deleted. */
  onDeleted: () => void;
}

export function PlayerPage({ summary, onDeleted }: Props) {
  const piece = usePiece(summary.id);
  if (piece.isPending) return <p className="text-zinc-400">Loading…</p>;
  if (piece.isError) return <p className="text-red-400">Could not load piece: {piece.error.message}</p>;
  return <PieceView piece={piece.data} summary={summary} onDeleted={onDeleted} />;
}

function PieceView({ piece, summary, onDeleted }: Props & { piece: Piece }) {
  const [draft, setDraft] = useState(() => PieceDraft.from(piece));
  const [editing, setEditing] = useState(false);
  // When the stored piece changes (saved, or its score replaced) the draft starts again from it.
  if (draft.saved !== piece) setDraft(PieceDraft.from(piece));

  const player = usePlayer(draft.piece);
  if (!player) return null;
  const shown = draft.piece;

  return (
    <main className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">
          {shown.title}
          {shown.key && <span className="ml-3 text-sm font-normal text-zinc-400">{keyLabel(shown.key)}</span>}
        </h2>
        <PieceToolbar
          summary={summary}
          editing={editing}
          dirty={draft.dirty}
          onToggleEdit={() => setEditing((on) => !on)}
          onDeleted={onDeleted}
        />
      </div>
      <TransportBar player={player} />
      <SectionStrip piece={shown} player={player} />
      <LyricsPane piece={shown} player={player} />
      <PianoRoll piece={shown} player={player} />
      <VoiceMixer piece={shown} player={player} />
      <ExportPanel piece={shown} player={player} />
      {editing && <EditPanel pieceId={summary.id} draft={draft} onChange={setDraft} />}
      {shown.warnings && shown.warnings.length > 0 && (
        <ul className="text-xs text-amber-300/80">
          {shown.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
    </main>
  );
}

function PieceToolbar({
  summary,
  editing,
  dirty,
  onToggleEdit,
  onDeleted,
}: {
  summary: PieceSummary;
  editing: boolean;
  dirty: boolean;
  onToggleEdit: () => void;
  onDeleted: () => void;
}) {
  const replace = useReplaceScore(summary.id);
  const remove = useDeletePiece(summary.id);
  const messages = [replace.error, remove.error].flatMap((e) => (e instanceof ApiError ? e.messages : e ? [e.message] : []));

  const confirmReplace = (file: File) => {
    const warning = dirty ? "You have unsaved changes; they will be lost. " : "";
    if (confirm(`${warning}Replace this piece's score with ${file.name}? Sections, title and voice labels are kept.`)) {
      replace.mutate(file);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" aria-pressed={editing} className={buttonClass} onClick={onToggleEdit}>
        {editing ? "Close editor" : "Edit"}
      </button>
      <FilePicker className={buttonClass} disabled={replace.isPending} onFile={confirmReplace}>
        {replace.isPending ? "Reading score…" : "Replace score…"}
      </FilePicker>
      {summary.origin === "library" && (
        <button
          type="button"
          disabled={remove.isPending}
          className={`${buttonClass} hover:border-red-400 hover:text-red-300`}
          onClick={() => {
            if (confirm(`Delete "${summary.title}"? It is moved to the library's .trash folder.`)) {
              remove.mutate(undefined, { onSuccess: onDeleted });
            }
          }}
        >
          Delete
        </button>
      )}
      {messages.length > 0 && (
        <ul role="alert" className="basis-full space-y-1 text-sm text-red-400">
          {messages.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
