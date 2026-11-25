import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tonetool.api.app import create_app
from tonetool.api.config import PieceEntry, ServerConfig
from tonetool.models import Piece

from . import scorebuilder as sb


@pytest.fixture
def piece(import_score) -> Piece:
    return import_score(sb.endings_score())


@pytest.fixture
def client(piece: Piece, tmp_path: Path) -> TestClient:
    piece.save(tmp_path / "good.piece.json")
    (tmp_path / "bad.piece.json").write_text("{not json")
    (tmp_path / "tonetool.toml").write_text(
        '[[pieces]]\nid = "good"\npath = "good.piece.json"\n'
        '[[pieces]]\nid = "bad"\npath = "bad.piece.json"\n'
        '[[pieces]]\nid = "missing"\npath = "nope.piece.json"\n'
    )
    return TestClient(create_app(tmp_path / "tonetool.toml"))


def test_relative_paths_resolve_against_config_file(tmp_path: Path):
    (tmp_path / "c.toml").write_text('[[pieces]]\nid = "a"\npath = "sub/a.json"\n')
    config = ServerConfig.load(tmp_path / "c.toml")
    assert config.pieces[0].path == tmp_path / "sub" / "a.json"


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ServerConfig(pieces=[PieceEntry(id="a", path=Path("x")), PieceEntry(id="a", path=Path("y"))])


def test_list_pieces_summarises_and_reports_broken_files(client: TestClient, piece: Piece):
    by_id = {s["id"]: s for s in client.get("/api/pieces").json()}
    assert by_id["good"]["title"] == piece.title
    assert by_id["good"]["measure_count"] == len(piece.measures)
    assert [t["id"] for t in by_id["good"]["tracks"]] == [t.id for t in piece.tracks]
    assert by_id["good"]["error"] is None
    assert by_id["bad"]["error"] and by_id["missing"]["error"]


def test_get_piece_round_trips(client: TestClient, piece: Piece):
    response = client.get("/api/pieces/good")
    assert response.status_code == 200
    assert Piece.model_validate(response.json()) == piece


def test_get_unknown_piece_is_404(client: TestClient):
    assert client.get("/api/pieces/nope").status_code == 404


def test_get_broken_piece_is_500_with_message(client: TestClient):
    response = client.get("/api/pieces/bad")
    assert response.status_code == 500
    assert "bad" in response.json()["detail"]


def test_edited_file_is_reloaded(client: TestClient, piece: Piece, tmp_path: Path):
    client.get("/api/pieces/good")
    piece.title = "Renamed"
    piece.save(tmp_path / "good.piece.json")
    os.utime(tmp_path / "good.piece.json", (1, 2_000_000_000))
    assert client.get("/api/pieces/good").json()["title"] == "Renamed"


def test_danish_characters_in_ids_and_paths(piece: Piece, tmp_path: Path):
    folder = tmp_path / "Sange fra Sønderjylland"
    folder.mkdir()
    piece.save(folder / "Blåbærrene på Ærø.piece.json")
    (tmp_path / "tonetool.toml").write_text(
        '[[pieces]]\nid = "blåbær-på-ærø"\npath = "Sange fra Sønderjylland/Blåbærrene på Ærø.piece.json"\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path / "tonetool.toml"))
    assert [s["id"] for s in client.get("/api/pieces").json()] == ["blåbær-på-ærø"]
    assert client.get("/api/pieces/bl%C3%A5b%C3%A6r-p%C3%A5-%C3%A6r%C3%B8").status_code == 200


def test_ids_still_reject_url_unsafe_characters():
    for bad in ["a b", "a/b", "a?b", ""]:
        with pytest.raises(ValueError):
            PieceEntry(id=bad, path=Path("x"))


def test_piece_json_is_utf8_on_disk(piece: Piece, tmp_path: Path):
    piece.title = "Blåbærrene på Ærø"
    path = tmp_path / "p.piece.json"
    piece.save(path)
    assert "Blåbærrene på Ærø" in path.read_bytes().decode("utf-8")
    assert Piece.load(path).title == piece.title
