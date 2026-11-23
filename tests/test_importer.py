from tonetool.models import VoiceKind

from . import scorebuilder as sb
from .helpers import flat_notes


def test_tracks_and_voice_kinds(import_score):
    piece = import_score(sb.simple_score())
    assert [(t.id, t.label, t.voice) for t in piece.tracks] == [
        ("T0", "Soprano", VoiceKind.SOPRANO),
        ("T1", "Alto", VoiceKind.ALTO),
    ]
    soprano = flat_notes(piece, "T0")
    assert [n.pitch for _, n in soprano[:4]] == [72, 74, 76, 77]  # C5 D5 E5 F5
    assert [(i, n.offset, n.duration) for i, n in soprano[:3]] == [(0, 0, 1), (0, 1, 1), (0, 2, 1)]


def test_measures_tempo_and_meter(import_score):
    piece = import_score(sb.simple_score(), bpm=90, time=(3, 4))
    assert piece.measures[0].tempo == 90
    assert (piece.measures[0].beats_per_bar, piece.measures[0].beat_unit) == (3, 4)


def test_printed_numbers_come_from_xml(import_score):
    parts, bars = sb.simple_score()
    bars[3].number = "3b"
    piece = import_score((parts, bars))
    assert [m.number for m in piece.measures] == ["1", "2", "3", "3b"]


def test_pickup_measure_is_short(import_score):
    parts = ["Soprano"]
    bars = [
        sb.Bar(notes={"Soprano": "G4/q"}, number="0", implicit=True),
        sb.Bar(notes={"Soprano": "C5/h D5/h"}),
    ]
    piece = import_score((parts, bars))
    assert piece.measures[0].length == 1
    assert piece.measures[1].start == 1


def test_ties_are_kept_as_flags_not_merged(import_score):
    parts = ["Soprano"]
    bars = [sb.Bar(notes={"Soprano": "C5/h D5/h~"}), sb.Bar(notes={"Soprano": "~D5/h E5/h"})]
    piece = import_score((parts, bars))
    notes = flat_notes(piece, "T0")
    assert [(n.pitch, i, n.duration, n.tied) for i, n in notes] == [
        (72, 0, 2, False),
        (74, 0, 2, False),  # tie origin: ordinary note, notated length
        (74, 1, 2, True),  # continuation: flagged, no attack of its own
        (76, 1, 2, False),
    ]


def test_every_link_after_the_first_is_flagged_in_a_long_chain(import_score):
    parts = ["Soprano"]
    bars = [
        sb.Bar(notes={"Soprano": "E5/w~"}),
        sb.Bar(notes={"Soprano": "~E5/w~"}),  # middle link: stop and start
        sb.Bar(notes={"Soprano": "~E5/w"}),
    ]
    piece = import_score((parts, bars))
    assert [n.tied for _, n in flat_notes(piece, "T0")] == [False, True, True]


def test_ties_are_per_pitch_in_a_chord(import_score):
    parts = ["Soprano"]
    bars = [
        sb.Bar(notes={"Soprano": "E5/w~ +G5/w"}),  # only the E is tied on
        sb.Bar(notes={"Soprano": "~E5/w +G5/w"}),
    ]
    piece = import_score((parts, bars))
    flags = {(i, n.pitch): n.tied for i, n in flat_notes(piece, "T0")}
    assert flags == {(0, 76): False, (0, 79): False, (1, 76): True, (1, 79): False}


def test_chord_expands_to_simultaneous_notes(import_score):
    parts = ["Soprano"]
    bars = [sb.Bar(notes={"Soprano": "C5/w +E5/w"})]
    piece = import_score((parts, bars))
    assert sorted(n.pitch for _, n in flat_notes(piece, "T0")) == [72, 76]


def test_two_voices_on_one_staff_become_two_tracks(import_score):
    parts = ["Soprano/Alto"]
    bars = [sb.Bar(notes={"Soprano/Alto": "E5/w | C5/w"})]
    piece = import_score((parts, bars))
    assert [(t.id, t.label) for t in piece.tracks] == [
        ("T0", "Soprano/Alto (voice 1)"),
        ("T1", "Soprano/Alto (voice 2)"),
    ]
    assert [n.pitch for _, n in flat_notes(piece, "T0")] == [76]
    assert [n.pitch for _, n in flat_notes(piece, "T1")] == [72]


def test_missing_tempo_warns(import_score, tmp_path):
    parts, bars = sb.simple_score()
    text = sb.build_musicxml(parts, bars)
    import re

    text = re.sub(r"<direction placement.*?</direction>", "", text, count=1)
    path = tmp_path / "notempo.musicxml"
    path.write_text(text)
    from tonetool.importer import ScoreImporter

    piece = ScoreImporter(path).run()
    assert any("no tempo" in w for w in piece.warnings)
    assert piece.measures[0].tempo == 100


