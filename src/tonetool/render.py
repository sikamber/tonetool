"""Practice-audio rendering: Piece + MixSettings -> WAV or MP3.

No system binaries needed (numpy, stdlib ``wave``, and ``lameenc`` which bundles LAME), so it
runs anywhere pip does. ``Synth`` is the seam where a soundfont-based synth can replace
``AdditiveSynth``.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, Protocol

import lameenc
import numpy as np
from pydantic import BaseModel, Field

from .models import Piece, VoiceKind
from .timeline import Timeline, TimelineBuilder


class TrackMix(BaseModel):
    volume: float = Field(default=1.0, ge=0.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)  # -1 left, +1 right
    mute: bool = False


class MixSettings(BaseModel):
    """Everything that varies between exports of the same piece."""

    tempo_scale: float = Field(default=1.0, gt=0.0)
    # keys: track id ("T1"), track label (case-insensitive), or voice kind ("S", "A", "T", "B")
    tracks: dict[str, TrackMix] = Field(default_factory=dict)
    section: str | None = None  # render only this section, as performed (its own voltas etc.)
    loops: int = Field(default=1, ge=1)  # how many times to repeat the section
    count_in_beats: int = Field(default=0, ge=0)
    metronome: bool = False
    metronome_volume: float = Field(default=0.5, ge=0.0)
    sample_rate: int = 44100

    @classmethod
    def focus_on(cls, keys: list[str], others_volume: float = 0.3, **kwargs: Any) -> MixSettings:
        """Convenience: ``keys`` at full volume and panned left, everyone else quieter and right."""
        settings = cls.model_validate(kwargs)
        settings.tracks = {k: TrackMix(volume=1.0, pan=-0.6) for k in keys}
        settings.tracks["*"] = TrackMix(volume=others_volume, pan=0.6)
        return settings

    def resolve(self, piece: Piece) -> dict[str, TrackMix]:
        """Map every track id to its mix. Specific keys beat voice-kind keys beat ``"*"``."""
        resolved = {t.id: self.tracks.get("*", TrackMix()) for t in piece.tracks}
        by_kind = {k.value: k for k in VoiceKind}
        used: set[str] = {"*"}
        for key, mix in self.tracks.items():
            if key in by_kind:
                for t in piece.tracks:
                    if t.voice.value == key:
                        resolved[t.id] = mix
                used.add(key)
        for key, mix in self.tracks.items():
            for t in piece.tracks:
                if key in (t.id, t.label) or key.lower() == t.label.lower():
                    resolved[t.id] = mix
                    used.add(key)
        unknown = set(self.tracks) - used
        if unknown:
            known = [t.id for t in piece.tracks] + sorted({t.voice.value for t in piece.tracks}) + ["*"]
            raise KeyError(f"mix refers to unknown tracks {sorted(unknown)}; known: {known}")
        return resolved


class Synth(Protocol):
    def render_note(
        self, pitch: int, duration_sec: float, sample_rate: int, attack: bool = True
    ) -> np.ndarray:
        """Mono float32 samples for one note, including any release tail.

        ``attack=False`` means the note enters mid-hold: avoid an audible re-strike.
        """
        ...


class AdditiveSynth:
    """A plain, steady organ-like tone: easy to pick a pitch out of, unlike a choir pad."""

    HARMONICS = (1.0, 0.45, 0.22, 0.1)
    ATTACK = 0.02
    DECLICK = 0.005  # fade-in used instead of the attack for notes entering mid-hold
    RELEASE = 0.08

    def render_note(
        self, pitch: int, duration_sec: float, sample_rate: int, attack: bool = True
    ) -> np.ndarray:
        """A few harmonics with a short attack and release; steady pitch, no vibrato."""
        frequency = 440.0 * 2 ** ((pitch - 69) / 12)
        total = duration_sec + self.RELEASE
        t = np.arange(int(total * sample_rate)) / sample_rate
        wave_ = sum(w * np.sin(2 * np.pi * frequency * (i + 1) * t) for i, w in enumerate(self.HARMONICS))
        envelope = np.minimum(1.0, t / (self.ATTACK if attack else self.DECLICK))
        release_start = duration_sec
        tail = t > release_start
        envelope[tail] *= np.clip(1.0 - (t[tail] - release_start) / self.RELEASE, 0.0, 1.0)
        return (wave_ * envelope / sum(self.HARMONICS) * 0.35).astype(np.float32)


class Renderer:
    def __init__(self, piece: Piece, settings: MixSettings | None = None, synth: Synth | None = None) -> None:
        """Use ``settings`` (defaults if None) and ``synth`` (``AdditiveSynth`` if None)."""
        self.piece = piece
        self.settings = settings or MixSettings()
        self.synth = synth or AdditiveSynth()

    def timeline(self) -> Timeline:
        """The unrolled timeline to render: the whole piece, or the chosen section repeated ``loops`` times."""
        builder = TimelineBuilder(self.piece, tempo_scale=self.settings.tempo_scale)
        if self.settings.section is None:
            return builder.build()
        section = self.piece.section(self.settings.section)
        return builder.build(section.measure_sequence() * self.settings.loops)

    def render(self) -> np.ndarray:
        """Stereo float32 array of shape (samples, 2)."""
        sr = self.settings.sample_rate
        timeline = self.timeline()
        mixes = self.settings.resolve(self.piece)

        count_in = self._count_in_seconds(timeline)
        tail = AdditiveSynth.RELEASE + 0.5
        out = np.zeros((int((count_in + timeline.duration + tail) * sr), 2), dtype=np.float32)

        for scheduled in timeline.notes:
            mix = mixes[scheduled.track_id]
            if mix.mute or mix.volume == 0:
                continue
            samples = self.synth.render_note(
                scheduled.pitch, scheduled.duration_sec, sr, attack=scheduled.attack
            )
            angle = (mix.pan + 1) * np.pi / 4  # equal-power panning
            start = int((count_in + scheduled.start_sec) * sr)
            end = min(start + len(samples), len(out))
            chunk = samples[: end - start] * mix.volume
            out[start:end, 0] += chunk * np.cos(angle)
            out[start:end, 1] += chunk * np.sin(angle)

        self._add_clicks(out, timeline, count_in)
        peak = float(np.abs(out).max())
        if peak > 0.95:
            out *= 0.95 / peak
        return out

    def render_to_file(self, path: Path, bitrate_kbps: int = 192) -> Path:
        """Write ``path``; the format follows the suffix (.mp3 or .wav)."""
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            return self.render_to_mp3(path, bitrate_kbps)
        if suffix == ".wav":
            return self.render_to_wav(path)
        raise ValueError(f"unsupported output format {suffix!r}; use .mp3 or .wav")

    def _pcm(self) -> bytes:
        """Interleaved little-endian 16-bit stereo."""
        return (np.clip(self.render(), -1.0, 1.0) * 32767).astype("<i2").tobytes()

    def render_to_wav(self, path: Path) -> Path:
        """Write 16-bit stereo WAV to ``path``."""
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(self.settings.sample_rate)
            wav.writeframes(self._pcm())
        return path

    def render_to_mp3(self, path: Path, bitrate_kbps: int = 192) -> Path:
        """Write MP3 to ``path`` at the given bitrate (encoded in-process with LAME)."""
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(bitrate_kbps)
        encoder.set_in_sample_rate(self.settings.sample_rate)
        encoder.set_channels(2)
        encoder.set_quality(2)  # 2 = high quality, still fast
        path.write_bytes(bytes(encoder.encode(self._pcm())) + bytes(encoder.flush()))
        return path

    # -- metronome ----------------------------------------------------------------------------

    def _count_in_seconds(self, timeline: Timeline) -> float:
        """Length of the count-in, using the first measure's beat length."""
        if self.settings.count_in_beats == 0 or not timeline.spans:
            return 0.0
        return self.settings.count_in_beats * timeline.spans[0].beat_secs

    def _add_clicks(self, out: np.ndarray, timeline: Timeline, count_in: float) -> None:
        """Mix the count-in and (if enabled) metronome clicks into ``out`` in place."""
        if not timeline.spans:
            return
        sr = self.settings.sample_rate
        volume = self.settings.metronome_volume
        first = timeline.spans[0]
        times: list[tuple[float, bool]] = [
            (i * first.beat_secs, i % max(first.beats, 1) == 0) for i in range(self.settings.count_in_beats)
        ]
        if self.settings.metronome:
            for span in timeline.spans:
                times += [(count_in + span.start_sec + b * span.beat_secs, b == 0) for b in range(span.beats)]
        for when, accent in times:
            click = self._click(sr, accent) * volume
            start = int(when * sr)
            end = min(start + len(click), len(out))
            if start < end:
                out[start:end] += click[: end - start, None]

    @staticmethod
    def _click(sample_rate: int, accent: bool) -> np.ndarray:
        """A short decaying sine burst; higher pitch for the accented first beat."""
        t = np.arange(int(0.04 * sample_rate)) / sample_rate
        frequency = 1500.0 if accent else 1000.0
        return (np.sin(2 * np.pi * frequency * t) * np.exp(-t * 90) * 0.5).astype(np.float32)
