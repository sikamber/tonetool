from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tonetool.api.app import create_app
from tonetool.api.config import PieceEntry, ServerConfig
from tonetool.models import Piece

from . import scorebuilder as sb


def score(bars=None, title="Test", parts=None) -> bytes:
    """MusicXML bytes for a small score (the endings score by default)."""
    default_parts, default_bars = sb.endings_score()
    return sb.build_musicxml(parts or default_parts, bars or default_bars, title=title).encode("utf-8")


def upload(client: TestClient, data: bytes, name: str = "song.musicxml", **form):
    return client.post("/api/pieces", files={"file": (name, data, "application/xml")}, data=form)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    return tmp_path / "library"


@pytest.fixture
def client(library: Path) -> TestClient:
    return TestClient(create_app(ServerConfig(library=library)))


def edits_of(piece: dict) -> dict:
    """The PUT body that changes nothing."""
    return {
        "title": piece["title"],
        "key": piece["key"],
        "tracks": [{"id": t["id"], "label": t["label"], "voice": t["voice"]} for t in piece["tracks"]],
        "sections": piece["sections"],
    }


def folders(library: Path) -> list[str]:
    return sorted(p.name for p in library.iterdir()) if library.exists() else []


# -- import -------------------------------------------------------------------------------------


def test_import_creates_a_library_piece_from_the_title(client: TestClient, library: Path):
    response = upload(client, score(title="Julesang"))
    assert response.status_code == 201
    summary = response.json()
    assert (summary["id"], summary["title"], summary["origin"]) == ("Julesang", "Julesang", "library")
    assert sorted(p.name for p in (library / "Julesang").iterdir()) == ["piece.json", "song.musicxml"]
    assert client.get("/api/pieces/Julesang").json()["source_file"] == "song.musicxml"


def test_importing_the_same_title_again_gets_a_new_id(client: TestClient):
    assert upload(client, score()).json()["id"] == "Test"
    assert upload(client, score()).json()["id"] == "Test-2"
    assert [p["id"] for p in client.get("/api/pieces").json()] == ["Test", "Test-2"]


def test_danish_titles_and_file_names_survive(client: TestClient, library: Path):
    response = upload(client, score(title="Blåbærrene på Ærø"), name="Blåbær på Ærø.musicxml")
    assert response.json()["id"] == "Blåbærrene-på-Ærø"
    assert (library / "Blåbærrene-på-Ærø" / "Blåbær på Ærø.musicxml").is_file()


def test_an_id_can_be_chosen(client: TestClient):
    assert upload(client, score(), id="mitid").json()["id"] == "mitid"
    assert upload(client, score(), id="mitid").status_code == 422  # taken
    assert upload(client, score(), id="a b").status_code == 422  # not a valid id


def test_file_names_cannot_escape_the_folder(client: TestClient, library: Path):
    upload(client, score(), name="../../evil.musicxml")
    assert (library / "Test" / "evil.musicxml").is_file()


def test_a_wrong_extension_is_refused(client: TestClient, library: Path):
    response = upload(client, b"hello", name="notes.txt")
    assert response.status_code == 422 and "MusicXML" in response.json()["detail"]
    assert folders(library) == []


def test_an_unreadable_score_is_refused_and_leaves_nothing_behind(client: TestClient, library: Path):
    response = upload(client, b"<this is not xml", name="broken.musicxml")
    assert response.status_code == 422 and "could not read" in response.json()["detail"]
    assert folders(library) == []


def test_oversized_uploads_are_refused(library: Path):
    client = TestClient(create_app(ServerConfig(library=library, max_upload_mb=1)))
    assert upload(client, b"x" * (1024 * 1024 + 1)).status_code == 413
    assert folders(library) == []


def test_importing_needs_a_library(tmp_path: Path):
    client = TestClient(create_app(ServerConfig()))
    assert upload(client, score()).status_code == 409


# -- editing ------------------------------------------------------------------------------------


@pytest.fixture
def imported(client: TestClient) -> dict:
    upload(client, score(title="Song"))
    return client.get("/api/pieces/Song").json()


def test_edits_are_saved_and_only_changed_sections_become_the_users(
    client: TestClient, library: Path, imported: dict
):
    assert {s["source"] for s in imported["sections"]} == {"auto"}
    edits = edits_of(imported)
    edits["title"] = "  Min sang  "
    edits["tracks"][1].update(label="Alt 1", voice="T")
    edits["sections"][1]["name"] = "Vers 2"
    response = client.put("/api/pieces/Song", json=edits)
    assert response.status_code == 200
    saved = Piece.model_validate(response.json())
    assert saved.title == "Min sang"
    assert [(t.label, t.voice.value) for t in saved.tracks] == [("Soprano", "S"), ("Alt 1", "T")]
    assert [(s.name, s.source.value) for s in saved.sections] == [
        ("A", "auto"), ("Vers 2", "user"), ("B", "auto"),
    ]
    assert Piece.load(library / "Song" / "piece.json") == saved
    assert client.get("/api/pieces/Song").json()["title"] == "Min sang"
    assert (library / "Song" / "piece.json.bak").is_file()


