"""Thin command-line wrapper: ``tonetool import|show|serve|hash-password|make-secret|openapi``. Logic lives in the package."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .importer import ScoreImporter
from .models import Piece


def cmd_import(args: argparse.Namespace) -> None:
    """Import a MusicXML score, save its piece JSON, and print a summary."""
    output = args.output or args.score.with_suffix(".piece.json")
    kept = None
    if args.keep_sections:
        if not output.exists():
            raise ValueError(f"--keep-sections: {output} does not exist yet")
        kept = Piece.load(output).sections
    piece = ScoreImporter(args.score).run(keep_sections=kept)
    piece.save(output)
    print(f"wrote {output}")
    _show(piece)


def _show(piece: Piece) -> None:
    """Print tracks, sections, playback order, and any warnings for a piece."""
    key = f", key {piece.key.name}" if piece.key else ""
    print(f"{piece.title}: {len(piece.measures)} measures, {len(piece.tracks)} tracks{key}")
    for track in piece.tracks:
        count = sum(len(v.notes) for v in piece.voice_measures(track.id))
        print(f"  track {track.id:8} {track.label} [{track.voice.value}] {count} notes")
    tempos = [f"{m.tempo:g} from bar {m.number}" for m in piece.measures if m.tempo is not None]
    print(f"  tempo (quarter-note BPM): {', '.join(tempos)}")
    for section in piece.sections:
        bars = section.describe(piece.measures)
        lyrics = f", lyric line {section.lyric_number}" if section.lyric_number else ""
        print(f"  section {section.id}: {section.name} (bars {bars}{lyrics}) [{section.source.value}]")
    print(f"  playback order: {piece.playback_order.describe(piece.measures)}")
    for warning in piece.warnings:
        print(f"  WARNING: {warning}")


def cmd_show(args: argparse.Namespace) -> None:
    """Load a saved piece JSON and print its summary."""
    _show(Piece.load(args.piece))


def cmd_serve(args: argparse.Namespace) -> None:
    """Run the web API for the pieces linked in the config file."""
    import uvicorn

    from .api.app import create_app
    from .api.auth import require_auth_for_public_host
    from .api.config import ServerConfig

    config = ServerConfig.load(args.config)
    require_auth_for_public_host(args.host, config)
    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        proxy_headers=True,  # behind a proxy, the client address comes from its X-Forwarded-For
        forwarded_allow_ips=args.forwarded_allow_ips,
    )


def cmd_hash_password(args: argparse.Namespace) -> None:
    """Ask for a password and print its hash, for the config's ``password_hash``."""
    import getpass

    from .api.auth import PasswordHasher

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Again: "):
        raise ValueError("the two passwords differ")
    if len(password) < 10:
        raise ValueError("use at least 10 characters")
    print(PasswordHasher.hash(password))


def cmd_make_secret(args: argparse.Namespace) -> None:
    """Print a random secret for signing session cookies."""
    import secrets

    print(secrets.token_urlsafe(48))


def cmd_openapi(args: argparse.Namespace) -> None:
    """Print the API's OpenAPI schema (the frontend generates its types from it)."""
    from .api.app import create_app
    from .api.config import ServerConfig

    print(json.dumps(create_app(ServerConfig()).openapi(), indent=2))


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse arguments and dispatch. User errors print a message and exit 1."""
    parser = argparse.ArgumentParser(prog="tonetool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="MusicXML -> piece.json (with suggested structure)")
    p_import.add_argument("score", type=Path)
    p_import.add_argument("-o", "--output", type=Path)
    p_import.add_argument(
        "--keep-sections",
        action="store_true",
        help="re-import notes and lyrics but keep the sections already in the output file",
    )
    p_import.set_defaults(func=cmd_import)

    p_show = sub.add_parser("show", help="print tracks, sections, playback order, warnings")
    p_show.add_argument("piece", type=Path)
    p_show.set_defaults(func=cmd_show)

    p_serve = sub.add_parser("serve", help="run the web API for the pieces in a config file")
    p_serve.add_argument(
        "--config", type=Path, default=Path(os.environ.get("TONETOOL_CONFIG", "tonetool.toml"))
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="refuses non-local addresses unless a login is set up")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--forwarded-allow-ips",
        default="127.0.0.1",
        help="proxies whose X-Forwarded-For is trusted (comma separated, or * if only the proxy can reach the server)",
    )
    p_serve.set_defaults(func=cmd_serve)

    p_hash = sub.add_parser("hash-password", help="hash a password for the config's [auth] password_hash")
    p_hash.set_defaults(func=cmd_hash_password)

    p_secret = sub.add_parser("make-secret", help="print a random secret for signing session cookies")
    p_secret.set_defaults(func=cmd_make_secret)

    p_openapi = sub.add_parser("openapi", help="print the API's OpenAPI schema as JSON")
    p_openapi.set_defaults(func=cmd_openapi)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (KeyError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
