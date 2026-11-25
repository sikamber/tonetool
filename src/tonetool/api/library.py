"""The collection of pieces the server can serve, import, edit and delete."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..importer import MUSICXML_SUFFIXES, ScoreImporter
from ..models import Piece, Section, VoiceKind
from .config import ServerConfig
from .editor import PieceEditor, PieceEdits
from .errors import ClientError, Conflict

Origin = Literal["library", "linked"]

PIECE_FILE = "piece.json"
PIECE_ID = re.compile(r"^[\w-]+$")  # \w is Unicode: æ, ø, å are fine


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
    origin: Origin = "linked"  # "library": imported in the app, owned by the library folder
    error: str | None = None  # set when the file could not be loaded


@dataclass(frozen=True)
class StoredPiece:
    """Where a piece lives. A library piece owns its folder (score + piece.json); a linked one is
    just a ``piece.json`` somewhere that the config points at."""

    id: str
    path: Path
    origin: Origin


def slug(text: str) -> str:
    """An id from free text: letters (any script) and digits kept, runs of anything else become ``-``."""
    return re.sub(r"[^\w]+", "-", unicodedata.normalize("NFC", text)).strip("-_")


class PieceLibrary:
    """Loads configured pieces from disk (re-reading a file only when it changes) and changes them.

    Pieces come from the config's ``[[pieces]]`` entries and from every ``<library>/<id>/piece.json``.
    Everything that writes holds a lock, because music21 (used by the importer) keeps global state.
    """

    def __init__(self, config: ServerConfig) -> None:
        """Remember the config; pieces are looked up on demand so new imports show up at once."""
        self._config = config
        self._cache: dict[str, tuple[float, Piece]] = {}
        self._lock = threading.RLock()

    # -- reading ------------------------------------------------------------------------------

    def get(self, piece_id: str) -> Piece:
        """The piece with this id. KeyError if unknown; OSError/ValueError if the file is bad."""
        with self._lock:
            stored = self._entry(piece_id)
            mtime = stored.path.stat().st_mtime
            cached = self._cache.get(piece_id)
            if cached is None or cached[0] != mtime:
                cached = (mtime, Piece.load(stored.path))
                self._cache[piece_id] = cached
            return cached[1]

    def summaries(self) -> list[PieceSummary]:
        """A summary per piece; a broken file yields an entry with ``error`` set."""
        with self._lock:
            return [self._summary(stored) for stored in self._stored().values()]

    # -- changing -----------------------------------------------------------------------------

    def edit(self, piece_id: str, edits: PieceEdits) -> Piece:
        """Apply ``edits`` (validated by the piece's own rules) and store the result."""
        with self._lock:
            stored = self._entry(piece_id)
            edited = PieceEditor(self.get(piece_id)).apply(edits)
            self._write(stored.path, edited)
            return edited

    def import_score(self, filename: str, data: bytes, piece_id: str | None = None) -> str:
        """Import a MusicXML score as a new library piece and return its id.

        The id is ``piece_id`` if given (it must be free), else made from the title and made unique.
        Nothing is left behind if the score cannot be read.
        """
        library = self._config.library
        if library is None:
            raise Conflict("this server has no library folder: set `library = ...` in the config")
        name = self._score_name(filename)
        if piece_id is not None and not PIECE_ID.fullmatch(piece_id):
            raise ClientError(f"invalid id {piece_id!r}: use letters, digits, '_' and '-'")
        with self._lock:
            library.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=library))
            try:
                score = staging / name
                score.write_bytes(data)
                piece = self._read_score(score)
                new_id = self._choose_id(piece_id, piece.title, name)
                piece.save(staging / PIECE_FILE)
                staging.rename(library / new_id)
                return new_id
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise

    def replace_score(self, piece_id: str, filename: str, data: bytes) -> Piece:
        """Re-import a piece from a new score, keeping its sections, title, key and voice labels/kinds.

        The new score must have the same number of bars and parts, since the sections refer to bars.
        """
        name = self._score_name(filename)
        with self._lock:
            stored = self._entry(piece_id)
            old = self.get(piece_id)
            with tempfile.TemporaryDirectory(prefix="tonetool-") as tmp:
                score = Path(tmp) / name
                score.write_bytes(data)
                new = self._read_score(score, keep_sections=old.sections)
            if len(new.measures) != len(old.measures) or len(new.tracks) != len(old.tracks):
                raise ClientError(
                    f"the new score has {len(new.measures)} bars and {len(new.tracks)} parts, but "
                    f"this piece has {len(old.measures)} and {len(old.tracks)}; import it as a new piece instead"
                )
            new.title = old.title
            new.key = old.key or new.key
            for before, after in zip(old.tracks, new.tracks):
                after.label, after.voice = before.label, before.voice
            if stored.origin == "library":
                folder = stored.path.parent
                previous = folder / Path(old.source_file).name
                if previous.name != name and previous.is_file():
                    self._trash(previous, f"{piece_id}-")
                (folder / name).write_bytes(data)
            self._write(stored.path, new)
            return new

    def delete(self, piece_id: str) -> None:
        """Move a library piece (its folder) to ``<library>/.trash``. Linked pieces cannot be deleted."""
        with self._lock:
            stored = self._entry(piece_id)
            if stored.origin != "library":
                raise Conflict(f"{piece_id!r} is linked in the config; remove it there")
            self._trash(stored.path.parent, f"{piece_id}-")
            self._cache.pop(piece_id, None)

    # -- internals ----------------------------------------------------------------------------

    def _stored(self) -> dict[str, StoredPiece]:
        """Every piece by id: library folders first, then config links (which win on a clash)."""
        found: dict[str, StoredPiece] = {}
        library = self._config.library
        if library is not None and library.is_dir():
            for folder in sorted(library.iterdir()):
                piece_id = unicodedata.normalize("NFC", folder.name)
                if folder.is_dir() and PIECE_ID.fullmatch(piece_id) and (folder / PIECE_FILE).is_file():
                    found[piece_id] = StoredPiece(piece_id, folder / PIECE_FILE, "library")
        for entry in self._config.pieces:
            found[entry.id] = StoredPiece(entry.id, entry.path, "linked")
        return found

    def _entry(self, piece_id: str) -> StoredPiece:
        """Look up a piece; KeyError listing the known ids if there is none."""
        stored = self._stored()
        try:
            return stored[piece_id]
        except KeyError:
            raise KeyError(f"no piece {piece_id!r}; have {list(stored)}") from None

    def _summary(self, stored: StoredPiece) -> PieceSummary:
        """Summarize one piece, capturing load failures instead of raising."""
        try:
            piece = self.get(stored.id)
        except (OSError, ValueError) as error:
            return PieceSummary(
                id=stored.id, title=stored.id, tracks=[], section_count=0, measure_count=0,
                origin=stored.origin, error=str(error),
            )
        return PieceSummary(
            id=stored.id,
            title=piece.title,
            tracks=[TrackSummary(id=t.id, label=t.label, voice=t.voice) for t in piece.tracks],
            section_count=len(piece.sections),
            measure_count=len(piece.measures),
            origin=stored.origin,
        )

    def _write(self, path: Path, piece: Piece) -> None:
        """Replace ``path`` atomically, keeping the previous version next to it as ``.bak``."""
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(piece.to_json(), encoding="utf-8")
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(temporary, path)
        self._cache.clear()

    def _read_score(self, path: Path, keep_sections: list[Section] | None = None) -> Piece:
        """Run the importer; anything it fails on is the caller's bad file, so report it as such."""
        try:
            return ScoreImporter(path).run(keep_sections=keep_sections)
        except Exception as error:  # music21, lxml and zipfile raise many kinds on bad input
            detail = str(error) if isinstance(error, ValueError) else f"{type(error).__name__}: {error}"
            raise ClientError(f"could not read the score: {detail}") from error

    @staticmethod
    def _score_name(filename: str) -> str:
        """A safe file name for an uploaded score: no folders, Unicode letters kept, MusicXML suffix."""
        name = unicodedata.normalize("NFC", Path(filename.replace("\\", "/")).name).strip()
        name = re.sub(r"[^\w .,()+&-]", "_", name)
        if Path(name).suffix.lower() not in MUSICXML_SUFFIXES:
            raise ClientError(f"expected a MusicXML file ({', '.join(MUSICXML_SUFFIXES)}), got {name!r}")
        return name

    def _choose_id(self, wanted: str | None, title: str, filename: str) -> str:
        """``wanted`` if free; otherwise an id made from the title (or file name) with a number if taken."""
        taken = set(self._stored())
        if wanted is not None:
            if wanted in taken:
                raise ClientError(f"a piece with id {wanted!r} already exists")
            return wanted
        base = slug(title) or slug(Path(filename).stem) or "piece"
        candidate, number = base, 1
        while candidate in taken:
            number += 1
            candidate = f"{base}-{number}"
        return candidate

    def _trash(self, path: Path, prefix: str) -> None:
        """Move a file or folder of the library into its ``.trash`` folder."""
        library = self._config.library
        assert library is not None
        trash = library / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = trash / (f"{prefix}{stamp}-{path.name}" if path.is_file() else f"{prefix}{stamp}")
        shutil.move(str(path), target)
