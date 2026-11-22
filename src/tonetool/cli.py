"""Thin command-line wrapper: ``tonetool import|show|render``. All logic lives in the package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .importer import ScoreImporter
from .models import Piece
from .render import MixSettings, Renderer, TrackMix


def _parse_volume(items: list[str]) -> dict[str, TrackMix]:
    """['S=1', 'A=0.3:-0.5'] -> {'S': TrackMix(volume=1), 'A': TrackMix(volume=0.3, pan=-0.5)}"""
    result: dict[str, TrackMix] = {}
    for item in items:
        key, _, value = item.partition("=")
        volume, _, pan = value.partition(":")
        result[key] = TrackMix(volume=float(volume), pan=float(pan) if pan else 0.0)
    return result


def cmd_import(args: argparse.Namespace) -> None:
    """Import a MusicXML score, save its piece JSON, and print a summary."""
    piece = ScoreImporter(args.score).run()
    output = args.output or args.score.with_suffix(".piece.json")
    piece.save(output)
    print(f"wrote {output}")
    _show(piece)


def _show(piece: Piece) -> None:
    """Print tracks, sections, playback order, and any warnings for a piece."""
    print(f"{piece.title}: {len(piece.measures)} measures, {len(piece.tracks)} tracks")
    for track in piece.tracks:
        count = sum(len(v.notes) for v in piece.voice_measures(track.id))
        print(f"  track {track.id:8} {track.label} [{track.voice.value}] {count} notes")
    for section in piece.sections:
        first, last = piece.measures[section.start].number, piece.measures[section.end].number
        print(f"  section {section.id}: {section.name} (bars {first}-{last}) [{section.source.value}]")
    print(f"  order [{piece.playback_order.source.value}]: {piece.playback_order.describe(piece.measures)}")
    for warning in piece.warnings:
        print(f"  WARNING: {warning}")


def cmd_show(args: argparse.Namespace) -> None:
    """Load a saved piece JSON and print its summary."""
    _show(Piece.load(args.piece))


def cmd_render(args: argparse.Namespace) -> None:
    """Render a piece to audio; command-line flags override the --params file."""
    piece = Piece.load(args.piece)
    if args.params:
        settings = MixSettings.model_validate_json(args.params.read_text())
    else:
        settings = MixSettings()
    # flags override the params file
    if args.tempo is not None:
        settings.tempo_scale = args.tempo
    if args.section is not None:
        settings.section = args.section
    if args.loops is not None:
        settings.loops = args.loops
    if args.count_in is not None:
        settings.count_in_beats = args.count_in
    if args.metronome:
        settings.metronome = True
    settings.tracks.update(_parse_volume(args.volume))
    output = args.output or args.piece.with_suffix(".mp3")
    Renderer(piece, settings).render_to_file(output, bitrate_kbps=args.bitrate)
    print(f"wrote {output}")


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse arguments and dispatch. User errors print a message and exit 1."""
    parser = argparse.ArgumentParser(prog="tonetool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="MusicXML -> piece.json (with suggested structure)")
    p_import.add_argument("score", type=Path)
    p_import.add_argument("-o", "--output", type=Path)
    p_import.set_defaults(func=cmd_import)

    p_show = sub.add_parser("show", help="print tracks, sections, playback order, warnings")
    p_show.add_argument("piece", type=Path)
    p_show.set_defaults(func=cmd_show)

    p_render = sub.add_parser("render", help="piece.json -> practice audio (WAV)")
    p_render.add_argument("piece", type=Path)
    p_render.add_argument("-o", "--output", type=Path)
    p_render.add_argument("--params", type=Path, help="MixSettings JSON file")
    p_render.add_argument("--tempo", type=float, help="tempo scale, e.g. 0.8")
    p_render.add_argument("--section", help="render only this section id")
    p_render.add_argument("--loops", type=int)
    p_render.add_argument("--count-in", type=int, dest="count_in", help="count-in beats")
    p_render.add_argument("--metronome", action="store_true")
    p_render.add_argument("--bitrate", type=int, default=192, help="MP3 bitrate in kbps (default 192)")
    p_render.add_argument(
        "--volume", action="append", default=[], metavar="TRACK=VOL[:PAN]",
        help="per-track mix; TRACK is a track id, label, voice letter (S/A/T/B), or * for the rest",
    )
    p_render.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (KeyError, ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
