"""Practice sets: one piece exported as a family of audio files, one voice at a time.

For every voice there are three files (the voice alone, the voice prominent, the voice panned
left against the rest panned right) plus one tutti file with everybody. Each file is just a
``MixSettings`` on top of the options shared by the whole set (tempo, section, count-in, ...),
so everything the ordinary renderer can do applies to every file.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .models import Piece
from .render import MixSettings, Renderer, TrackMix

PracticeKind = Literal["tutti", "solo", "prominent", "stereo"]
FORMATS = ("mp3", "wav")


def _slug(text: str) -> str:
    """File-name-safe version of ``text``: letters and digits are kept, runs of the rest become ``_``."""
    return re.sub(r"\W+", "_", text).strip("_")


class PracticeFile(BaseModel):
    """One file of a practice set: what kind it is, which voice it features, and how to mix it."""

    kind: PracticeKind
    track_id: str | None  # the featured voice; None for the tutti file
    name: str  # file name without extension
    settings: MixSettings


class PracticeSet:
    """The practice files for one piece.

    ``base`` carries the options shared by every file (tempo, section, loops, count-in, metronome);
    any per-track mix in it is ignored, since each file defines its own.

    ``others_volume`` is the *combined* level of all the other voices in the prominent files,
    relative to the featured voice (1.0 = as loud as it, 0.3 = about 10 dB below it). Voices add
    up, so with n other voices each one is scaled by 1/sqrt(n): four voices at 0.3 each would be
    louder than the featured voice itself. The stereo files use the same rule to balance the ears,
    so the featured voice on the left is as loud as everyone else together on the right.
    """

    STEREO_PAN = 1.0  # the featured voice goes fully left, everyone else fully right

    def __init__(
        self, piece: Piece, base: MixSettings | None = None, others_volume: float = 0.3
    ) -> None:
        """Remember the piece, the shared options, and the prominent files' background volume."""
        if others_volume < 0:
            raise ValueError("others_volume must not be negative")
        self.piece = piece
        self.base = base or MixSettings()
        self.others_volume = others_volume

    def files(self) -> list[PracticeFile]:
        """The files of the set: tutti first, then each voice's solo, prominent and stereo files.

        A piece with a single voice has nothing to contrast it with, so it only gets the tutti.
        """
        prefix = _slug(self.piece.title) or "practice"
        tutti = self.base.model_copy(deep=True)
        tutti.tracks = {}
        files = [PracticeFile(kind="tutti", track_id=None, name=f"{prefix}_tutti", settings=tutti)]
        if len(self.piece.tracks) < 2:
            return files

        slugs = self._voice_slugs()
        kinds: tuple[PracticeKind, ...] = ("solo", "prominent", "stereo")
        for track in self.piece.tracks:
            for kind in kinds:
                files.append(
                    PracticeFile(
                        kind=kind,
                        track_id=track.id,
                        name=f"{prefix}_{slugs[track.id]}_{kind}",
                        settings=self._mix(kind, track.id),
                    )
                )
        return files

    def export(
        self,
        folder: Path,
        fmt: str = "mp3",
        bitrate_kbps: int = 192,
        on_written: Callable[[Path], None] | None = None,
    ) -> list[Path]:
        """Render every file into ``folder`` (created if needed) and return their paths.

        ``on_written`` is called after each file, since a whole set can take a while.
        """
        if fmt not in FORMATS:
            raise ValueError(f"unsupported format {fmt!r}; use one of {', '.join(FORMATS)}")
        folder.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for file in self.files():
            path = Renderer(self.piece, file.settings).render_to_file(
                folder / f"{file.name}.{fmt}", bitrate_kbps=bitrate_kbps
            )
            paths.append(path)
            if on_written:
                on_written(path)
        return paths

    def _mix(self, kind: PracticeKind, track_id: str) -> MixSettings:
        """The shared options plus the per-track mix that defines ``kind`` for one voice."""
        # combined level of n voices grows like sqrt(n), so each of them gets 1/sqrt(n) of the total
        share = 1 / math.sqrt(len(self.piece.tracks) - 1)
        if kind == "solo":
            tracks = {track_id: TrackMix(), "*": TrackMix(mute=True)}
        elif kind == "prominent":
            tracks = {
                track_id: TrackMix(),
                "*": TrackMix(volume=self.others_volume * share),
            }
        elif kind == "stereo":
            tracks = {
                track_id: TrackMix(pan=-self.STEREO_PAN),
                "*": TrackMix(pan=self.STEREO_PAN, volume=share),
            }
        else:
            raise ValueError(f"no per-voice mix for {kind!r}")
        settings = self.base.model_copy(deep=True)
        settings.tracks = tracks
        return settings

    def _voice_slugs(self) -> dict[str, str]:
        """File-name part for each track id: its label, with the id added if labels collide."""
        slugs = {t.id: _slug(t.label) or t.id for t in self.piece.tracks}
        if len(set(slugs.values())) < len(slugs):
            slugs = {track_id: f"{slug}_{track_id}" for track_id, slug in slugs.items()}
        return slugs
