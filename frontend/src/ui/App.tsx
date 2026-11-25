import { useState, type ReactNode } from "react";
import { useLogout, usePieces, useSession } from "../api/hooks";
import type { SessionStatus } from "../api/types";
import { ImportButton } from "./ImportButton";
import { LoginPage } from "./LoginPage";
import { PieceList } from "./PieceList";
import { hashForPieceId, pieceIdFromHash } from "./pieceHash";
import { PlayerPage } from "./PlayerPage";

function Shell({ children, session }: { children: ReactNode; session?: SessionStatus }) {
  const logout = useLogout();
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tonetool</h1>
          <p className="text-sm text-zinc-400">Choir practice tracks</p>
        </div>
        {session?.auth_required && session.authenticated && (
          <div className="flex items-center gap-3 text-sm text-zinc-400">
            <span>{session.username}</span>
            <button
              type="button"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
              className="rounded-md border border-zinc-700 px-3 py-1.5 hover:bg-zinc-800 disabled:opacity-50"
            >
              Log out
            </button>
          </div>
        )}
      </header>
      {children}
    </div>
  );
}

/** Asks who the user is first, and shows the login page instead of the library if need be. */
export function App() {
  const session = useSession();
  if (session.isPending) return <Shell><p className="text-zinc-400">Loading…</p></Shell>;
  if (session.isError) return <Shell><p className="text-red-400">Could not reach the server: {session.error.message}</p></Shell>;
  if (session.data.auth_required && !session.data.authenticated) return <Shell><LoginPage /></Shell>;
  return (
    <Shell session={session.data}>
      <Library />
    </Shell>
  );
}

function Library() {
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
    <>
      {pieces.isPending && <p className="text-zinc-400">Loading pieces…</p>}
      {pieces.isError && <p className="text-red-400">Could not load pieces: {pieces.error.message}</p>}
      {pieces.data && <PieceList pieces={pieces.data} selectedId={current?.id ?? null} onSelect={select} />}
      {pieces.data && <ImportButton onImported={select} />}
      {current && <PlayerPage key={current.id} summary={current} onDeleted={deselect} />}
    </>
  );
}
