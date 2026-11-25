/** The piece id stored in a URL hash ("#Juletræet", which browsers hold percent-encoded), or null. */
export function pieceIdFromHash(hash: string): string | null {
  const raw = hash.replace(/^#/, "");
  if (!raw) return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return null; // malformed escape sequence
  }
}

/** The hash that selects `pieceId`. */
export function hashForPieceId(pieceId: string): string {
  return `#${encodeURIComponent(pieceId)}`;
}
