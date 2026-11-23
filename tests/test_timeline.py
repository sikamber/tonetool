import pytest

from tonetool.timeline import TimelineBuilder

from . import scorebuilder as sb


def test_unrolled_duration_and_source_map(import_score):
    piece = import_score(sb.endings_score(), bpm=120)  # whole-note bars = 2 s
    timeline = TimelineBuilder(piece).build()
    assert [s.source_measure for s in timeline.spans] == [0, 1, 2, 0, 1, 3, 4, 5]
    assert timeline.duration == pytest.approx(16.0)
    assert timeline.span_at(0.0).source_measure == 0
    assert timeline.span_at(6.5).source_measure == 0  # second pass through bar 1
    assert timeline.span_at(15.9).source_measure == 5


def test_notes_are_repeated_with_correct_times(import_score):
    piece = import_score(sb.endings_score(), bpm=120)
    timeline = TimelineBuilder(piece).build()
    soprano = timeline.notes_for("T0")
    assert len(soprano) == 8  # one whole note per performed bar
    assert [round(n.start_sec, 3) for n in soprano] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert [n.source_measure for n in soprano] == [0, 1, 2, 0, 1, 3, 4, 5]


def test_tempo_scale_stretches_time(import_score):
    piece = import_score(sb.simple_score(), bpm=120)
    assert TimelineBuilder(piece, tempo_scale=0.5).build().duration == pytest.approx(16.0)
    assert TimelineBuilder(piece, tempo_scale=2.0).build().duration == pytest.approx(4.0)


def test_rejects_bad_input(import_score):
    piece = import_score(sb.simple_score())
    with pytest.raises(ValueError):
        TimelineBuilder(piece, tempo_scale=0)
    with pytest.raises(ValueError):
        TimelineBuilder(piece).build([0, 9])


def test_tied_note_ends_when_next_performed_bar_is_not_its_continuation(import_score):
    parts = ["Soprano"]
    bars = [
        sb.Bar(notes={"Soprano": "C5/h D5/h~"}),
        sb.Bar(notes={"Soprano": "~D5/h E5/h"}),
        sb.Bar(notes={"Soprano": "G5/w"}),
    ]
    piece = import_score((parts, bars), bpm=120)  # quarter = 0.5 s
    straight = TimelineBuilder(piece).build([0, 1, 2]).notes_for("T0")
    assert straight[1].duration_sec == pytest.approx(2.0)  # D lasts through the tie
    skipped = TimelineBuilder(piece).build([0, 2]).notes_for("T0")
    assert skipped[1].duration_sec == pytest.approx(1.0)  # clipped at the end of bar 1


def test_arbitrary_measure_list(import_score):
    piece = import_score(sb.simple_score())
    timeline = TimelineBuilder(piece).build([3, 3, 0])
    assert [s.source_measure for s in timeline.spans] == [3, 3, 0]


def span(notes, pitch):
    """(start, end) in seconds of each note of this pitch, in order."""
    return [(round(n.start_sec, 3), round(n.start_sec + n.duration_sec, 3)) for n in notes if n.pitch == pitch]


THREE_BAR_TIE = [
    sb.Bar(notes={"Soprano": "C5/h E5/h~"}),
    sb.Bar(notes={"Soprano": "~E5/w~"}),
    sb.Bar(notes={"Soprano": "~E5/w"}),
]


def test_long_tie_chain_is_held_through_every_link(import_score):
    piece = import_score((["Soprano"], THREE_BAR_TIE), bpm=120)  # bar = 2 s
    notes = TimelineBuilder(piece).build([0, 1, 2]).notes_for("T0")
    assert span(notes, 76) == [(1.0, 6.0)]  # one note, half bar + two whole bars
    assert [n.attack for n in notes if n.pitch == 76] == [True]


def test_long_tie_chain_stops_where_the_jump_breaks_it(import_score):
    piece = import_score((["Soprano"], THREE_BAR_TIE), bpm=120)
    notes = TimelineBuilder(piece).build([0, 1, 0]).notes_for("T0")  # bar 3 never reached
    assert span(notes, 76) == [(1.0, 4.0), (5.0, 6.0)]  # must not ring into the repeated bar


