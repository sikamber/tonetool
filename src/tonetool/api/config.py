"""Server configuration: which piece files the backend serves."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class PieceEntry(BaseModel):
    """One piece the server exposes: an id (letters of any script, digits, ``_``, ``-``) and its file."""

    id: str = Field(pattern=r"^[\w-]+$")  # \w is Unicode: æ, ø, å are fine
    path: Path


class ServerConfig(BaseModel):
    """The contents of ``tonetool.toml``.

    ``[[pieces]]`` entries link ids to piece files. Relative paths resolve against the directory
    of the config file, so a config and its pieces can be moved together.
    """

    pieces: list[PieceEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> ServerConfig:
        """Reject two entries with the same id."""
        ids = [entry.id for entry in self.pieces]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate piece ids in config")
        return self

    @classmethod
    def load(cls, path: Path) -> ServerConfig:
        """Read a TOML config file and resolve its relative piece paths."""
        config = cls.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        base = path.resolve().parent
        for entry in config.pieces:
            if not entry.path.is_absolute():
                entry.path = base / entry.path
        return config
