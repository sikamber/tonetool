"""MusicXML -> Piece.

Notes and tempo come from music21 (chords expanded, ties flagged, voices separated). Structure
suggestions come from lxml (see structure.py). Measures are matched between the two by
document-order index; the importer refuses to continue if the counts disagree.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import music21 as m21

from .models import Measure, Note, Piece, Track, VoiceKind, VoiceMeasure
from .structure import SuggestedStructure, read_musicxml_root

DEFAULT_BPM = 100.0


class ScoreImporter:
    """Turns one MusicXML file into a ``Piece`` with *suggested* (``auto``) structure."""

    def __init__(self, path: Path) -> None:
        """Remember the score path; call ``run`` to do the import."""
        self.path = path
        self.warnings: list[str] = []

    def run(self) -> Piece:
        """Parse the score and return a ``Piece`` with suggested sections and playback order."""
        score = m21.converter.parse(str(self.path))
        if not isinstance(score, m21.stream.Score):
            raise TypeError(
                f"{self.path}: expected a single score, got {type(score).__name__}"
            )
        if not score.parts:
            raise ValueError(f"{self.path}: no parts found")
        measures = self._read_measures(score)
        tracks = self._read_tracks(score, measures)

        structure = SuggestedStructure(read_musicxml_root(self.path))
        if len(structure.measure_mark_collections) != len(measures):
            raise ValueError(
                f"measure count mismatch: music21 saw {len(measures)}, "
                f"XML has {len(structure.measure_mark_collections)}; structure cannot be aligned"
            )
        # printed numbers come from the XML (music21 renumbers some cases)
        for measure, collection in zip(measures, structure.measure_mark_collections):
            measure.number = collection.number
        sections = structure.suggest_sections()
        order = structure.suggest_order()

        title = (
            score.metadata.title
            if score.metadata and score.metadata.title
            else self.path.stem
        )
        return Piece(
            title=title,
            source_file=self.path.name,
            xml_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            measures=measures,
            tracks=tracks,
            sections=sections,
            playback_order=order,
            warnings=[*self.warnings, *structure.warnings],
        )

    # -- measures and tempo -------------------------------------------------------------------

    def _read_measures(self, score: m21.stream.Score) -> list[Measure]:
        """Build ``Measure`` objects as notated in the source (without repeats or jumps), based on the first part."""
        part = score.parts[0]
        raw = list(part.getElementsByClass(m21.stream.Measure))
        if not raw:
            raise ValueError(f"{self.path}: first part has no measures")

        tempo_marks = sorted(
            (
                float(m.getOffsetInHierarchy(part)),
                float(m.getQuarterBPM() or DEFAULT_BPM),
            )
            for m in part.recurse().getElementsByClass(m21.tempo.MetronomeMark)
            if m.getQuarterBPM()
        )
        if not tempo_marks:
            self.warnings.append(
                f"no tempo marking found; assuming {DEFAULT_BPM:g} BPM"
            )

        beats, unit = 4, 4
        measures: list[Measure] = []
        for index, m in enumerate(raw):
            start = float(m.offset)
            end = (
                float(raw[index + 1].offset)
                if index + 1 < len(raw)
                else start + float(m.highestTime)
            )
            signature = m.timeSignature or m.getContextByClass(m21.meter.TimeSignature)
            if signature is not None:
                beats, unit = signature.numerator, signature.denominator
            bpm = DEFAULT_BPM
            for offset, value in tempo_marks:
                if offset <= start + 1e-9:
                    bpm = value
            measures.append(
                Measure(
                    index=index,
                    number=str(m.number),
                    start=start,
                    length=end - start,
                    bpm=bpm,
                    beats_per_bar=beats,
                    beat_unit=unit,
                )
            )
        return measures

    # -- notes --------------------------------------------------------------------------------

    def _read_tracks(
        self, score: m21.stream.Score, measures: list[Measure]
    ) -> list[Track]:
        """Create one ``Track`` per voice and give every measure a ``VoiceMeasure`` for it.

        A voice that rests in a measure gets an empty ``VoiceMeasure``, so each measure ends up
        with one entry per track in ``measures[i].voices``.

        MusicXML "parts" only exist here, as the input vocabulary: a part is one notated line and
        can carry several voices (e.g. S/A on one staff), and each voice becomes a track. A part's
        voices are found by pre-scanning all of its measures. A measure that writes only one voice
        in a multi-voice part is a unison passage, so every voice of the part gets those notes.

        Raises if the parts do not all have the same number of measures: notes are addressed by
        measure index, so a bar missing in the middle of one part would silently shift everything
        after it. Parts with no notes contribute no tracks (and add a warning).
        """
        tracks: list[Track] = []
        measure_counts: list[tuple[str, int]] = []  # (part name, measures), checked after the loop
        for part_index, part in enumerate(score.parts):
            name = part.partName or f"part {part_index}"
            part_measures = list(part.getElementsByClass(m21.stream.Measure))
            measure_counts.append((name, len(part_measures)))
            voices_by_measure = [self._notes_by_voice(m) for m in part_measures]

            voice_ids = sorted(
                {
                    voice_id
                    for voices in voices_by_measure
                    for voice_id, notes in voices.items()
                    if notes
                }
            )
            if not voice_ids:
                self.warnings.append(f"{name}: no notes found")
                continue
            multi = len(voice_ids) > 1
            part_tracks: dict[str, Track] = {}
            for voice_id in voice_ids:
                track = Track(
                    id=f"T{len(tracks)}",
                    label=f"{name} (voice {voice_id})" if multi else name,
                    voice=VoiceKind.guess(name),
                )
                tracks.append(track)
                part_tracks[voice_id] = track

            for voices, measure in zip(voices_by_measure, measures):
                if multi and len(voices) == 1:
                    (notes,) = voices.values()
                    voices = {
                        voice_id: [n.model_copy() for n in notes] for voice_id in voice_ids
                    }
                for voice_id, track in part_tracks.items():
                    measure.voices[track.id] = VoiceMeasure(notes=voices.get(voice_id, []))

        if len({count for _, count in measure_counts}) > 1:
            detail = ", ".join(f"{name}={count}" for name, count in measure_counts)
            raise ValueError(
                f"{self.path}: parts have different numbers of measures ({detail}); "
                "cannot line them up"
            )
        return tracks

    def _notes_by_voice(self, measure: m21.stream.Measure) -> dict[str, list[Note]]:
        """The notes of one measure keyed by MusicXML voice id: chords expanded, in time order.

        A voice that only rests maps to ``[]``, so ``len`` of the result is the number of voices
        written in the measure, which is how a single-voiced measure is recognised.
        """
        by_voice: dict[str, list[Note]] = {}
        for voice_id, container in self._voices_of(measure):
            notes = by_voice.setdefault(voice_id, [])
            for element in container.notes:
                offset = float(element.getOffsetInHierarchy(measure))
                duration = float(element.duration.quarterLength)
                for pitch, tied in self._pitches_of(element):
                    notes.append(
                        Note(pitch=pitch, tied=tied, offset=offset, duration=duration)
                    )
            notes.sort(key=lambda n: (n.offset, n.pitch))
        return by_voice

    @staticmethod
    def _voices_of(measure: m21.stream.Measure) -> list[tuple[str, m21.stream.Stream]]:
        """(voice id, container) pairs; notes sitting directly in the measure count as voice '1'."""
        voices: list[tuple[str, m21.stream.Stream]] = [
            (str(v.id), v) for v in measure.getElementsByClass(m21.stream.Voice)
        ]
        if any(isinstance(el, (m21.note.Note, m21.chord.Chord)) for el in measure):
            voices.insert(0, ("1", measure))
        return voices

    @staticmethod
    def _pitches_of(element: m21.note.GeneralNote) -> list[tuple[int, bool]]:
        """(MIDI number, continues-a-tie) per sounding pitch; empty for rests and other elements.

        A pitch continues a tie if it is the middle or end of one; ties are per pitch in a chord.
        """
        if isinstance(element, m21.chord.Chord):
            singles = list(element.notes)
        elif isinstance(element, m21.note.Note):
            singles = [element]
        else:
            return []
        return [
            (n.pitch.midi, n.tie is not None and n.tie.type in ("stop", "continue"))
            for n in singles
        ]
