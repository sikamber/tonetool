"""The collection of pieces the server can serve."""

from __future__ import annotations

from pydantic import BaseModel

from ..models import Piece, VoiceKind
from .config import PieceEntry, ServerConfig


class TrackSummary(BaseModel):
    id: str
    label: str
    voice: VoiceKind


class PieceSummary(BaseModel):
    """What the piece picker needs, without the notes."""

    id: str
    title: str
    tracks: list[TrackSummary]
    section_count: int
    measure_count: int
    error: str | None = None  # set when the file could not be loaded


class PieceLibrary:
    """Loads configured pieces from disk, re-reading a file only when it changes."""

    def __init__(self, config: ServerConfig) -> None:
        """Index the configured entries by id."""
        self._entries = {entry.id: entry for entry in config.pieces}
        self._cache: dict[str, tuple[float, Piece]] = {}

    def get(self, piece_id: str) -> Piece:
        """The piece with this id. KeyError if unconfigured; OSError/ValueError if the file is bad."""
        entry = self._entry(piece_id)
        mtime = entry.path.stat().st_mtime
        cached = self._cache.get(piece_id)
        if cached is None or cached[0] != mtime:
            cached = (mtime, Piece.load(entry.path))
            self._cache[piece_id] = cached
        return cached[1]

    def summaries(self) -> list[PieceSummary]:
        """A summary per configured piece; a broken file yields an entry with ``error`` set."""
        return [self._summary(entry) for entry in self._entries.values()]

    def _entry(self, piece_id: str) -> PieceEntry:
        """Look up a configured entry; KeyError listing the known ids if there is none."""
        try:
            return self._entries[piece_id]
        except KeyError:
            raise KeyError(f"no piece {piece_id!r}; have {list(self._entries)}") from None

    def _summary(self, entry: PieceEntry) -> PieceSummary:
        """Summarize one entry, capturing load failures instead of raising."""
        try:
            piece = self.get(entry.id)
        except (OSError, ValueError) as error:
            return PieceSummary(
                id=entry.id, title=entry.id, tracks=[], section_count=0, measure_count=0,
                error=str(error),
            )
        return PieceSummary(
            id=entry.id,
            title=piece.title,
            tracks=[TrackSummary(id=t.id, label=t.label, voice=t.voice) for t in piece.tracks],
            section_count=len(piece.sections),
            measure_count=len(piece.measures),
        )
