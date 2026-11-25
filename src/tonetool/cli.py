"""Thin command-line wrapper: ``tonetool import|show|serve|openapi``. Logic lives in the package."""

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
    print(f"{piece.title}: {len(piece.measures)} measures, {len(piece.tracks)} tracks")
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

    uvicorn.run(create_app(args.config), host=args.host, port=args.port)


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
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

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
