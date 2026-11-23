from tonetool.models import PlaybackOrder, Provenance

from . import scorebuilder as sb


def numbers(piece):
    """Performed sequence as printed measure numbers."""
    return [piece.measures[i].number for i in piece.playback_order.measure_sequence()]


def test_straight_through(import_score):
    piece = import_score(sb.simple_score())
    assert piece.playback_order.measure_sequence() == [0, 1, 2, 3]
    assert len(piece.sections) == 1
    assert piece.sections[0].source is Provenance.AUTO
    assert piece.warnings == []


def test_repeat_with_first_and_second_ending(import_score):
    piece = import_score(sb.endings_score())
    # 1 2 3(1st ending) | back to 1 2, skip 3, play 4 | 5 6
    assert numbers(piece) == ["1", "2", "3", "1", "2", "4", "5", "6"]
    assert piece.playback_order.describe(piece.measures) == "1-3 | 1-2 | 4-6"


def ranges(section):
    return [(segment.start, segment.end) for segment in section.segments]


def test_sections_follow_the_performance_one_per_pass(import_score):
    piece = import_score(sb.endings_score())
    # pass 1 plays bars 1-3 (1st ending); pass 2 replays 1-2, skips to the 2nd ending (bar 4); then B
    assert [(s.name, ranges(s)) for s in piece.sections] == [
        ("A", [(0, 2)]),
        ("A (2)", [(0, 1), (3, 3)]),
        ("B", [(4, 5)]),
    ]
    assert [s.describe(piece.measures) for s in piece.sections] == ["1-3", "1-2, 4", "5-6"]


def test_sections_are_the_playback_order(import_score):
    piece = import_score(sb.endings_score())
    flat = [m for section in piece.sections for m in section.measure_sequence()]
    assert flat == piece.playback_order.measure_sequence() == [0, 1, 2, 0, 1, 3, 4, 5]


def test_playback_order_is_derived_and_not_stored(import_score):
    dumped = import_score(sb.endings_score()).model_dump()
    assert "playback_order" not in dumped
    assert "segments" in dumped["sections"][0]


def test_sections_may_share_bars_and_the_order_follows_them(import_score):
    from tonetool.models import Piece

    # the "three verses" case: verses 1 and 2 are the same notated bars, verse 3 is a variation
    data = import_score(sb.simple_score()).model_dump()
    data["sections"] = [
        {"id": "v1", "name": "Verse 1", "segments": [{"start": 0, "end": 1}]},
        {"id": "v2", "name": "Verse 2", "segments": [{"start": 0, "end": 1}]},
        {"id": "v3", "name": "Verse 3", "segments": [{"start": 2, "end": 3}]},
    ]
    piece = Piece.model_validate(data)
    assert piece.playback_order.measure_sequence() == [0, 1, 0, 1, 2, 3]
    assert piece.section("v2").measure_sequence() == [0, 1]


def test_piece_rejects_bad_sections(import_score):
    import pytest

    from tonetool.models import Piece

    good = import_score(sb.simple_score()).model_dump()

    def with_sections(sections):
        return {**good, "sections": sections}

    seg = {"start": 0, "end": 1}
    with pytest.raises(ValueError, match="at least one section"):
        Piece.model_validate(with_sections([]))
    with pytest.raises(ValueError):  # a section needs at least one range
        Piece.model_validate(with_sections([{"id": "a", "name": "A", "segments": []}]))
    with pytest.raises(ValueError, match="duplicate section ids"):
        Piece.model_validate(
            with_sections([{"id": "a", "name": "A", "segments": [seg]}] * 2)
        )
    with pytest.raises(ValueError, match=r"section 'a': segment 0-9 outside 0-3"):
        Piece.model_validate(
            with_sections([{"id": "a", "name": "A", "segments": [{"start": 0, "end": 9}]}])
        )


def test_old_schema_versions_ask_for_a_reimport(import_score, tmp_path):
    import json

    import pytest

    from tonetool.models import Piece

    data = import_score(sb.simple_score()).model_dump()
    data["schema_version"] = 1
    path = tmp_path / "old.piece.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="re-import the score"):
        Piece.load(path)


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