def test_tie_into_both_endings_is_held_on_the_second_pass(import_score):
    bars = [
        sb.Bar(notes={"Soprano": "C5/h E5/h~"}, forward_repeat=True),
        sb.Bar(notes={"Soprano": "~E5/h G5/h"}, ending="1", backward_repeat=True),
        sb.Bar(notes={"Soprano": "~E5/h A5/h"}, ending="2"),
        sb.Bar(notes={"Soprano": "C5/w"}),
    ]
    piece = import_score((["Soprano"], bars), bpm=120)
    timeline = TimelineBuilder(piece).build()
    assert [s.source_measure for s in timeline.spans] == [0, 1, 0, 2, 3]
    e5 = [n for n in timeline.notes_for("T0") if n.pitch == 76]
    assert span(e5, 76) == [(1.0, 3.0), (5.0, 7.0)]  # second pass: held into the 2nd ending
    assert all(n.attack for n in e5)  # ...with no re-strike at the barline


def test_tie_into_first_ending_only_stops_on_the_second_pass(import_score):
    bars = [
        sb.Bar(notes={"Soprano": "C5/h E5/h~"}, forward_repeat=True),
        sb.Bar(notes={"Soprano": "~E5/h G5/h"}, ending="1", backward_repeat=True),
        sb.Bar(notes={"Soprano": "A5/h A5/h"}, ending="2"),
    ]
    piece = import_score((["Soprano"], bars), bpm=120)
    notes = TimelineBuilder(piece).build().notes_for("T0")
    assert span(notes, 76) == [(1.0, 3.0), (5.0, 6.0)]


def test_continuation_with_nothing_to_continue_sounds_without_attack(import_score):
    piece = import_score((["Soprano"], THREE_BAR_TIE), bpm=120)
    notes = TimelineBuilder(piece).build([1]).notes_for("T0")  # start mid-tie, e.g. a looped section
    assert span(notes, 76) == [(0.0, 2.0)]  # sounds from the start, for its notated length
    assert [n.attack for n in notes] == [False]


def test_tied_chord_holds_each_pitch(import_score):
    bars = [
        sb.Bar(notes={"Soprano": "C5/h E5/h~ +G5/h~"}),  # chord at the end of the bar, tied on
        sb.Bar(notes={"Soprano": "~E5/h +~G5/h"}),
    ]
    piece = import_score((["Soprano"], bars), bpm=120)
    notes = TimelineBuilder(piece).build([0, 1]).notes_for("T0")
    assert span(notes, 76) == [(1.0, 3.0)]
    assert span(notes, 79) == [(1.0, 3.0)]


def test_continuation_right_after_same_pitch_is_merged_not_restruck(import_score):
    # A loop/jump lands on a tied continuation, and the note just played has the same pitch and
    # ends exactly there: the held note carries on rather than re-striking.
    bars = [
        sb.Bar(notes={"Soprano": "C5/h E5/h"}),
        sb.Bar(notes={"Soprano": "R/w"}),
        sb.Bar(notes={"Soprano": "~E5/w"}),
    ]
    piece = import_score((["Soprano"], bars), bpm=120)
    notes = TimelineBuilder(piece).build([0, 2]).notes_for("T0")
    assert span(notes, 76) == [(1.0, 4.0)]


def test_each_measure_keeps_its_own_notated_tempo_wherever_it_is_played(import_score):
    parts, bars = sb.simple_score()
    bars[2].tempo = 60  # bar 3 at 60 bpm: a 4-beat bar takes 4 s; the others take 2 s at 120
    piece = import_score((parts, bars), bpm=120)
    timeline = TimelineBuilder(piece).build([2, 0, 3])
    assert [round(span.end_sec - span.start_sec, 3) for span in timeline.spans] == [4.0, 2.0, 4.0]
    # bar 4 follows bar 3's mark in notated order, so it is slow even though it is played last
