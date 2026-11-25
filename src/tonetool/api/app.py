"""The FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from ..models import Piece
from .config import ServerConfig
from .library import PieceLibrary, PieceSummary


def create_app(config: ServerConfig | Path) -> FastAPI:
    """Build the app for a config (or the path of a config file)."""
    if isinstance(config, Path):
        config = ServerConfig.load(config)
    library = PieceLibrary(config)
    app = FastAPI(title="tonetool")

    @app.get("/api/pieces")
    def list_pieces() -> list[PieceSummary]:
        return library.summaries()

    @app.get("/api/pieces/{piece_id}")
    def get_piece(piece_id: str) -> Piece:
        try:
            return library.get(piece_id)
        except KeyError as error:
            raise HTTPException(404, str(error.args[0])) from error
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"could not load piece {piece_id!r}: {error}") from error

    return app