def test_json_roundtrip(import_score, tmp_path):
    from tonetool.models import Piece

    piece = import_score(sb.endings_score())
    piece.save(tmp_path / "p.json")
    assert Piece.load(tmp_path / "p.json") == piece


def test_unnamed_part_is_labelled_by_position_not_by_music21_junk_id(tmp_path):
    from tonetool.importer import ScoreImporter

    parts, bars = sb.simple_score()
    text = sb.build_musicxml(parts[:1], bars).replace("<part-name>Soprano</part-name>", "<part-name></part-name>")
    path = tmp_path / "unnamed.musicxml"
    path.write_text(text)
    track = ScoreImporter(path).run().tracks[0]
    assert (track.id, track.label) == ("T0", "part 0")


def test_parts_with_different_measure_counts_are_rejected(tmp_path):
    import re

    import pytest

    from tonetool.importer import ScoreImporter

    parts, bars = sb.simple_score()
    text = sb.build_musicxml(parts, bars)
    head, _, alto = text.partition('<part id="P2">')
    alto = re.sub(r'<measure number="4">.*?</measure>', "", alto, flags=re.S)  # alto loses bar 4
    path = tmp_path / "ragged.musicxml"
    path.write_text(head + '<part id="P2">' + alto)
    with pytest.raises(ValueError, match=r"Soprano=4, Alto=3"):
        ScoreImporter(path).run()


def test_track_ids_run_across_parts_in_score_order(import_score):
    # a staff with two voices, followed by a staff with one: T0, T1 from the first, T2 from the second
    parts = ["Soprano/Alto", "Tenor"]
    bars = [sb.Bar(notes={"Soprano/Alto": "E5/w | C5/w", "Tenor": "G4/w"})]
    piece = import_score((parts, bars))
    assert [(t.id, t.label) for t in piece.tracks] == [
        ("T0", "Soprano/Alto (voice 1)"),
        ("T1", "Soprano/Alto (voice 2)"),
        ("T2", "Tenor"),
    ]


def test_notes_live_in_measures_keyed_by_track(import_score):
    piece = import_score(sb.simple_score())
    first = piece.measures[0].voices
    assert set(first) == {"T0", "T1"}
    assert [n.pitch for n in first["T0"].notes] == [72, 74, 76, 77]  # soprano, bar 1
    assert [n.pitch for n in first["T1"].notes] == [64, 65, 67, 69]  # alto, bar 1


def test_voice_measures_is_the_horizontal_view(import_score):
    import pytest

    piece = import_score(sb.simple_score())
    soprano = piece.voice_measures("T0")
    assert [[n.pitch for n in vm.notes] for vm in soprano] == [
        [72, 74, 76, 77],
        [79, 76],
        [77, 76, 74, 72],
        [72],
    ]
    with pytest.raises(KeyError, match="T9"):
        piece.voice_measures("T9")


def test_a_resting_voice_has_an_empty_voice_measure(import_score):
    parts = ["Soprano", "Alto"]
    bars = [
        sb.Bar(notes={"Soprano": "C5/w", "Alto": "E4/w"}),
        sb.Bar(notes={"Soprano": "D5/w", "Alto": "R/w"}),  # alto rests
    ]
    piece = import_score((parts, bars))
    assert set(piece.measures[1].voices) == {"T0", "T1"}  # every track has an entry in every bar
    assert piece.measures[1].voices["T1"].notes == []
    assert len(piece.voice_measures("T1")) == len(piece.measures)


def test_single_voiced_measure_in_a_two_voice_part_is_given_to_both_voices(import_score):
    parts = ["Soprano/Alto"]
    bars = [
        sb.Bar(notes={"Soprano/Alto": "E5/w | C5/w"}),  # divisi
        sb.Bar(notes={"Soprano/Alto": "G5/w"}),  # unison, written once
    ]
    piece = import_score((parts, bars))
    in_bar_2 = piece.measures[1].voices
    assert [n.pitch for n in in_bar_2["T0"].notes] == [79]
    assert [n.pitch for n in in_bar_2["T1"].notes] == [79]
    assert in_bar_2["T0"].notes[0] is not in_bar_2["T1"].notes[0]  # copies, not shared objects


