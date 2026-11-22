from tonetool.models import PlaybackOrder, Provenance

from . import scorebuilder as sb


def numbers(piece):
    """Performed sequence as printed measure numbers."""
    return [piece.measures[i].number for i in piece.playback_order.measure_sequence()]


def test_straight_through(import_score):
    piece = import_score(sb.simple_score())
    assert piece.playback_order.measure_sequence() == [0, 1, 2, 3]
    assert len(piece.sections) == 1
    assert piece.playback_order.source is Provenance.AUTO
    assert piece.warnings == []


def test_repeat_with_first_and_second_ending(import_score):
    piece = import_score(sb.endings_score())
    # 1 2 3(1st ending) | back to 1 2, skip 3, play 4 | 5 6
    assert numbers(piece) == ["1", "2", "3", "1", "2", "4", "5", "6"]
    assert piece.playback_order.describe(piece.measures) == "1-3 | 1-2 | 4-6"


def test_sections_from_rehearsal_marks(import_score):
    piece = import_score(sb.endings_score())
    assert [(s.name, s.start, s.end) for s in piece.sections] == [("A", 0, 3), ("B", 4, 5)]


def test_dal_segno_al_coda(import_score):
    piece = import_score(sb.dal_segno_score())
    # 1 2 3 4(D.S.) -> 3 4(to coda) -> 5
    assert numbers(piece) == ["1", "2", "3", "4", "3", "4", "5"]


def test_plain_repeat_without_endings(import_score):
    parts, bars = sb.simple_score()
    bars[0].forward_repeat = True
    bars[1].backward_repeat = True
    piece = import_score((parts, bars))
    assert numbers(piece) == ["1", "2", "1", "2", "3", "4"]


def test_text_only_jump_warns_and_is_not_followed(import_score):
    piece = import_score(sb.text_only_jump_score())
    assert piece.playback_order.measure_sequence() == [0, 1, 2, 3]
    assert any("D.S. al Coda" in w and "not encoded" in w for w in piece.warnings)


def test_playback_order_compression_roundtrip():
    order = PlaybackOrder.from_measure_sequence([0, 1, 2, 1, 2, 4])
    assert [(s.start, s.end) for s in order.segments] == [(0, 2), (1, 2), (4, 4)]
    assert order.measure_sequence() == [0, 1, 2, 1, 2, 4]
