import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tonetool.api.app import create_app
from tonetool.api.config import ServerConfig
from tonetool.api.errors import ClientError
from tonetool.api.uploads import MAX_ARCHIVE_ENTRIES, MAX_MEASURES, MAX_PARTS, ScoreValidator

from . import scorebuilder as sb

PARTS, BARS = sb.endings_score()
SCORE = sb.build_musicxml(PARTS, BARS, title="Test").encode("utf-8")


def mxl(score: bytes = SCORE, extra: dict[str, bytes] | None = None, name: str = "score.xml") -> bytes:
    """A compressed MusicXML archive: container.xml pointing at the score, plus any extra files."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "META-INF/container.xml",
            f'<container><rootfiles><rootfile full-path="{name}"/></rootfiles></container>',
        )
        archive.writestr(name, score)
        for member, content in (extra or {}).items():
            archive.writestr(member, content)
    return out.getvalue()


@pytest.fixture
def library(tmp_path: Path) -> Path:
    return tmp_path / "library"


@pytest.fixture
def client(library: Path) -> TestClient:
    return TestClient(create_app(ServerConfig(library=library, max_unpacked_mb=1)))


def upload(client: TestClient, data: bytes, name: str = "song.musicxml"):
    return client.post("/api/pieces", files={"file": (name, data, "application/octet-stream")})


def refused(client: TestClient, library: Path, data: bytes, name: str, fragment: str) -> None:
    response = upload(client, data, name)
    assert response.status_code == 422, response.text
    assert fragment in response.json()["detail"]
    assert not library.exists() or list(library.iterdir()) == []  # nothing was stored


# -- what is accepted ---------------------------------------------------------------------------


def test_plain_xml_and_compressed_scores_import(client: TestClient):
    assert upload(client, SCORE, "a.musicxml").status_code == 201
    assert upload(client, mxl(), "b.mxl").status_code == 201
    assert upload(client, b"\xef\xbb\xbf" + SCORE, "c.xml").status_code == 201  # with a byte-order mark


# -- content must match the name ----------------------------------------------------------------


def test_a_zip_named_xml_is_refused(client: TestClient, library: Path):
    refused(client, library, mxl(), "sneaky.xml", "ZIP archive")


@pytest.mark.parametrize("data", [SCORE, b"", b"PK\x03\x04 not really a zip", b"hello"])
def test_something_that_is_not_a_zip_named_mxl_is_refused(client: TestClient, library: Path, data: bytes):
    refused(client, library, data, "score.mxl", "not a valid .mxl")


@pytest.mark.parametrize("data", [b"\x00\x01\x02 binary", b"hello", b"", b"\x89PNG\r\n\x1a\n"])
def test_binary_or_text_named_xml_is_refused(client: TestClient, library: Path, data: bytes):
    refused(client, library, data, "score.xml", "not an XML document")


# -- archives -----------------------------------------------------------------------------------


def test_an_archive_that_unpacks_to_too_much_is_refused(client: TestClient, library: Path):
    bomb = mxl(extra={"padding.bin": b"\0" * (3 * 1024 * 1024)})  # a few KB zipped, 3 MB unpacked, limit is 1
    assert len(bomb) < 100_000
    refused(client, library, bomb, "bomb.mxl", "unpacks to more than 1 MB")


def test_a_score_larger_than_the_limit_inside_an_archive_is_refused(client: TestClient, library: Path):
    huge = SCORE + b"<!-- " + b"x" * (2 * 1024 * 1024) + b" -->"
    refused(client, library, mxl(huge), "big.mxl", "unpacks to more than")


@pytest.mark.parametrize("member", ["../evil.xml", "/etc/evil.xml", "a/../../evil.xml", "C:/evil.xml", "..\\evil.xml"])
def test_an_archive_with_names_that_climb_out_is_refused(client: TestClient, library: Path, member: str):
    refused(client, library, mxl(extra={member: b"x"}), "slip.mxl", "unsafe file name")


def test_an_archive_with_too_many_files_is_refused(client: TestClient, library: Path):
    many = mxl(extra={f"f{i}.txt": b"x" for i in range(MAX_ARCHIVE_ENTRIES)})
    refused(client, library, many, "many.mxl", "files")


def test_an_archive_without_a_container_or_score_is_refused(client: TestClient, library: Path):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("score.xml", SCORE)
    refused(client, library, out.getvalue(), "nocontainer.mxl", "no META-INF/container.xml")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="gone.xml"/></rootfiles></container>')
    refused(client, library, out.getvalue(), "noscore.mxl", "no gone.xml")


def test_an_encrypted_archive_is_refused():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("META-INF/container.xml", "<container/>")
    data = bytearray(out.getvalue())
    # set the "encrypted" bit (bit 0 of the general purpose flags) in the central directory entry
    central = data.index(b"PK\x01\x02")
    data[central + 8] |= 1
    with pytest.raises(ClientError, match="encrypted"):
        ScoreValidator().check("x.mxl", bytes(data))


# -- XML ----------------------------------------------------------------------------------------

BILLION_LAUGHS = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>'
    b"<score-partwise><part id='P1'><measure>&lol2;</measure></part></score-partwise>"
)
EXTERNAL_ENTITY = (
    b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    b"<score-partwise><part id='P1'><measure>&xxe;</measure></part></score-partwise>"
)


@pytest.mark.parametrize("document", [BILLION_LAUGHS, EXTERNAL_ENTITY])
@pytest.mark.parametrize("name", ["bad.xml", "bad.mxl"])
def test_entity_declarations_are_refused(client: TestClient, library: Path, document: bytes, name: str):
    data = mxl(document) if name.endswith("mxl") else document
    refused(client, library, data, name, "entity declarations")


def test_a_reference_to_an_undefined_entity_is_not_resolved(client: TestClient, library: Path):
    document = b"<score-partwise><part id='P1'><measure>&xxe;</measure></part></score-partwise>"
    refused(client, library, document, "ref.xml", "not valid XML")


def test_the_musicxml_dtd_is_never_fetched(client: TestClient):
    # real exports point at a DTD on musicxml.org; the parser must not try to load it
    assert b"DOCTYPE score-partwise PUBLIC" in SCORE
    assert upload(client, SCORE, "dtd.xml").status_code == 201


@pytest.mark.parametrize(
    "document, fragment",
    [
        (b"<html><body/></html>", "not a MusicXML score"),
        (b"<score-timewise><measure number='1'/></score-timewise>", "score-timewise"),
        (b"<score-partwise><part-list/></score-partwise>", "no parts"),
        (b"<score-partwise><part id='P1'", "not valid XML"),
    ],
)
def test_xml_that_is_not_a_partwise_score_is_refused(client: TestClient, library: Path, document: bytes, fragment: str):
    refused(client, library, document, "other.xml", fragment)


# -- size of the score --------------------------------------------------------------------------


def test_too_many_parts_or_bars_are_refused_before_importing(client: TestClient, library: Path):
    parts = b"".join(b"<part id='P%d'><measure number='1'/></part>" % i for i in range(MAX_PARTS + 1))
    refused(client, library, b"<score-partwise>" + parts + b"</score-partwise>", "many.xml", "parts")
    bars = b"<measure number='1'/>" * (MAX_MEASURES + 1)
    refused(client, library, b"<score-partwise><part id='P1'>" + bars + b"</part></score-partwise>", "long.xml", "bars")


def test_the_library_has_a_limit(tmp_path: Path):
    client = TestClient(create_app(ServerConfig(library=tmp_path / "lib", max_pieces=2)))
    assert upload(client, SCORE, "1.xml").status_code == 201
    assert upload(client, SCORE, "2.xml").status_code == 201
    response = upload(client, SCORE, "3.xml")
    assert response.status_code == 409 and "full" in response.json()["detail"]


def test_replacing_a_score_is_validated_too(client: TestClient, library: Path):
    upload(client, SCORE, "a.musicxml")
    piece_id = client.get("/api/pieces").json()[0]["id"]
    before = (library / piece_id / "piece.json").read_bytes()
    response = client.post(f"/api/pieces/{piece_id}/score", files={"file": ("b.xml", BILLION_LAUGHS, "application/xml")})
    assert response.status_code == 422 and "entity declarations" in response.json()["detail"]
    assert (library / piece_id / "piece.json").read_bytes() == before
