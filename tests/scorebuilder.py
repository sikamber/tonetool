"""Builds small MusicXML scores for tests and examples, so repeats/endings/jumps are exercised
without needing real scores checked into the repo.

Each measure is a ``Bar``; per-part notes are given as ``"C4/q D4/q E4/h"`` strings
(pitch/duration, duration in w h q e). Structural markings are fields on ``Bar``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

DURATIONS = {"w": 4, "h": 2, "q": 1, "e": 0.5}
TYPES = {"w": "whole", "h": "half", "q": "quarter", "e": "eighth"}
DIVISIONS = 2  # per quarter


@dataclass
class Bar:
    notes: dict[str, str]  # part name -> "C4/q D4/q ..."; use "R/q" for a rest
    forward_repeat: bool = False
    backward_repeat: bool = False
    ending: str | None = None  # "1" etc.; applied to this single bar (start+stop)
    ending_start: str | None = None  # open a multi-bar bracket
    ending_stop: bool = False  # close it after this bar
    rehearsal: str | None = None
    sound: dict[str, str] = field(default_factory=dict)  # e.g. {"dacapo": "yes"}
    words: str | None = None
    number: str | None = None  # printed number override
    implicit: bool = False


def _pitch_xml(token: str) -> str:
    """MusicXML ``<pitch>`` element for a token like 'C5', 'F#4' or 'Bb3'."""
    match = re.fullmatch(r"([A-G])([#b]?)(\d)", token)
    if not match:
        raise ValueError(f"bad pitch {token!r}")
    step, accidental, octave = match.groups()
    alter = {"#": 1, "b": -1, "": 0}[accidental]
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    return f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"


def _note_xml(token: str, voice: int = 1) -> str:
    """Token grammar: [+]['~']PITCH/DUR['~']  (+ chord member, leading ~ tie stop, trailing ~ tie start)."""
    chord = token.startswith("+")
    token = token.lstrip("+")
    tie_stop, tie_start = token.startswith("~"), token.endswith("~")
    pitch, _, dur = token.strip("~").partition("/")
    body = "<rest/>" if pitch == "R" else _pitch_xml(pitch)
    ties = ('<tie type="stop"/>' if tie_stop else "") + ('<tie type="start"/>' if tie_start else "")
    tied = ('<tied type="stop"/>' if tie_stop else "") + ('<tied type="start"/>' if tie_start else "")
    notations = f"<notations>{tied}</notations>" if tied else ""
    return (
        f"<note>{'<chord/>' if chord else ''}{body}<duration>{int(DURATIONS[dur] * DIVISIONS)}</duration>"
        f"{ties}<voice>{voice}</voice><type>{TYPES[dur]}</type>{notations}</note>"
    )


def _voice_length(tokens: list[str]) -> int:
    """Total divisions of a voice (chord members add no time)."""
    return sum(
        int(DURATIONS[t.lstrip("+").strip("~").partition("/")[2]] * DIVISIONS) for t in tokens if not t.startswith("+")
    )


def _measure_xml(bar: Bar, number: str, part_name: str, first: bool, bpm: int, time: tuple[int, int]) -> str:
    """One ``<measure>`` of one part, including its structural markings."""
    out = [f'<measure number="{number}"{" implicit=\"yes\"" if bar.implicit else ""}>']
    if first:
        out.append(
            f"<attributes><divisions>{DIVISIONS}</divisions><key><fifths>0</fifths></key>"
            f"<time><beats>{time[0]}</beats><beat-type>{time[1]}</beat-type></time>"
            f"<clef><sign>G</sign><line>2</line></clef></attributes>"
        )
        out.append(
            f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
            f"<per-minute>{bpm}</per-minute></metronome></direction-type><sound tempo=\"{bpm}\"/></direction>"
        )
    if bar.rehearsal:
        out.append(
            f"<direction><direction-type><rehearsal>{escape(bar.rehearsal)}</rehearsal></direction-type></direction>"
        )
    if bar.words:
        out.append(f"<direction><direction-type><words>{escape(bar.words)}</words></direction-type></direction>")
    if bar.sound:
        attrs = " ".join(f'{k}="{v}"' for k, v in bar.sound.items())
        out.append(f"<direction><direction-type><words/></direction-type><sound {attrs}/></direction>")
    left = ""
    if bar.forward_repeat:
        left += '<repeat direction="forward"/>'
    start = bar.ending or bar.ending_start
    if start:
        left += f'<ending number="{start}" type="start"/>'
    if left:
        out.append(f'<barline location="left"><bar-style>heavy-light</bar-style>{left}</barline>')
    voices = bar.notes.get(part_name, "R/w").split("|")  # "|" separates voices on one staff
    for number_, voice_text in enumerate(voices, start=1):
        tokens = voice_text.split()
        if number_ > 1:
            out.append(f"<backup><duration>{_voice_length(voices[0].split())}</duration></backup>")
        out.extend(_note_xml(t, number_) for t in tokens)
    right = ""
    if bar.ending:
        right += f'<ending number="{bar.ending}" type="stop"/>'
    elif bar.ending_stop:
        right += '<ending number="1" type="stop"/>'
    if bar.backward_repeat:
        right += '<repeat direction="backward"/>'
    if right:
        out.append(f'<barline location="right">{right}</barline>')
    out.append("</measure>")
    return "".join(out)


def build_musicxml(
    parts: list[str], bars: list[Bar], title: str = "Test", bpm: int = 120, time: tuple[int, int] = (4, 4)
) -> str:
    """A complete score-partwise document with one part per name and one measure per Bar."""
    list_xml = "".join(
        f'<score-part id="P{i + 1}"><part-name>{escape(name)}</part-name></score-part>' for i, name in enumerate(parts)
    )
    body = []
    for i, name in enumerate(parts):
        measures = "".join(
            _measure_xml(bar, bar.number or str(n + 1), name, n == 0, bpm, time) for n, bar in enumerate(bars)
        )
        body.append(f'<part id="P{i + 1}">{measures}</part>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise version=\"4.0\"><work><work-title>{escape(title)}</work-title></work>"
        f"<part-list>{list_xml}</part-list>{''.join(body)}</score-partwise>"
    )


def write_score(path: Path, parts: list[str], bars: list[Bar], **kwargs: Any) -> Path:
    """Build a score and write it to ``path``; extra keyword arguments go to ``build_musicxml``."""
    path.write_text(build_musicxml(parts, bars, **kwargs))
    return path


# -- canned scores used by tests and examples ---------------------------------------------------

PARTS = ["Soprano", "Alto"]


def _bar(s: str, a: str, **kw: Any) -> Bar:
    """A Bar for the two-part (Soprano/Alto) canned scores."""
    return Bar(notes={"Soprano": s, "Alto": a}, **kw)


def simple_score() -> tuple[list[str], list[Bar]]:
    """4 straight bars, no structure markings."""
    return PARTS, [
        _bar("C5/q D5/q E5/q F5/q", "E4/q F4/q G4/q A4/q"),
        _bar("G5/h E5/h", "B4/h G4/h"),
        _bar("F5/q E5/q D5/q C5/q", "A4/q G4/q F4/q E4/q"),
        _bar("C5/w", "E4/w"),
    ]


def endings_score() -> tuple[list[str], list[Bar]]:
    """A (1-2, repeated with 1st/2nd ending at bars 3/4), then B (5-6). Notated order 1 2 3 4 5 6."""
    return PARTS, [
        _bar("C5/w", "E4/w", rehearsal="A", forward_repeat=True),
        _bar("D5/w", "F4/w"),
        _bar("E5/w", "G4/w", ending="1", backward_repeat=True),
        _bar("F5/w", "A4/w", ending="2"),
        _bar("G5/w", "B4/w", rehearsal="B"),
        _bar("C5/w", "E4/w"),
    ]


def dal_segno_score() -> tuple[list[str], list[Bar]]:
    """1 2 3(segno) 4(tocoda, D.S.) 5(coda). Expected: 1 2 3 4 | 3 4(stop at tocoda) -> 5."""
    return PARTS, [
        _bar("C5/w", "E4/w"),
        _bar("D5/w", "F4/w"),
        _bar("E5/w", "G4/w", sound={"segno": "s1"}),
        _bar("F5/w", "A4/w", sound={"tocoda": "c1", "dalsegno": "s1"}),
        _bar("G5/w", "B4/w", sound={"coda": "c1"}),
    ]


def text_only_jump_score() -> tuple[list[str], list[Bar]]:
    """A D.S. written only as text: the importer must warn and not guess."""
    parts, bars = simple_score()
    bars[3].words = "D.S. al Coda"
    return parts, bars
