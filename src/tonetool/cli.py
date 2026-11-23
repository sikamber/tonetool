"""Thin command-line wrapper: ``tonetool import|show|render|practice``. Logic lives in the package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .importer import ScoreImporter
from .models import Piece
from .practice import FORMATS, PracticeSet
from .render import MixSettings, Renderer, TrackMix


def _parse_volume(items: list[str]) -> dict[str, TrackMix]:
    """['S=1', 'A=0.3:-0.5'] -> {'S': TrackMix(volume=1), 'A': TrackMix(volume=0.3, pan=-0.5)}"""
    result: dict[str, TrackMix] = {}
    for item in items:
        key, _, value = item.partition("=")
        volume, _, pan = value.partition(":")
        result[key] = TrackMix(volume=float(volume), pan=float(pan) if pan else 0.0)
    return result


def _add_mix_options(parser: argparse.ArgumentParser) -> None:
    """The options that shape the audio and are shared by ``render`` and ``practice``."""
    parser.add_argument("--tempo", type=float, help="tempo scale, e.g. 0.8")
    parser.add_argument("--section", help="render only this section id")
    parser.add_argument("--loops", type=int)
    parser.add_argument("--count-in", type=int, dest="count_in", help="count-in beats")
    parser.add_argument("--metronome", action="store_true")
    parser.add_argument("--bitrate", type=int, default=192, help="MP3 bitrate in kbps (default 192)")


def _apply_mix_options(settings: MixSettings, args: argparse.Namespace) -> None:
    """Apply the flags that were given on top of ``settings`` (flags win over a params file)."""
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
    tempos = [f"{m.tempo:g} from bar {m.number}" for m in piece.measures if m.tempo is not None]
    print(f"  tempo (quarter-note BPM): {', '.join(tempos)}")
    for section in piece.sections:
        bars = section.describe(piece.measures)
        print(f"  section {section.id}: {section.name} (bars {bars}) [{section.source.value}]")
    print(f"  playback order: {piece.playback_order.describe(piece.measures)}")
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
    _apply_mix_options(settings, args)
    settings.tracks.update(_parse_volume(args.volume))
    output = args.output or args.piece.with_suffix(".mp3")
    Renderer(piece, settings).render_to_file(output, bitrate_kbps=args.bitrate)
    print(f"wrote {output}")


def cmd_practice(args: argparse.Namespace) -> None:
    """Export a set of practice files (tutti, and solo/prominent/stereo per voice) into a folder."""
    piece = Piece.load(args.piece)
    settings = MixSettings()
    _apply_mix_options(settings, args)
    folder = args.output_dir or args.piece.parent / "practice"
    practice = PracticeSet(piece, settings, others_volume=args.others_volume)
    paths = practice.export(
        folder,
        fmt=args.format,
        bitrate_kbps=args.bitrate,
        on_written=lambda path: print(f"wrote {path}"),
    )
    print(f"{len(paths)} files in {folder}")


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
    _add_mix_options(p_render)
    p_render.add_argument(
        "--volume", action="append", default=[], metavar="TRACK=VOL[:PAN]",
        help="per-track mix; TRACK is a track id, label, voice letter (S/A/T/B), or * for the rest",
    )
    p_render.set_defaults(func=cmd_render)

    p_practice = sub.add_parser(
        "practice",
        help="export a practice folder: tutti, plus solo/prominent/stereo files for each voice",
    )
    p_practice.add_argument("piece", type=Path)
    p_practice.add_argument(
        "-o", "--output-dir", type=Path, help="folder to write into (default: practice/ next to the piece)"
    )
    p_practice.add_argument("--format", choices=FORMATS, default="mp3")
    p_practice.add_argument(
        "--others-volume", type=float, default=0.3,
        help="combined volume of all the other voices in the prominent files, relative to the featured voice (default 0.3)",
    )
    _add_mix_options(p_practice)
    p_practice.set_defaults(func=cmd_practice)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (KeyError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
