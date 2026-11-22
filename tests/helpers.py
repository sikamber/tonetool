"""Small helpers for reading a Piece in tests."""

from tonetool.models import Note, Piece


def flat_notes(piece: Piece, track_id: str) -> list[tuple[int, Note]]:
    """One voice's notes as (measure index, Note), in score order."""
    return [
        (index, note)
        for index, voice in enumerate(piece.voice_measures(track_id))
        for note in voice.notes
    ]
