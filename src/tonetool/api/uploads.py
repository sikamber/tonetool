"""Checking an uploaded score before anything is done with it.

The importer (music21, lxml) is not meant to be pointed at hostile files, and parsing is slow, so
an upload is looked at first, cheaply: does the content match what the name claims, is the archive
sane, is the XML safe to parse, is it a MusicXML score at all, and is it of a size we will import.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path, PurePosixPath

from lxml import etree

from ..structure import hardened_parser
from .errors import ClientError

ZIP_MAGIC = b"PK\x03\x04"
# An XML document starts with an optional byte-order mark, whitespace, and then "<"
XML_START = re.compile(rb"^(?:\xef\xbb\xbf)?\s*<")
MAX_ARCHIVE_ENTRIES = 50
MAX_CONTAINER_BYTES = 1024 * 1024
# A real choir score has a few parts and a few hundred bars; these only stop abuse.
MAX_PARTS = 40
MAX_MEASURES = 2000
MAX_NOTES = 500_000


class ScoreValidator:
    """Checks a score's bytes against its file name. Raises ``ClientError`` with a reason."""

    def __init__(self, max_unpacked_mb: int = 100) -> None:
        """``max_unpacked_mb`` limits what a compressed (.mxl) score may expand to."""
        self.max_unpacked = max_unpacked_mb * 1024 * 1024

    def check(self, filename: str, data: bytes) -> None:
        """Raise ``ClientError`` unless ``data`` is a MusicXML score we are willing to import."""
        if Path(filename).suffix.lower() == ".mxl":
            document = self._unzip(data)
        else:
            if data.startswith(ZIP_MAGIC):
                raise ClientError("this file is a ZIP archive: a compressed score should be named .mxl")
            if not XML_START.match(data[:64]):
                raise ClientError("this file is not an XML document")
            document = data
        self._check_document(document)

    def _unzip(self, data: bytes) -> bytes:
        """The score document inside a compressed .mxl, after checking the archive is sane."""
        if not data.startswith(ZIP_MAGIC):
            raise ClientError("this file is not a valid .mxl (it is not a ZIP archive)")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as error:
            raise ClientError("this file is not a valid .mxl (the ZIP archive is damaged)") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ClientError(f"the archive has {len(infos)} files; a score has only a few")
            unpacked = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise ClientError("the archive is encrypted")
                if self._unsafe_name(info.filename):
                    raise ClientError(f"the archive has an unsafe file name: {info.filename!r}")
                unpacked += info.file_size
                if unpacked > self.max_unpacked:
                    raise ClientError(f"the archive unpacks to more than {self.max_unpacked // (1024 * 1024)} MB")
            container = self._member(archive, "META-INF/container.xml", MAX_CONTAINER_BYTES)
            root = self._parse(container)
            rootfile = root.find(".//rootfile")
            name = rootfile.get("full-path") if rootfile is not None else None
            if not name:
                raise ClientError("the archive's META-INF/container.xml names no score")
            return self._member(archive, name, self.max_unpacked)

    @staticmethod
    def _unsafe_name(name: str) -> bool:
        """Absolute paths, drive letters and ``..`` (a name that would climb out of a folder)."""
        parts = PurePosixPath(name.replace("\\", "/")).parts
        return name.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:", name)) or ".." in parts

    @staticmethod
    def _member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
        try:
            info = archive.getinfo(name)
        except KeyError:
            raise ClientError(f"the archive has no {name}") from None
        if info.file_size > limit:
            raise ClientError(f"{name} in the archive is too large")
        return archive.read(info)

    def _check_document(self, document: bytes) -> None:
        """The XML must be parseable without risk, be a partwise MusicXML score, and not be huge."""
        if b"<!ENTITY" in document:
            raise ClientError("XML entity declarations are not allowed in a score")
        root = self._parse(document)
        kind = etree.QName(root).localname
        if kind == "score-timewise":
            raise ClientError("score-timewise MusicXML is not supported: export the score as partwise")
        if kind != "score-partwise":
            raise ClientError(f"this is not a MusicXML score (its root element is <{kind}>)")
        parts = root.findall("part")
        if not parts:
            raise ClientError("the score has no parts")
        if len(parts) > MAX_PARTS:
            raise ClientError(f"the score has {len(parts)} parts; the limit is {MAX_PARTS}")
        measures = max(len(part.findall("measure")) for part in parts)
        if measures > MAX_MEASURES:
            raise ClientError(f"the score has {measures} bars; the limit is {MAX_MEASURES}")
        notes = sum(1 for _ in root.iter("note"))
        if notes > MAX_NOTES:
            raise ClientError(f"the score has {notes} notes; the limit is {MAX_NOTES}")

    @staticmethod
    def _parse(document: bytes) -> etree._Element:
        try:
            return etree.fromstring(document, hardened_parser())
        except etree.XMLSyntaxError as error:
            raise ClientError(f"the file is not valid XML: {error}") from error
