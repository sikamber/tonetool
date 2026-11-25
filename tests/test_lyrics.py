import json
from pathlib import Path

from tonetool.lyrics import LyricVerses
from tonetool.models import Piece, Provenance, Syllabic

from . import scorebuilder as sb


def lyrics_of(piece: Piece, track_id: str = "T0"):
    """[(measure, number, text, syllabic)] for one voice, in score order."""
    return [
        (index, lyric.number, lyric.text, lyric.syllabic)
        for index, voice in enumerate(piece.voice_measures(track_id))
        for note in voice.notes
        for lyric in note.lyrics
    ]


def test_syllables_are_imported_per_lyric_line(import_score):
    bars = [sb.Bar(notes={"Soprano": "C5/q{Ju-;Hjer-} D5/q{-le-;-ter} E5/h{-træ;-klip}"})]
    piece = import_score((["Soprano"], bars))
    assert lyrics_of(piece) == [
        (0, "1", "Ju", Syllabic.BEGIN),
        (0, "2", "Hjer", Syllabic.BEGIN),
        (0, "1", "le", Syllabic.MIDDLE),
        (0, "2", "ter", Syllabic.END),
        (0, "1", "træ", Syllabic.END),
        (0, "2", "klip", Syllabic.END),
    ]


def test_verse_labels_are_not_part_of_the_text(import_score):
    bars = [sb.Bar(notes={"Soprano": "C5/h{1.Ju-;2)Hjer} D5/h{-le}"})]
    assert [text for _, _, text, _ in lyrics_of(import_score((["Soprano"], bars)))] == ["Ju", "Hjer", "le"]


def test_a_chord_is_sung_once_on_its_first_note(import_score):
    bars = [sb.Bar(notes={"Soprano": "C5/h{la} +E5/h D5/h"})]
    notes = import_score((["Soprano"], bars)).measures[0].voices["T0"].notes
    assert [len(n.lyrics) for n in notes] == [1, 0, 0]


def test_notes_without_lyrics_have_none(import_score):
    piece = import_score(sb.simple_score())
    assert lyrics_of(piece) == []
    assert all(s.lyric_number is None for s in piece.sections)


# bars 1-2 are repeated; line 1 is verse 1, line 2 verse 2. Bars 3-4 (verse 3, once) use line 1.
THREE_VERSES = [
    sb.Bar(notes={"Soprano": "C5/w{1.a;2.x}"}, forward_repeat=True),
    sb.Bar(notes={"Soprano": "D5/w{b;y}"}, backward_repeat=True),
    sb.Bar(notes={"Soprano": "E5/w{3.c}"}, rehearsal="B"),
    sb.Bar(notes={"Soprano": "F5/w{d}"}),
]


def test_each_pass_over_the_same_bars_sings_the_next_line(import_score):
    piece = import_score((["Soprano"], THREE_VERSES))
    assert [(s.segments[0].start, s.segments[-1].end, s.lyric_number) for s in piece.sections] == [
        (0, 1, "1"),  # first pass over bars 1-2
        (0, 1, "2"),  # second pass
        (2, 3, "1"),  # bars 3-4 were never sung: line 1, even though it is the third verse
    ]


def test_a_repeat_without_a_new_line_reuses_the_last_one(import_score):
    bars = [
        sb.Bar(notes={"Soprano": "C5/w{a}"}, forward_repeat=True),
        sb.Bar(notes={"Soprano": "D5/w{b}"}, backward_repeat=True),
    ]
    piece = import_score((["Soprano"], bars))
    assert [s.lyric_number for s in piece.sections] == ["1", "1"]


def test_sections_edited_by_a_person_keep_their_lyric_number(import_score):
    piece = import_score((["Soprano"], THREE_VERSES))
    piece.sections[1].source = Provenance.USER
    piece.sections[1].lyric_number = "1"
    LyricVerses(piece).assign()
    assert [s.lyric_number for s in piece.sections] == ["1", "1", "1"]


def test_pieces_from_schema_3_still_load(import_score, tmp_path: Path):
    piece = import_score((["Soprano"], THREE_VERSES))
    data = json.loads(piece.model_dump_json())
    data["schema_version"] = 3
    for section in data["sections"]:
        del section["lyric_number"]
    for measure in data["measures"]:
        for voice in measure["voices"].values():
            for note in voice["notes"]:
                del note["lyrics"]
    path = tmp_path / "old.piece.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = Piece.load(path)
    assert loaded.schema_version == 4
    assert all(s.lyric_number is None for s in loaded.sections)


def test_reimport_can_keep_the_sections_of_an_earlier_import(tmp_path: Path):
    from tonetool.importer import ScoreImporter
    from tonetool.models import PlaybackSegment, Section

    path = sb.write_score(tmp_path / "s.musicxml", ["Soprano"], THREE_VERSES)
    mine = [
        Section(id="v1", name="Vers 1", segments=[PlaybackSegment(start=0, end=1)]),
        Section(id="v2", name="Vers 2", segments=[PlaybackSegment(start=0, end=1)]),
        Section(id="v3", name="Vers 3", segments=[PlaybackSegment(start=2, end=3)]),
    ]
    piece = ScoreImporter(path).run(keep_sections=mine)
    assert [(s.name, s.lyric_number) for s in piece.sections] == [
        ("Vers 1", "1"),
        ("Vers 2", "2"),
        ("Vers 3", "1"),
    ]
