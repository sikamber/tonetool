import { ApiError } from "../api/client";
import { useImportPiece } from "../api/hooks";
import { buttonClass, FilePicker } from "./FilePicker";

/** Upload a MusicXML score as a new piece. */
export function ImportButton({ onImported }: { onImported: (pieceId: string) => void }) {
  const importPiece = useImportPiece();
  const error = importPiece.error instanceof ApiError ? importPiece.error.messages : null;

  return (
    <div className="mb-8 flex flex-wrap items-center gap-3">
      <FilePicker
        className={buttonClass}
        disabled={importPiece.isPending}
        onFile={(file) => importPiece.mutate(file, { onSuccess: (summary) => onImported(summary.id) })}
      >
        Import score…
      </FilePicker>
      {importPiece.isPending && <span className="text-sm text-zinc-400">Reading score, this can take a few seconds…</span>}
      {error?.map((message) => (
        <span key={message} className="text-sm text-red-400">
          {message}
        </span>
      ))}
      {importPiece.isError && !error && <span className="text-sm text-red-400">Import failed: {importPiece.error.message}</span>}
    </div>
  );
}
