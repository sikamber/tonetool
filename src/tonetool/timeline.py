"""Unrolling: apply a playback order to a piece to get absolute-time events.

This is the one place that knows how to turn notated structure into performance time. The audio
renderer consumes it today; a live React player (and cursor following) can consume the same data
later, which is why it carries the time -> source-measure map.
"""

from __future__ import annotations

from bisect import bisect_right

from pydantic import BaseModel

from .models import Piece, PlaybackOrder


class MeasureSpan(BaseModel):
    """One measure as it is actually played: when, and which notated measure it came from."""

    position: int  # 0-based position in the performed sequence
    source_measure: int  # notated measure index
    start_sec: float
    end_sec: float
    beat_secs: float  # duration of one metronome beat in this measure
    beats: int


class ScheduledNote(BaseModel):
    track_id: str
    pitch: int
    start_sec: float
    duration_sec: float
    source_measure: int
    position: int  # performed-measure position the note starts in
    attack: bool = True  # False: enters a note that is already held, so no re-strike is wanted


class Timeline(BaseModel):
    spans: list[MeasureSpan]
    notes: list[ScheduledNote]

    @property
    def duration(self) -> float:
        """Total length in seconds."""
        return self.spans[-1].end_sec if self.spans else 0.0

    def span_at(self, seconds: float) -> MeasureSpan:
        """The performed measure sounding at ``seconds`` (for cursor following)."""
        starts = [s.start_sec for s in self.spans]
        return self.spans[max(0, bisect_right(starts, seconds) - 1)]

    def notes_for(self, track_id: str) -> list[ScheduledNote]:
        """The scheduled notes belonging to one track."""
        return [n for n in self.notes if n.track_id == track_id]


def _ends_at(note: ScheduledNote, seconds: float) -> bool:
    """Whether ``note`` stops sounding exactly at ``seconds`` (floating-point tolerant)."""
    return abs(note.start_sec + note.duration_sec - seconds) < 1e-6


class TimelineBuilder:
    """Builds a ``Timeline`` from a piece and a measure sequence.

    ``tempo_scale`` multiplies the notated tempo (0.8 = 20% slower).

    Ties are resolved here, in *performed* order. A note flagged ``tied`` extends the held note of
    the same pitch if that note ends exactly where this one starts (any chain length, across
    barlines, voltas, and jumps). If there is nothing to continue (a jump or loop point landed
    mid-tie), it sounds for its own duration without an attack, as a singer entering a held note.
    """

    def __init__(self, piece: Piece, tempo_scale: float = 1.0) -> None:
        """Remember the piece and the tempo scale (1.0 = as notated)."""
        if tempo_scale <= 0:
            raise ValueError("tempo_scale must be positive")
        self.piece = piece
        self.tempo_scale = tempo_scale

    def build(self, order: PlaybackOrder | list[int] | None = None) -> Timeline:
        """Unroll ``order`` (a PlaybackOrder or explicit measure list; default: the piece's own) into a Timeline."""
        sequence = self._sequence(order)
        spans: list[MeasureSpan] = []
        notes: list[ScheduledNote] = []
        held: dict[tuple[str, int], ScheduledNote] = {}  # (track, pitch) -> latest note of that pitch
        bpms = self.piece.measure_bpms()
        clock = 0.0
        for position, index in enumerate(sequence):
            measure = self.piece.measures[index]
            seconds_per_quarter = 60.0 / (bpms[index] * self.tempo_scale)
            length_sec = measure.length * seconds_per_quarter
            spans.append(
                MeasureSpan(
                    position=position,
                    source_measure=index,
                    start_sec=clock,
                    end_sec=clock + length_sec,
                    beat_secs=measure.beat_length * seconds_per_quarter,
                    beats=max(1, round(measure.length / measure.beat_length)),
                )
            )
            for track_id, voice in measure.voices.items():
                for n in voice.notes:
                    start = clock + n.offset * seconds_per_quarter
                    duration = n.duration * seconds_per_quarter
                    if duration <= 0:
                        continue
                    previous = held.get((track_id, n.pitch))
                    if n.tied and previous is not None and _ends_at(previous, start):
                        previous.duration_sec += duration
                        continue
                    scheduled = ScheduledNote(
                        track_id=track_id,
                        pitch=n.pitch,
                        start_sec=start,
                        duration_sec=duration,
                        source_measure=index,
                        position=position,
                        attack=not n.tied,
                    )
                    notes.append(scheduled)
                    held[(track_id, n.pitch)] = scheduled
            clock += length_sec
        return Timeline(spans=spans, notes=notes)

    def _sequence(self, order: PlaybackOrder | list[int] | None) -> list[int]:
        """Resolve the ``order`` argument to a validated list of measure indices."""
        if order is None:
            order = self.piece.playback_order
        if isinstance(order, PlaybackOrder):
            order.validate_against(len(self.piece.measures))
            return order.measure_sequence()
        bad = [i for i in order if not 0 <= i < len(self.piece.measures)]
        if bad:
            raise ValueError(f"measure indices out of range: {bad}")
        return list(order)
