"""Suggesting the tonal key of a score."""

from __future__ import annotations

import music21 as m21

from .models import Key, Mode


class KeySuggester:
    """Suggests a ``Key`` from a score's first key signature.

    A signature with an explicit mode (``<mode>`` in MusicXML) is taken as written. A signature
    alone says only how many sharps or flats there are, which fits a major key and its relative
    minor; of the two, the one whose tonic is the lowest note of the final measure wins (tonal
    music tends to end on the tonic in the bass), and major is the default. No key signature, no
    suggestion. It is only a suggestion: a person can change the key.
    """

    def __init__(self, score: m21.stream.Score) -> None:
        """Remember the score to look at."""
        self.score = score

    def suggest(self) -> Key | None:
        """The suggested key, or None if the score has no key signature."""
        signature = self._first_signature()
        if signature is None:
            return None
        if isinstance(signature, m21.key.Key) and signature.mode in ("major", "minor"):
            return self._convert(signature)
        major = signature.asKey("major")
        minor = signature.asKey("minor")
        bass = self._final_bass_pitch_class()
        if bass is not None and bass != major.tonic.pitchClass and bass == minor.tonic.pitchClass:
            return self._convert(minor)
        return self._convert(major)

    def _first_signature(self) -> m21.key.KeySignature | None:
        """The first key signature of the first part."""
        for signature in self.score.parts[0].recurse().getElementsByClass(m21.key.KeySignature):
            return signature
        return None

    def _final_bass_pitch_class(self) -> int | None:
        """Pitch class of the lowest note sounding in the last measure of any part."""
        pitches: list[int] = []
        for part in self.score.parts:
            measures = list(part.getElementsByClass(m21.stream.Measure))
            if measures:
                pitches += [p.midi for element in measures[-1].recurse().notes for p in element.pitches]
        return min(pitches) % 12 if pitches else None

    @staticmethod
    def _convert(key: m21.key.Key) -> Key | None:
        """Our ``Key`` (music21 writes flats as ``-``); None for tonics we cannot spell, e.g. ``F##``."""
        tonic = key.tonic.name.replace("-", "b")
        try:
            return Key(tonic=tonic, mode=Mode(key.mode))
        except ValueError:
            return None