def test_a_resting_second_voice_is_not_mistaken_for_a_unison(import_score):
    parts = ["Soprano/Alto"]
    bars = [
        sb.Bar(notes={"Soprano/Alto": "E5/w | C5/w"}),
        sb.Bar(notes={"Soprano/Alto": "G5/w | R/w"}),  # alto explicitly rests
    ]
    piece = import_score((parts, bars))
    assert [n.pitch for n in piece.measures[1].voices["T0"].notes] == [79]
    assert piece.measures[1].voices["T1"].notes == []


def test_piece_rejects_a_measure_with_an_unknown_or_missing_track(import_score):
    import pytest

    from tonetool.models import Piece

    piece = import_score(sb.simple_score())
    extra = piece.model_dump()
    extra["measures"][0]["voices"]["T9"] = {"notes": []}
    with pytest.raises(ValueError, match="one VoiceMeasure per track"):
        Piece.model_validate(extra)

    missing = piece.model_dump()
    del missing["measures"][1]["voices"]["T1"]
    with pytest.raises(ValueError, match="one VoiceMeasure per track"):
        Piece.model_validate(missing)


def test_non_musicxml_extension_gets_a_clear_error_not_a_music21_crash(tmp_path):
    import pytest

    from tonetool.importer import ScoreImporter

    zipped = tmp_path / "score.zip"
    zipped.write_bytes(b"PK\x03\x04")  # music21 would route .zip to its MuseData parser
    with pytest.raises(ValueError, match=r"expected a MusicXML file .*got '\.zip'.*extract"):
        ScoreImporter(zipped).run()
    bare = tmp_path / "score"
    bare.write_bytes(b"")
    with pytest.raises(ValueError, match="no extension"):
        ScoreImporter(bare).run()


def test_a_directory_or_missing_path_gets_a_clear_error(tmp_path):
    import pytest

    from tonetool.importer import ScoreImporter

    with pytest.raises(ValueError, match="is a directory, not a file"):
        ScoreImporter(tmp_path).run()
    with pytest.raises(FileNotFoundError, match="no such file"):
        ScoreImporter(tmp_path / "missing.musicxml").run()


def test_cli_reports_file_problems_without_a_traceback(tmp_path, capsys):
    import pytest

    from tonetool.cli import main

    for command in (["import", str(tmp_path)], ["show", str(tmp_path)]):
        with pytest.raises(SystemExit) as exit_info:
            main(command)
        assert exit_info.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_a_tempo_mark_sits_on_its_measure_and_later_measures_inherit_it(import_score):
    parts, bars = sb.simple_score()
    bars[2].tempo = 90
    piece = import_score((parts, bars), bpm=120)
    assert [m.tempo for m in piece.measures] == [120, None, 90, None]
    assert piece.measure_bpms() == [120, 120, 90, 90]


def test_a_first_tempo_that_comes_late_warns_and_defaults_the_start(import_score):
    import re

    from tonetool.importer import ScoreImporter

    parts, bars = sb.simple_score()
    bars[2].tempo = 90
    text = sb.build_musicxml(parts, bars)
    text = re.sub(r"<direction placement.*?</direction>", "", text, count=1)  # drop the bar-1 mark
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "late.musicxml"
    path.write_text(text)
    piece = ScoreImporter(path).run()
    assert piece.measure_bpms() == [100, 100, 90, 90]
    assert any("no tempo marking at the start" in w for w in piece.warnings)


def test_the_first_measure_must_carry_a_tempo(import_score):
    import pytest

    from tonetool.models import Piece

    data = import_score(sb.simple_score()).model_dump()
    data["measures"][0]["tempo"] = None
    with pytest.raises(ValueError, match="first measure needs a tempo"):
        Piece.model_validate(data)


def test_editing_only_the_first_measures_tempo_changes_the_whole_piece(import_score):
    from tonetool.models import Piece

    data = import_score(sb.simple_score(), bpm=120).model_dump()
    data["measures"][0]["tempo"] = 80
    assert Piece.model_validate(data).measure_bpms() == [80, 80, 80, 80]


def test_schema_2_files_are_upgraded_on_load(import_score, tmp_path):
    import json

    from tonetool.models import Piece

    parts, bars = sb.simple_score()
    bars[2].tempo = 90
    data = import_score((parts, bars), bpm=120).model_dump()
    data["schema_version"] = 2
    for measure, bpm in zip(data["measures"], [120, 120, 90, 90]):  # schema 2: a bpm on every bar
        del measure["tempo"]
        measure["bpm"] = bpm
    path = tmp_path / "v2.piece.json"
    path.write_text(json.dumps(data))
    piece = Piece.load(path)
    assert [m.tempo for m in piece.measures] == [120, None, 90, None]
    assert piece.measure_bpms() == [120, 120, 90, 90]
