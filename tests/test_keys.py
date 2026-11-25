import pytest
from pydantic import ValidationError

from tonetool.models import Key, Mode

from . import scorebuilder as sb


def song(last_bass: str, key: tuple[int, str | None] | None):
    """Two bars; the last one ends with ``last_bass`` as the lowest note. -> (score, kwargs)."""
    bars = [
        sb.Bar(notes={"Soprano": "G5/w", "Bass": "C3/w"}),
        sb.Bar(notes={"Soprano": "E5/w", "Bass": f"{last_bass}/w"}),
    ]
    return (["Soprano", "Bass"], bars), {"key": key}


@pytest.mark.parametrize(
    "fifths, mode, bass, expected",
    [
        (0, None, "C3", "C major"),
        (0, None, "A2", "A minor"),  # the signature fits both; the piece ends on A
        (0, None, "E3", "C major"),  # ends on neither tonic: major
        (2, None, "D3", "D major"),
        (2, None, "B2", "B minor"),
        (-2, None, "Bb2", "Bb major"),  # flats are spelled with b
        (-2, None, "G2", "G minor"),
        (3, None, "F#2", "F# minor"),  # sharps with #
        (-3, "minor", "G2", "C minor"),  # an explicit mode is taken as written, whatever the bass does
        (1, "major", "E3", "G major"),
    ],
)
def test_the_key_is_suggested_from_the_signature_and_the_final_bass_note(
    import_score, fifths, mode, bass, expected
):
    score, kwargs = song(bass, (fifths, mode))
    piece = import_score(score, **kwargs)
    assert piece.key is not None and piece.key.name == expected


def test_a_score_without_a_key_signature_has_no_key(import_score):
    score, kwargs = song("C3", None)
    assert import_score(score, **kwargs).key is None


def test_key_pitch_classes():
    assert [Key(tonic=t, mode=Mode.MAJOR).pitch_class for t in ["C", "C#", "Db", "D", "Eb", "F#", "Gb", "A", "Bb", "B"]] == [
        0, 1, 1, 2, 3, 6, 6, 9, 10, 11,
    ]
    assert Key(tonic="Cb", mode=Mode.MAJOR).pitch_class == 11
    assert Key(tonic="E", mode=Mode.MINOR).name == "E minor"


@pytest.mark.parametrize("tonic", ["H", "c", "C##", "Bbb", "", "C ", "Cb2"])
def test_a_tonic_must_be_a_note_name(tonic):
    with pytest.raises(ValidationError):
        Key(tonic=tonic, mode=Mode.MAJOR)


def test_pieces_from_schema_4_still_load(import_score, tmp_path):
    import json

    from tonetool.models import SCHEMA_VERSION, Piece

    score, kwargs = song("C3", (0, None))
    data = json.loads(import_score(score, **kwargs).model_dump_json())
    data["schema_version"] = 4
    del data["key"]
    path = tmp_path / "old.piece.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = Piece.load(path)
    assert loaded.schema_version == SCHEMA_VERSION and loaded.key is None
