"""Server configuration: which piece files the backend serves."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PieceEntry(BaseModel):
    """One piece the server exposes: an id (letters of any script, digits, ``_``, ``-``) and its file."""

    id: str = Field(pattern=r"^[\w-]+$")  # \w is Unicode: æ, ø, å are fine
    path: Path


class AuthConfig(BaseModel):
    """Who may use the app: one user. Without this section there is no login (for local use only).

    ``password_hash`` comes from ``tonetool hash-password`` and ``secret`` signs the session cookies
    (use something long and random: ``tonetool make-secret``). Each value can instead be given as an
    environment variable (``TONETOOL_USERNAME``, ``TONETOOL_PASSWORD_HASH``, ``TONETOOL_SECRET``,
    ``TONETOOL_SESSION_HOURS``, ``TONETOOL_COOKIE_SECURE``), which wins over the file, so secrets
    need not be kept in it. ``cookie_secure`` should only be switched off for plain-HTTP trials.
    """

    username: str = Field(min_length=1)
    password_hash: str = Field(min_length=1)
    secret: str = Field(min_length=32)
    session_hours: int = Field(default=12, gt=0)
    cookie_secure: bool = True


class ServerConfig(BaseModel):
    """The contents of ``tonetool.toml``.

    ``[[pieces]]`` entries link ids to piece files; ``library`` is a folder where pieces imported in
    the app are stored (and which is scanned for them). Relative paths resolve against the directory
    of the config file, so a config and its pieces can be moved together.
    """

    pieces: list[PieceEntry] = Field(default_factory=list)
    # Folder for pieces imported in the app, one subfolder per piece. None: imports are disabled.
    library: Path | None = None
    max_upload_mb: int = Field(default=25, gt=0)
    # what a compressed (.mxl) score may expand to, and how many pieces the library may hold
    max_unpacked_mb: int = Field(default=100, gt=0)
    max_pieces: int = Field(default=200, gt=0)
    auth: AuthConfig | None = None
    # The built frontend (frontend/dist), served by the API itself so one process does everything.
    static_dir: Path | None = None

    @model_validator(mode="after")
    def _unique_ids(self) -> ServerConfig:
        """Reject two entries with the same id."""
        ids = [entry.id for entry in self.pieces]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate piece ids in config")
        return self

    @classmethod
    def load(cls, path: Path, environ: Mapping[str, str] | None = None) -> ServerConfig:
        """Read a TOML config file, apply the ``TONETOOL_*`` login variables, resolve relative paths."""
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        auth = cls._auth_from(raw.get("auth", {}), os.environ if environ is None else environ)
        if auth:
            raw["auth"] = auth
        config = cls.model_validate(raw)
        base = path.resolve().parent
        for entry in config.pieces:
            if not entry.path.is_absolute():
                entry.path = base / entry.path
        if config.library is not None and not config.library.is_absolute():
            config.library = base / config.library
        if config.static_dir is not None and not config.static_dir.is_absolute():
            config.static_dir = base / config.static_dir
        return config

    @staticmethod
    def _auth_from(section: dict[str, Any], environ: Mapping[str, str]) -> dict[str, Any]:
        """The ``[auth]`` table with environment variables laid over it; empty if no login is set up."""
        auth = dict(section)
        for key, variable in (
            ("username", "TONETOOL_USERNAME"),
            ("password_hash", "TONETOOL_PASSWORD_HASH"),
            ("secret", "TONETOOL_SECRET"),
        ):
            if environ.get(variable):
                auth[key] = environ[variable]
        if not any(key in auth for key in ("username", "password_hash", "secret")):
            return {}  # no login configured; ignore stray option variables
        if environ.get("TONETOOL_SESSION_HOURS"):
            auth["session_hours"] = int(environ["TONETOOL_SESSION_HOURS"])
        if environ.get("TONETOOL_COOKIE_SECURE"):
            auth["cookie_secure"] = environ["TONETOOL_COOKIE_SECURE"].strip().lower() in ("1", "true", "yes", "on")
        return auth
