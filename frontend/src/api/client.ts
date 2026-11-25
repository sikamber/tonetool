import type { Piece, PieceEdits, PieceSummary } from "./types";

/** An error response from the server, with its message(s) flattened to readable strings. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly messages: string[],
  ) {
    super(messages.join("; "));
    this.name = "ApiError";
  }
}

/**
 * Readable messages from a FastAPI error body's `detail`: a string, or a list of `{loc, msg}` for
 * request-validation errors ("title: String should have at least 1 character").
 */
export function errorMessages(detail: unknown, fallback: string): string[] {
  if (typeof detail === "string" && detail) return [detail];
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item: unknown) => {
      if (typeof item === "string") return [item];
      if (item && typeof item === "object" && "msg" in item) {
        const { msg, loc } = item as { msg: unknown; loc?: unknown };
        const where = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
        const text = String(msg).replace(/^Value error, /, "");
        return [where ? `${where}: ${text}` : text];
      }
      return [];
    });
    if (messages.length > 0) return messages;
  }
  return [fallback];
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body: { detail?: unknown } | null = await response.json().catch(() => null);
    throw new ApiError(response.status, errorMessages(body?.detail, `${response.status} ${response.statusText}`));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const piecePath = (id: string) => `/api/pieces/${encodeURIComponent(id)}`;

const withFile = (file: File): RequestInit => {
  const form = new FormData();
  form.append("file", file);
  return { method: "POST", body: form };
};

export const api = {
  listPieces: () => request<PieceSummary[]>("/api/pieces"),
  getPiece: (id: string) => request<Piece>(piecePath(id)),
  importPiece: (file: File) => request<PieceSummary>("/api/pieces", withFile(file)),
  savePiece: (id: string, edits: PieceEdits) =>
    request<Piece>(piecePath(id), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edits),
    }),
  replaceScore: (id: string, file: File) => request<Piece>(`${piecePath(id)}/score`, withFile(file)),
  deletePiece: (id: string) => request<void>(piecePath(id), { method: "DELETE" }),
};
