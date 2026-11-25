import type { Piece, PieceSummary } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const detail = await response.json().then((b: { detail?: string }) => b.detail, () => undefined);
    throw new Error(detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listPieces: () => getJson<PieceSummary[]>("/api/pieces"),
  getPiece: (id: string) => getJson<Piece>(`/api/pieces/${encodeURIComponent(id)}`),
};