def test_sections_can_be_added_removed_and_reordered(client: TestClient, imported: dict):
    edits = edits_of(imported)
    new = {"id": "s9", "name": "Coda", "segments": [{"start": 4, "end": 5}], "lyric_number": None}
    edits["sections"] = [new, *edits["sections"][:2]]
    saved = client.put("/api/pieces/Song", json=edits).json()
    assert [s["id"] for s in saved["sections"]] == ["s9", "s1", "s2"]
    assert saved["sections"][0]["source"] == "user"


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda e: e["sections"][0]["segments"].__setitem__(0, {"start": 0, "end": 99}), "outside"),
        (lambda e: e["sections"][1].__setitem__("id", "s1"), "duplicate section ids"),
        (lambda e: e["sections"].clear(), "at least one section"),
        (lambda e: e["tracks"].pop(), "exactly the piece's tracks"),
        (lambda e: e["tracks"][0].__setitem__("id", "T9"), "exactly the piece's tracks"),
        (lambda e: e["sections"][0]["segments"].__setitem__(0, {"start": 3, "end": 1}), "start 3 > end 1"),
    ],
)
def test_invalid_edits_are_refused_and_change_nothing(
    client: TestClient, library: Path, imported: dict, change, message: str
):
    before = (library / "Song" / "piece.json").read_bytes()
    edits = edits_of(imported)
    change(edits)
    response = client.put("/api/pieces/Song", json=edits)
    assert response.status_code == 422
    assert message in str(response.json()["detail"])
    assert (library / "Song" / "piece.json").read_bytes() == before


def test_empty_titles_and_labels_are_refused(client: TestClient, imported: dict):
    for field in ("title", "label"):
        edits = edits_of(imported)
        if field == "title":
            edits["title"] = "   "
        else:
            edits["tracks"][0]["label"] = ""
        assert client.put("/api/pieces/Song", json=edits).status_code == 422


def test_editing_an_unknown_piece_is_404(client: TestClient, imported: dict):
    assert client.put("/api/pieces/nope", json=edits_of(imported)).status_code == 404


def test_linked_pieces_are_edited_in_place(tmp_path: Path, import_score):
    path = tmp_path / "linked.piece.json"
    import_score(sb.endings_score()).save(path)
    client = TestClient(create_app(ServerConfig(pieces=[PieceEntry(id="linked", path=path)])))
    edits = edits_of(client.get("/api/pieces/linked").json())
    edits["title"] = "Changed"
    assert client.put("/api/pieces/linked", json=edits).status_code == 200
    assert Piece.load(path).title == "Changed"
    assert path.with_name("linked.piece.json.bak").is_file()


# -- delete -------------------------------------------------------------------------------------


def test_delete_moves_the_piece_to_the_trash(client: TestClient, library: Path, imported: dict):
    assert client.delete("/api/pieces/Song").status_code == 204
    assert client.get("/api/pieces/Song").status_code == 404
    assert not (library / "Song").exists()
    trashed = list((library / ".trash").iterdir())
    assert len(trashed) == 1 and (trashed[0] / "piece.json").is_file()
    assert client.delete("/api/pieces/Song").status_code == 404


def test_linked_pieces_cannot_be_deleted(tmp_path: Path, import_score):
    path = tmp_path / "linked.piece.json"
    import_score(sb.endings_score()).save(path)
    client = TestClient(create_app(ServerConfig(library=tmp_path / "lib", pieces=[PieceEntry(id="linked", path=path)])))
    assert client.delete("/api/pieces/linked").status_code == 409
    assert path.exists()


# -- replace score ------------------------------------------------------------------------------


def replace(client: TestClient, data: bytes, name: str = "song.musicxml"):
    return client.post("/api/pieces/Song/score", files={"file": (name, data, "application/xml")})


