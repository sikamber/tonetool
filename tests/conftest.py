from pathlib import Path

import pytest

from tonetool.importer import ScoreImporter
from tonetool.models import Piece

from . import scorebuilder as sb


@pytest.fixture
def import_score(tmp_path: Path):
    """import_score(sb.endings_score()) -> Piece"""

    def _import(score: tuple[list[str], list[sb.Bar]], name: str = "score", **kwargs) -> Piece:
        parts, bars = score
        path = sb.write_score(tmp_path / f"{name}.musicxml", parts, bars, **kwargs)
        return ScoreImporter(path).run()

    return _import
