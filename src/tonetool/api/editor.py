"""Editing a stored piece: the layer a person may change, applied under the piece's own validation."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints, ValidationError

from ..models import Key, Piece, Provenance, Section, VoiceKind
from .errors import ClientError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TrackEdit(BaseModel):
    """The editable part of a track: how it is called and what kind of voice it is."""

    id: str
    label: Text
    voice: VoiceKind


class PieceEdits(BaseModel):
    """Everything about a piece that can be changed in the app. Notes, lyrics and tempo cannot:
    they come from the MusicXML score."""

    title: Text
    # Required but nullable: ``null`` clears the key, and leaving the field out is an error, so a
    # client that does not know about keys cannot remove one by accident.
    key: Key | None
    tracks: list[TrackEdit]
    sections: list[Section]


class PieceEditor:
    """Applies ``PieceEdits`` to a piece, giving a new, fully validated piece."""

    def __init__(self, piece: Piece) -> None:
        """Remember the piece being edited (it is not modified)."""
        self.piece = piece

    def apply(self, edits: PieceEdits) -> Piece:
        """The piece with ``edits`` applied; ``ClientError`` if the result is not a valid piece.

        A section that is new or differs from the stored one with the same id becomes
        ``Provenance.USER``; unchanged sections keep their provenance.
        """
        known = [t.id for t in self.piece.tracks]
        given = [t.id for t in edits.tracks]
        if sorted(known) != sorted(given):
            raise ClientError(f"the edit must list exactly the piece's tracks {known}, got {given}")

        data = self.piece.model_dump(mode="json")
        data["title"] = edits.title
        data["key"] = edits.key.model_dump(mode="json") if edits.key else None
        by_id = {t.id: t for t in edits.tracks}
        for track in data["tracks"]:
            track["label"] = by_id[track["id"]].label
            track["voice"] = by_id[track["id"]].voice.value
        data["sections"] = [self._section(s).model_dump(mode="json") for s in edits.sections]
        try:
            return Piece.model_validate(data)
        except ValidationError as error:
            messages = [e["msg"].removeprefix("Value error, ") for e in error.errors()]
            raise ClientError("; ".join(messages)) from error

    def _section(self, section: Section) -> Section:
        """``section`` with its provenance decided: kept if it equals the stored one, else a person's."""
        stored = {s.id: s for s in self.piece.sections}.get(section.id)
        same = stored is not None and stored.model_dump(exclude={"source"}) == section.model_dump(
            exclude={"source"}
        )
        source = stored.source if same and stored is not None else Provenance.USER
        return section.model_copy(update={"source": source})