def test_replacing_the_score_keeps_sections_title_and_labels(client: TestClient, library: Path, imported: dict):
    edits = edits_of(imported)
    edits["title"] = "Min sang"
    edits["tracks"][0]["label"] = "Sopran 1"
    edits["sections"][0]["name"] = "Vers 1"
    client.put("/api/pieces/Song", json=edits)

    parts, bars = sb.endings_score()
    bars[0] = sb.Bar(notes={"Soprano": "G5/w", "Alto": "E4/w"}, rehearsal="A", forward_repeat=True)  # new note
    response = replace(client, score(bars, title="A different title in the file"))
    assert response.status_code == 200
    new = Piece.model_validate(response.json())
    assert new.title == "Min sang"
    assert new.tracks[0].label == "Sopran 1"
    assert [(s.name, s.source.value) for s in new.sections][0] == ("Vers 1", "user")
    assert new.measures[0].voices["T0"].notes[0].pitch == 79  # the new score's note
    assert Piece.load(library / "Song" / "piece.json") == new


def test_a_score_with_another_file_name_replaces_the_old_file(client: TestClient, library: Path, imported: dict):
    assert replace(client, score(), name="new name.musicxml").status_code == 200
    assert sorted(p.name for p in (library / "Song").iterdir()) == ["new name.musicxml", "piece.json", "piece.json.bak"]
    assert client.get("/api/pieces/Song").json()["source_file"] == "new name.musicxml"
    assert any("song.musicxml" in p.name for p in (library / ".trash").iterdir())


def test_a_score_with_a_different_number_of_bars_is_refused(client: TestClient, library: Path, imported: dict):
    before = (library / "Song" / "piece.json").read_bytes()
    parts, bars = sb.simple_score()  # 4 bars; the piece has 6
    response = replace(client, score(bars, parts=parts))
    assert response.status_code == 422
    assert "import it as a new piece" in response.json()["detail"] or "reach past" in response.json()["detail"]
    assert (library / "Song" / "piece.json").read_bytes() == before


def test_a_score_with_another_number_of_parts_is_refused(client: TestClient, library: Path, imported: dict):
    before = (library / "Song" / "piece.json").read_bytes()
    parts, bars = sb.endings_score()
    one_part = [sb.Bar(notes={"Soprano": b.notes["Soprano"]}, **{k: v for k, v in vars(b).items() if k != "notes"}) for b in bars]
    response = replace(client, score(one_part, parts=["Soprano"]))
    assert response.status_code == 422 and "parts" in response.json()["detail"]
    assert (library / "Song" / "piece.json").read_bytes() == before


def test_replacing_with_a_broken_file_changes_nothing(client: TestClient, library: Path, imported: dict):
    before = (library / "Song" / "piece.json").read_bytes()
    assert replace(client, b"<nope").status_code == 422
    assert (library / "Song" / "piece.json").read_bytes() == before


# -- key ----------------------------------------------------------------------------------------


def test_the_suggested_key_is_stored_and_can_be_changed_and_cleared(client: TestClient, imported: dict):
    assert imported["key"] == {"tonic": "C", "mode": "major"}  # the endings score has no signature: fifths 0
    edits = edits_of(imported)
    edits["key"] = {"tonic": "Bb", "mode": "minor"}
    saved = client.put("/api/pieces/Song", json=edits).json()
    assert saved["key"] == {"tonic": "Bb", "mode": "minor"}
    assert client.get("/api/pieces/Song").json()["key"] == {"tonic": "Bb", "mode": "minor"}
    edits["key"] = None
    assert client.put("/api/pieces/Song", json=edits).json()["key"] is None


@pytest.mark.parametrize("key", [{"tonic": "H", "mode": "major"}, {"tonic": "C", "mode": "dorian"}, {"tonic": "C"}])
def test_an_invalid_key_is_refused(client: TestClient, imported: dict, key):
    edits = edits_of(imported)
    edits["key"] = key
    assert client.put("/api/pieces/Song", json=edits).status_code == 422


def test_leaving_the_key_out_of_an_edit_is_an_error_not_a_clear(client: TestClient, imported: dict):
    edits = edits_of(imported)
    del edits["key"]
    assert client.put("/api/pieces/Song", json=edits).status_code == 422
    assert client.get("/api/pieces/Song").json()["key"] == imported["key"]


def test_replacing_the_score_keeps_a_key_that_was_set(client: TestClient, imported: dict):
    edits = edits_of(imported)
    edits["key"] = {"tonic": "F", "mode": "minor"}
    client.put("/api/pieces/Song", json=edits)
    assert replace(client, score()).json()["key"] == {"tonic": "F", "mode": "minor"}


def test_replacing_the_score_fills_in_a_missing_key(client: TestClient, imported: dict):
    edits = edits_of(imported)
    edits["key"] = None
    client.put("/api/pieces/Song", json=edits)
    assert replace(client, score()).json()["key"] == {"tonic": "C", "mode": "major"}
