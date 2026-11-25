"""Which lyric line each section sings.

A score's lyric lines (MusicXML ``number="1"``, ``"2"``, ...) are not the verses of the performance:
the usual convention is that a repeat sings the next line, but a score can also hold two different
verses on one line in different bars (verse 1 in bars 1-12 and verse 3 in bars 13-24 on line 1,
with verse 2 on line 2 over bars 1-12). So the mapping is stored per section
(``Section.lyric_number``), and this class only suggests it.
"""

from __future__ import annotations

from collections import Counter

from .models import Piece, Provenance


class LyricVerses:
    """Suggests ``Section.lyric_number`` for a piece by counting how often its bars were sung.

    Going through the sections in performance order, a section whose bars have already been sung
    ``n`` times sings lyric line ``n + 1``. If the score has no such line there, it sings the highest
    line it does have below that (a verse that is repeated unchanged), or none if there is no text.
    """

    def __init__(self, piece: Piece) -> None:
        """Remember the piece and index which lyric lines each measure carries."""
        self.piece = piece
        self.lines_by_measure: list[set[int]] = [
            {
                int(lyric.number)
                for voice in measure.voices.values()
                for note in voice.notes
                for lyric in note.lyrics
                if lyric.number.isdigit()
            }
            for measure in piece.measures
        ]

    def suggest(self) -> dict[str, str | None]:
        """Section id -> suggested lyric line (as ``Lyric.number``), or None, for every section."""
        sung: Counter[int] = Counter()
        suggestion: dict[str, str | None] = {}
        for section in self.piece.sections:
            measures = section.measure_sequence()
            wanted = max((sung[m] for m in measures), default=0) + 1
            available = {line for m in measures for line in self.lines_by_measure[m]}
            usable = [line for line in available if line <= wanted]
            suggestion[section.id] = str(max(usable)) if usable else None
            sung.update(set(measures))
        return suggestion

    def assign(self) -> None:
        """Apply the suggestions to the sections that a person has not edited."""
        suggestion = self.suggest()
        for section in self.piece.sections:
            if section.source == Provenance.AUTO:
                section.lyric_number = suggestion[section.id]
