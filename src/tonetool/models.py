"""Domain model for a piece.

``Piece`` is the serialized form (``piece.json``). The MusicXML file is the immutable source
for notes; everything about *how the piece is performed* (sections, playback order) lives here
and is the final authority. The importer only produces initial suggestions
(``Provenance.AUTO``); a user edit flips them to ``Provenance.USER``.

Measures are always referenced by 0-based document-order index, never by printed number.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 1


class Provenance(StrEnum):
    AUTO = "auto"  # suggested by the importer, unreviewed
    USER = "user"  # confirmed or edited by a person


class Note(BaseModel):
    """One sounding pitch inside a measure."""

    pitch: int  # MIDI note number
    offset: float  # quarter notes from the start of the measure it sits in
    duration: float  # quarter notes, as notated: a tied note is not merged with its neighbours
    tied: bool = False  # continues a note held from before; has no attack of its own


class VoiceMeasure(BaseModel):
    """What one voice sings in one measure (no notes if it rests).

    Deliberately thin: it gives per-voice, per-measure data (lyrics, say) a natural home later.
    """

    notes: list[Note] = Field(default_factory=list)  # in time order; chords are simultaneous notes


class Measure(BaseModel):
    """One notated measure (position in the score, not in the performance)."""

    index: int
    number: str  # printed number; may be "0" (pickup), "12a", or repeat across endings
    start: float  # notated offset from the start of the piece, in quarter notes
    length: float  # actual length in quarter notes (pickups are shorter)
    bpm: float  # quarter-note BPM in effect at the start of the measure
    beats_per_bar: int = 4
    beat_unit: int = 4  # denominator of the time signature
    # what each voice sings in this measure: exactly one entry per track, keyed by Track.id
    # (empty when that voice rests)
    voices: dict[str, VoiceMeasure] = Field(default_factory=dict)

    @property
    def beat_length(self) -> float:
        """Length of one metronome beat in quarter notes (compound meters beat in dotted units)."""
        if (
            self.beat_unit == 8
            and self.beats_per_bar % 3 == 0
            and self.beats_per_bar > 3
        ):
            return 1.5
        return 4 / self.beat_unit

    @property
    def end(self) -> float:
        """Notated end offset from the start of the piece, in quarter notes."""
        return self.start + self.length


class VoiceKind(StrEnum):
    SOPRANO = "S"
    ALTO = "A"
    TENOR = "T"
    BASS = "B"
    OTHER = "other"

    @classmethod
    def guess(cls, label: str) -> VoiceKind:
        """Guess the voice type from a part name like 'Soprano 1' or 'T'; OTHER if unknown."""
        text = label.lower()
        for kind, pattern in (
            (cls.SOPRANO, r"sopran|^s\b|^s\d|descant"),
            (cls.ALTO, r"alto|^a\b|^a\d|contralto"),
            (cls.TENOR, r"tenor|^t\b|^t\d"),
            (cls.BASS, r"bass|baritone|^b\b|^b\d"),
        ):
            if re.search(pattern, text):
                return kind
        return cls.OTHER


class Track(BaseModel):
    """One independently mixable line: a single voice.

    Choral scores often put two voices on one staff (e.g. S/A), so the unit that a singer wants
    to mute or solo is a voice, not a staff. A track holds no notes itself: they live in the
    measures (``Measure.voices``, keyed by ``Track.id``); see ``Piece.voice_measures``.
    """

    id: str  # "T0", "T1", ... in score order
    label: str
    voice: VoiceKind = VoiceKind.OTHER


class Section(BaseModel):
    """A named, inclusive range of notated measures. Used for navigation and looping."""

    id: str
    name: str
    start: int
    end: int
    source: Provenance = Provenance.AUTO

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        """Reject sections whose start is after their end."""
        if self.start > self.end:
            raise ValueError(
                f"section {self.id!r}: start {self.start} > end {self.end}"
            )
        return self

    def measures(self) -> range:
        """Measure indices covered by the section, inclusive."""
        return range(self.start, self.end + 1)

    def __len__(self) -> int:
        """Number of measures in the section."""
        return self.end - self.start + 1


class PlaybackSegment(BaseModel):
    """A contiguous run of notated measures, played in order. Inclusive on both ends."""

    start: int
    end: int

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        """Reject segments whose start is after their end."""
        if self.start > self.end:
            raise ValueError(f"segment start {self.start} > end {self.end}")
        return self

    def measures(self) -> range:
        """Measure indices covered by the segment, inclusive."""
        return range(self.start, self.end + 1)


class PlaybackOrder(BaseModel):
    """The performed order of measures, as a flat list of ranges.

    Flat ranges are deliberately dumb: they can express any form (voltas, D.S. al Coda, skipped
    endings) and are trivial to validate. Editing helpers rewrite the list rather than storing a
    repeat DSL.
    """

    segments: list[PlaybackSegment]
    source: Provenance = Provenance.AUTO

    @classmethod
    def from_measure_sequence(
        cls, sequence: list[int], source: Provenance = Provenance.AUTO
    ) -> Self:
        """Compress e.g. [0,1,2,3,1,2,4] into segments [0-3], [1-2], [4-4]."""
        segments: list[PlaybackSegment] = []
        for index in sequence:
            if segments and segments[-1].end + 1 == index:
                segments[-1].end = index
            else:
                segments.append(PlaybackSegment(start=index, end=index))
        return cls(segments=segments, source=source)

    @classmethod
    def straight_through(cls, measure_count: int) -> Self:
        """Order that plays every measure once, front to back."""
        return cls.from_measure_sequence(list(range(measure_count)))

    def measure_sequence(self) -> list[int]:
        """Flatten the segments into the performed list of measure indices."""
        return [m for segment in self.segments for m in segment.measures()]

    def validate_against(self, measure_count: int) -> None:
        """Raise ValueError if the order is empty or points outside ``measure_count`` measures."""
        if not self.segments:
            raise ValueError("playback order is empty")
        for segment in self.segments:
            if segment.start < 0 or segment.end >= measure_count:
                raise ValueError(
                    f"segment {segment.start}-{segment.end} outside 0-{measure_count - 1}"
                )

    def describe(self, measures: list[Measure]) -> str:
        """Human-readable form using printed measure numbers, e.g. '1-4 | 2-3 | 5-6'."""
        return " | ".join(
            f"{measures[s.start].number}-{measures[s.end].number}"
            if s.start != s.end
            else measures[s.start].number
            for s in self.segments
        )


class Piece(BaseModel):
    schema_version: int = SCHEMA_VERSION
    title: str
    source_file: str
    xml_sha256: (
        str  # detects drift if the MusicXML is replaced after structure was confirmed
    )
    measures: list[Measure]
    tracks: list[Track]
    sections: list[Section]
    playback_order: PlaybackOrder
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        """Check that the playback order, sections, and track ids agree with the measures."""
        count = len(self.measures)
        self.playback_order.validate_against(count)
        for section in self.sections:
            if section.end >= count:
                raise ValueError(f"section {section.id!r} outside measure range")
        ids = [t.id for t in self.tracks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate track ids")
        for measure in self.measures:
            if set(measure.voices) != set(ids):
                raise ValueError(
                    f"measure {measure.index} must have exactly one VoiceMeasure per track "
                    f"{sorted(ids)}, has {sorted(measure.voices)}"
                )
        return self

    def track(self, track_id: str) -> Track:
        """Look up a track by id; KeyError listing the known ids if there is none."""
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(f"no track {track_id!r}; have {[t.id for t in self.tracks]}")

    def voice_measures(self, track_id: str) -> list[VoiceMeasure]:
        """One voice across every measure, in notated order (the "horizontal" view).

        Always ``len(self.measures)`` entries; a measure where the voice rests has an empty
        ``VoiceMeasure``. KeyError if there is no such track.
        """
        self.track(track_id)  # for the error message listing the known ids
        return [m.voices[track_id] for m in self.measures]

    def section(self, section_id: str) -> Section:
        """Look up a section by id; KeyError listing the known ids if there is none."""
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(
            f"no section {section_id!r}; have {[s.id for s in self.sections]}"
        )

    def save(self, path: Path) -> None:
        """Write the piece to ``path`` as indented JSON."""
        path.write_text(self.model_dump_json(indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a piece from a JSON file written by ``save``."""
        return cls.model_validate_json(path.read_text())
