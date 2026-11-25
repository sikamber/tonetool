"""Domain model for a piece.

``Piece`` is the serialized form (``piece.json``). The MusicXML file is the immutable source
for notes; everything about *how the piece is performed* (the sections, whose order is the
playback order) lives here and is the final authority. The importer only produces initial suggestions
(``Provenance.AUTO``); a user edit flips them to ``Provenance.USER``.

Measures are always referenced by 0-based document-order index, never by printed number.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 5


class Mode(StrEnum):
    MAJOR = "major"
    MINOR = "minor"


_NATURAL_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class Key(BaseModel):
    """The tonal key of a piece: a tonic and a mode.

    The tonic is spelled as a note name (``"Bb"``, ``"F#"``) because the spelling is what people
    expect to read; the pitch class is what colours and analysis use.
    """

    tonic: str = Field(pattern=r"^[A-G][#b]?$")
    mode: Mode

    @property
    def pitch_class(self) -> int:
        """0-11, with C = 0."""
        shift = {"#": 1, "b": -1}.get(self.tonic[1:], 0)
        return (_NATURAL_PITCH_CLASSES[self.tonic[0]] + shift) % 12

    @property
    def name(self) -> str:
        """For people: ``"Bb major"``."""
        return f"{self.tonic} {self.mode.value}"


class Provenance(StrEnum):
    AUTO = "auto"  # suggested by the importer, unreviewed
    USER = "user"  # confirmed or edited by a person


class Syllabic(StrEnum):
    """Where a syllable sits in its word, as in MusicXML."""

    SINGLE = "single"  # a whole word
    BEGIN = "begin"
    MIDDLE = "middle"
    END = "end"

    @property
    def continues(self) -> bool:
        """Whether the word goes on in the next syllable."""
        return self in (Syllabic.BEGIN, Syllabic.MIDDLE)


class Lyric(BaseModel):
    """One syllable sung on a note, for one lyric line of the score.

    ``number`` is the MusicXML lyric number. It is *not* the verse of the performance: a score may
    use one lyric line for verse 1 and verse 3 (different bars), so ``Section.lyric_number`` says
    which line a section sings. ``syllabic`` is as written in the score and not always reliable
    (some exporters mark a word's first syllable ``middle``); only ``Syllabic.continues`` is used.
    """

    number: str
    text: str
    syllabic: Syllabic = Syllabic.SINGLE


class Note(BaseModel):
    """One sounding pitch inside a measure."""

    pitch: int  # MIDI note number
    offset: float  # quarter notes from the start of the measure it sits in
    duration: float  # quarter notes, as notated: a tied note is not merged with its neighbours
    tied: bool = False  # continues a note held from before; has no attack of its own
    # the syllables sung on this note, one per lyric line; for a chord only its first note has them
    lyrics: list[Lyric] = Field(default_factory=list)


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
    # quarter-note BPM of a tempo mark on this measure, or None to keep the previous tempo (in
    # notated order); see Piece.measure_bpms. The first measure must have one.
    tempo: float | None = Field(default=None, gt=0)
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

    def describe(self, measures: list[Measure]) -> str:
        """Printed bar numbers: '1-4', or '5' for a single bar."""
        first, last = measures[self.start].number, measures[self.end].number
        return first if self.start == self.end else f"{first}-{last}"


class PlaybackOrder(BaseModel):
    """The performed order of measures, as a flat list of ranges.

    Not stored: ``Piece.playback_order`` generates it by playing the sections in order. Flat
    ranges are deliberately dumb: they can express any form (voltas, D.S. al Coda, skipped
    endings) and are trivial to validate.
    """

    segments: list[PlaybackSegment]

    @classmethod
    def from_measure_sequence(cls, sequence: list[int]) -> Self:
        """Compress e.g. [0,1,2,3,1,2,4] into segments [0-3], [1-2], [4-4]."""
        segments: list[PlaybackSegment] = []
        for index in sequence:
            if segments and segments[-1].end + 1 == index:
                segments[-1].end = index
            else:
                segments.append(PlaybackSegment(start=index, end=index))
        return cls(segments=segments)

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
        return " | ".join(segment.describe(measures) for segment in self.segments)


class Section(BaseModel):
    """A named stretch of the performance: one or more notated ranges, played in order.

    ``Piece.sections`` is in performance order, and the playback order is generated by playing
    every section's segments in turn. Sections hold the bars *as performed*, so the same notated
    bars can appear in several sections (verses 1 and 2), and a section can end in either of two
    voltas. Section-specific data (lyrics, say) has a natural home here later.
    """

    id: str
    name: str
    segments: list[PlaybackSegment] = Field(min_length=1)
    source: Provenance = Provenance.AUTO
    # which lyric line (``Lyric.number``) is sung in this section; None if it has no lyrics
    lyric_number: str | None = None

    def measure_sequence(self) -> list[int]:
        """The measure indices of this section in the order they are played."""
        return [m for segment in self.segments for m in segment.measures()]

    def describe(self, measures: list[Measure]) -> str:
        """Printed bar numbers of its ranges, e.g. '1-2, 4'."""
        return ", ".join(segment.describe(measures) for segment in self.segments)


class Piece(BaseModel):
    schema_version: int = SCHEMA_VERSION
    title: str
    source_file: str
    xml_sha256: (
        str  # detects drift if the MusicXML is replaced after structure was confirmed
    )
    measures: list[Measure]
    tracks: list[Track]
    sections: list[Section]  # in performance order; they define the playback order
    key: Key | None = None  # suggested by the importer from the score; a person can set it
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        """Check that sections, track ids, and voices agree with the measures."""
        count = len(self.measures)
        if not self.sections:
            raise ValueError("a piece needs at least one section: they define the playback order")
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("duplicate section ids")
        for section in self.sections:
            for segment in section.segments:
                if segment.start < 0 or segment.end >= count:
                    raise ValueError(
                        f"section {section.id!r}: segment {segment.start}-{segment.end} "
                        f"outside 0-{count - 1}"
                    )
        if self.measures[0].tempo is None:
            raise ValueError("the first measure needs a tempo: later measures inherit it")
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

    @property
    def playback_order(self) -> PlaybackOrder:
        """The performed order of measures: every section played in turn, contiguous bars merged."""
        return PlaybackOrder.from_measure_sequence(
            [m for section in self.sections for m in section.measure_sequence()]
        )

    def measure_bpms(self) -> list[float]:
        """The tempo of every measure in quarter-note BPM.

        A tempo mark applies to its own measure and to the measures after it in *notated* order,
        until the next mark. So a measure keeps its own tempo wherever the performance jumps to it.
        """
        bpms: list[float] = []
        current = 0.0  # replaced at measure 0, which validation guarantees has a tempo
        for measure in self.measures:
            if measure.tempo is not None:
                current = measure.tempo
            bpms.append(current)
        return bpms

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

    def to_json(self) -> str:
        """The piece as indented JSON, the form ``save`` writes."""
        return self.model_dump_json(indent=2) + "\n"

    def save(self, path: Path) -> None:
        """Write the piece to ``path`` as indented JSON."""
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a piece from a JSON file written by ``save``."""
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        version = data.get("schema_version") if isinstance(data, dict) else None
        if version == 2:
            data = cls._upgrade_v2(data)
            version = data["schema_version"]
        while version in (3, 4):  # 4 added optional lyrics, 5 an optional key: nothing to convert
            version += 1
            data["schema_version"] = version
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{path}: piece has schema version {version}, this version reads "
                f"{SCHEMA_VERSION}; re-import the score"
            )
        return cls.model_validate(data)

    @staticmethod
    def _upgrade_v2(data: dict[str, Any]) -> dict[str, Any]:
        """Schema 2 stored a resolved ``bpm`` on every measure; 3 stores ``tempo`` only on changes (returns v3)."""
        previous: float | None = None
        for measure in data["measures"]:
            bpm = measure.pop("bpm")
            measure["tempo"] = bpm if bpm != previous else None
            previous = bpm
        data["schema_version"] = 3
        return data
