"""The FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..models import Piece
from .config import ServerConfig
from .editor import PieceEdits
from .errors import ClientError, Conflict
from .library import PieceLibrary, PieceSummary


def create_app(config: ServerConfig | Path) -> FastAPI:
    """Build the app for a config (or the path of a config file)."""
    if isinstance(config, Path):
        config = ServerConfig.load(config)
    library = PieceLibrary(config)
    app = FastAPI(title="tonetool")
    upload_limit = config.max_upload_mb * 1024 * 1024

    def failure(error: Exception, piece_id: str | None = None) -> HTTPException:
        """The HTTP error for something the library raised."""
        if isinstance(error, KeyError):
            return HTTPException(404, str(error.args[0]))
        if isinstance(error, Conflict):
            return HTTPException(409, str(error))
        if isinstance(error, ClientError):
            return HTTPException(422, str(error))
        return HTTPException(500, f"could not load piece {piece_id!r}: {error}")

    async def read_upload(file: UploadFile) -> bytes:
        """The uploaded bytes, refusing files over the size limit."""
        data = await file.read(upload_limit + 1)
        if len(data) > upload_limit:
            raise HTTPException(413, f"file is larger than {config.max_upload_mb} MB")
        return data

    @app.get("/api/pieces")
    def list_pieces() -> list[PieceSummary]:
        return library.summaries()

    @app.get("/api/pieces/{piece_id}")
    def get_piece(piece_id: str) -> Piece:
        try:
            return library.get(piece_id)
        except (KeyError, OSError, ValueError) as error:
            raise failure(error, piece_id) from error

    @app.post("/api/pieces", status_code=201)
    async def import_piece(file: UploadFile = File(...), id: str | None = Form(None)) -> PieceSummary:
        data = await read_upload(file)
        try:
            piece_id = await run_in_threadpool(library.import_score, file.filename or "", data, id)
        except (Conflict, ClientError) as error:
            raise failure(error) from error
        return next(s for s in library.summaries() if s.id == piece_id)

    @app.put("/api/pieces/{piece_id}")
    def edit_piece(piece_id: str, edits: PieceEdits) -> Piece:
        try:
            return library.edit(piece_id, edits)
        except (KeyError, Conflict, ClientError, OSError) as error:
            raise failure(error, piece_id) from error

    @app.post("/api/pieces/{piece_id}/score")
    async def replace_score(piece_id: str, file: UploadFile = File(...)) -> Piece:
        data = await read_upload(file)
        try:
            return await run_in_threadpool(library.replace_score, piece_id, file.filename or "", data)
        except (KeyError, Conflict, ClientError, OSError) as error:
            raise failure(error, piece_id) from error

    @app.delete("/api/pieces/{piece_id}", status_code=204)
    def delete_piece(piece_id: str) -> Response:
        try:
            library.delete(piece_id)
        except (KeyError, Conflict) as error:
            raise failure(error, piece_id) from error
        return Response(status_code=204)

    return app
