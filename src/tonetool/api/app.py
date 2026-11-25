"""The FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..models import Piece
from .auth import Authenticator, LoginFailed, TooManyAttempts
from .config import ServerConfig
from .editor import PieceEdits
from .errors import ClientError, Conflict
from .library import PieceLibrary, PieceSummary

SESSION_COOKIE = "tonetool_session"

# Only this site's own files; inline styles stay allowed because the UI sets some at run time.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class Credentials(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class SessionStatus(BaseModel):
    """Whether a login is needed, and whether this browser has one."""

    auth_required: bool
    authenticated: bool
    username: str | None = None


def create_app(config: ServerConfig | Path) -> FastAPI:
    """Build the app for a config (or the path of a config file)."""
    if isinstance(config, Path):
        config = ServerConfig.load(config)
    library = PieceLibrary(config)
    authenticator = Authenticator(config.auth) if config.auth else None
    app = FastAPI(title="tonetool")
    upload_limit = config.max_upload_mb * 1024 * 1024

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_user(request: Request) -> str | None:
        """The logged-in user, or None; always None if there is no login."""
        if authenticator is None:
            return None
        return authenticator.user_for(request.cookies.get(SESSION_COOKIE))

    def require_user(request: Request) -> None:
        """Dependency: 401 unless logged in (or there is no login at all)."""
        if authenticator is not None and current_user(request) is None:
            raise HTTPException(401, "login required")

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

    # -- open to everyone ---------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/session")
    def session_status(request: Request) -> SessionStatus:
        user = current_user(request)
        return SessionStatus(auth_required=authenticator is not None, authenticated=user is not None or authenticator is None, username=user)

    @app.post("/api/session")
    def log_in(credentials: Credentials, request: Request, response: Response) -> SessionStatus:
        if authenticator is None or config.auth is None:
            raise HTTPException(409, "login is not enabled on this server")
        client = request.client.host if request.client else "unknown"
        try:
            token = authenticator.login(credentials.username, credentials.password, client)
        except TooManyAttempts as error:
            raise HTTPException(429, str(error), headers={"Retry-After": str(error.retry_after)}) from error
        except LoginFailed as error:
            raise HTTPException(401, "wrong username or password") from error
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=config.auth.session_hours * 3600,
            httponly=True,
            secure=config.auth.cookie_secure,
            samesite="strict",
            path="/",
        )
        return SessionStatus(auth_required=True, authenticated=True, username=config.auth.username)

    @app.delete("/api/session", status_code=204)
    def log_out() -> Response:
        response = Response(status_code=204)
        secure = config.auth.cookie_secure if config.auth else True
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="strict")
        return response

    # -- the library: login required ----------------------------------------------------------

    pieces = APIRouter(dependencies=[Depends(require_user)])

    @pieces.get("/api/pieces")
    def list_pieces() -> list[PieceSummary]:
        return library.summaries()

    @pieces.get("/api/pieces/{piece_id}")
    def get_piece(piece_id: str) -> Piece:
        try:
            return library.get(piece_id)
        except (KeyError, OSError, ValueError) as error:
            raise failure(error, piece_id) from error

    @pieces.post("/api/pieces", status_code=201)
    async def import_piece(file: UploadFile = File(...), id: str | None = Form(None)) -> PieceSummary:
        data = await read_upload(file)
        try:
            piece_id = await run_in_threadpool(library.import_score, file.filename or "", data, id)
        except (Conflict, ClientError) as error:
            raise failure(error) from error
        return next(s for s in library.summaries() if s.id == piece_id)

    @pieces.put("/api/pieces/{piece_id}")
    def edit_piece(piece_id: str, edits: PieceEdits) -> Piece:
        try:
            return library.edit(piece_id, edits)
        except (KeyError, Conflict, ClientError, OSError) as error:
            raise failure(error, piece_id) from error

    @pieces.post("/api/pieces/{piece_id}/score")
    async def replace_score(piece_id: str, file: UploadFile = File(...)) -> Piece:
        data = await read_upload(file)
        try:
            return await run_in_threadpool(library.replace_score, piece_id, file.filename or "", data)
        except (KeyError, Conflict, ClientError, OSError) as error:
            raise failure(error, piece_id) from error

    @pieces.delete("/api/pieces/{piece_id}", status_code=204)
    def delete_piece(piece_id: str) -> Response:
        try:
            library.delete(piece_id)
        except (KeyError, Conflict) as error:
            raise failure(error, piece_id) from error
        return Response(status_code=204)

    app.include_router(pieces)

    # The built frontend, last, so that it never shadows an API route.
    if config.static_dir is not None:
        if not config.static_dir.is_dir():
            raise ValueError(f"static_dir {config.static_dir} is not a folder (build the frontend first)")
        app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="frontend")

    return app
