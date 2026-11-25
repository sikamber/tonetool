"""Read structural markings directly from MusicXML and suggest sections + playback order.

music21 is used for notes (see importer.py); the structural bits are read with lxml so that we see
exactly what the exporter wrote. Exporters differ a lot here (e.g. "D.S. al Coda" is often only
text), so anything we cannot interpret reliably becomes a warning, not a guess.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .models import PlaybackOrder, Section

_JUMP_TEXT = re.compile(
    r"\b(d\.?\s?[cs]\.?|da\s+capo|dal\s+segno|fine|to\s+coda|al\s+coda|coda)\b", re.I
)


def hardened_parser() -> etree.XMLParser:
    """An XML parser that is safe to point at a file somebody else made.

    Entities are not resolved (so no ``&xxe;`` reading local files and no entity bombs), the DTD
    that MusicXML files point to is neither loaded nor fetched, nothing touches the network, and
    absurdly deep or huge documents are refused.
    """
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False
    )


def read_musicxml_root(path: Path) -> etree._Element:
    """Parse .musicxml/.xml, or the main document inside a compressed .mxl."""
    parser = hardened_parser()
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as archive:
            container = etree.fromstring(archive.read("META-INF/container.xml"), parser)
            rootfile = container.find(".//rootfile")
            full_path = rootfile.get("full-path") if rootfile is not None else None
            if full_path is None:
                raise ValueError(f"{path}: META-INF/container.xml has no rootfile")
            return etree.fromstring(archive.read(full_path), parser)
    return etree.parse(str(path), parser).getroot()


def _parse_ending_numbers(raw: str) -> set[int]:
    """'1' -> {1}; '1, 2' -> {1,2}; '1-3' -> {1,2,3}."""
    numbers: set[int] = set()
    for chunk in re.split(r"[,\s]+", raw.strip()):
        if not chunk:
            continue
        if "-" in chunk:
            low, _, high = chunk.partition("-")
            numbers.update(range(int(low), int(high) + 1))
        else:
            numbers.add(int(chunk))
    return numbers


@dataclass
class MeasureMarkCollection:
    """Structural markings found on one notated measure."""

    index: int
    number: str
    forward_repeat: bool = False
    backward_repeat: bool = False
    repeat_times: int = 2  # total passes through the repeated block
    ending_numbers: set[int] | None = (
        None  # set when the measure sits in a volta bracket
    )
    rehearsal: str | None = None
    segno: set[str] = field(default_factory=set)  # targets defined here
    coda: set[str] = field(default_factory=set)
    dacapo: bool = False
    dalsegno: str | None = None
    tocoda: str | None = None
    fine: bool = False
    jump_text: list[str] = field(default_factory=list)  # raw words like "D.S. al Coda"


class SuggestedStructure:
    """Builds suggested sections and a playback order from the XML of one score."""

    def __init__(self, root: etree._Element) -> None:
        """Read the structural markings from a parsed MusicXML document."""
        self.measure_mark_collections: list[MeasureMarkCollection] = self._collect(root)
        self.warnings: list[str] = []

    # -- collection ---------------------------------------------------------------------------

    @staticmethod
    def _collect(root: etree._Element) -> list[MeasureMarkCollection]:
        """Walk the first part's measures once and record the markings found on each."""
        part = root.find("part")
        if part is None:
            raise ValueError("MusicXML has no <part>")
        marks: list[MeasureMarkCollection] = []
        active_ending: set[int] | None = None
        for index, measure in enumerate(part.findall("measure")):
            m = MeasureMarkCollection(
                index=index, number=measure.get("number", str(index + 1))
            )
            for barline in measure.findall("barline"):
                ending = barline.find("ending")
                if ending is not None and ending.get("type") == "start":
                    active_ending = _parse_ending_numbers(ending.get("number", "1"))
                repeat = barline.find("repeat")
                if repeat is not None:
                    if repeat.get("direction") == "forward":
                        m.forward_repeat = True
                    else:
                        m.backward_repeat = True
                        m.repeat_times = int(repeat.get("times", "2"))
            m.ending_numbers = set(active_ending) if active_ending is not None else None
            for barline in measure.findall("barline"):
                ending = barline.find("ending")
                if ending is not None and ending.get("type") in ("stop", "discontinue"):
                    active_ending = None
            for rehearsal in measure.iter("rehearsal"):
                m.rehearsal = (rehearsal.text or "").strip() or m.rehearsal
            for words in measure.iter("words"):
                text = (words.text or "").strip()
                if text and _JUMP_TEXT.search(text):
                    m.jump_text.append(text)
            for sound in measure.iter("sound"):
                if segno := sound.get("segno"):
                    m.segno.add(segno)
                if coda := sound.get("coda"):
                    m.coda.add(coda)
                if sound.get("dacapo") == "yes":
                    m.dacapo = True
                if sound.get("dalsegno"):
                    m.dalsegno = sound.get("dalsegno")
                if sound.get("tocoda"):
                    m.tocoda = sound.get("tocoda")
                if sound.get("fine"):
                    m.fine = True
            marks.append(m)
        return marks

    # -- sections -----------------------------------------------------------------------------

    def suggest_sections(self) -> list[Section]:
        """Cut the performed sequence into sections: runs of notated ranges, in playback order.

        A section starts at the first measure, at every rehearsal mark and forward repeat, and
        wherever the music jumps back (a repeat or D.S.), so each pass through a repeated passage
        becomes its own section. A pass that skips forward (past a first ending, or to a coda)
        stays one section made of several ranges. The playback order is these sections in order.
        """
        marks = self.measure_mark_collections
        sequence = self._performed_sequence()
        passes: list[list[int]] = []
        for position, index in enumerate(sequence):
            jumped_back = position > 0 and index <= sequence[position - 1]
            if (
                position == 0
                or jumped_back
                or marks[index].rehearsal
                or marks[index].forward_repeat
            ):
                passes.append([])
            passes[-1].append(index)

        sections: list[Section] = []
        times_used: dict[str, int] = {}  # so a repeated pass reads "A", then "A (2)"
        for number, measure_indices in enumerate(passes, start=1):
            name = marks[measure_indices[0]].rehearsal or f"Section {number}"
            times_used[name] = times_used.get(name, 0) + 1
            if times_used[name] > 1:
                name = f"{name} ({times_used[name]})"
            sections.append(
                Section(
                    id=f"s{number}",
                    name=name,
                    segments=PlaybackOrder.from_measure_sequence(measure_indices).segments,
                )
            )
        return sections

    # -- playback order -----------------------------------------------------------------------

    def _performed_sequence(self) -> list[int]:
        """Simulate repeats, voltas, and encoded jumps to get the performed measure sequence.

        Conventions (standard, but they are conventions):
        * a backward repeat plays the block ``repeat_times`` times (default 2);
        * after a da capo / dal segno jump, repeats are not taken and the *last* volta is played;
        * ``fine`` only stops playback after a jump; ``tocoda`` only jumps after a jump.
        Jumps are only honoured if encoded in ``<sound>``; text-only jumps produce a warning.
        """
        marks = self.measure_mark_collections
        count = len(marks)
        segno_at = {s: m.index for m in marks for s in m.segno}
        coda_at = {c: m.index for m in marks for c in m.coda}
        run_last_ending = self._last_ending_per_measure()

        sequence: list[int] = []
        passes: dict[int, int] = {}  # repeat start measure -> completed repeats
        repeat_start = 0
        jumped = False
        in_volta = False
        i = 0
        budget = count * 50 + 100  # guards against malformed jump loops
        while i < count and budget > 0:
            budget -= 1
            m = marks[i]
            if m.forward_repeat:
                repeat_start = i
            if m.ending_numbers is None and in_volta:
                # Left a volta bracket: that repeat is finished, whatever came after it.
                in_volta = False
                passes.pop(repeat_start, None)
                repeat_start = i
            if m.ending_numbers is not None:
                in_volta = True
                current_pass = (
                    run_last_ending[i] if jumped else passes.get(repeat_start, 0) + 1
                )
                if current_pass not in m.ending_numbers:
                    i += 1  # skip this volta measure; the matching one comes later
                    continue
            sequence.append(i)

            if m.backward_repeat and not jumped:
                done = passes.get(repeat_start, 0) + 1
                if done < m.repeat_times:
                    passes[repeat_start] = done
                    in_volta = False  # jumping back is not leaving the bracket
                    i = repeat_start
                    continue
                passes[repeat_start] = (
                    0  # finished; a later forward repeat starts fresh
                )
                repeat_start = i + 1
            if jumped and m.fine:
                break
            if jumped and m.tocoda and m.tocoda in coda_at:
                i = coda_at[m.tocoda]
                continue
            if not jumped and m.dacapo:
                jumped, i = True, 0
                continue
            if not jumped and m.dalsegno:
                target = segno_at.get(m.dalsegno)
                if target is None:
                    self.warnings.append(
                        f"measure {m.number}: dalsegno={m.dalsegno!r} has no matching segno"
                    )
                else:
                    jumped, i = True, target
                    continue
            i += 1
        if budget <= 0:
            self.warnings.append(
                "playback simulation hit its step limit; check jump markings"
            )

        self._warn_about_unencoded_jumps()
        return sequence

    def _last_ending_per_measure(self) -> dict[int, int]:
        """For each measure in a volta run, the highest ending number in that contiguous run."""
        result: dict[int, int] = {}
        run: list[int] = []
        for m in [
            *self.measure_mark_collections,
            MeasureMarkCollection(index=-1, number=""),
        ]:
            if m.ending_numbers is not None:
                run.append(m.index)
                continue
            if run:
                top = max(
                    max(self.measure_mark_collections[r].ending_numbers or {1})
                    for r in run
                )
                result.update({r: top for r in run})
                run = []
        return result

    def _warn_about_unencoded_jumps(self) -> None:
        """Warn where jump-like text (D.S., Fine, ...) has no matching ``<sound>`` encoding."""
        for m in self.measure_mark_collections:
            encoded = m.dacapo or m.dalsegno or m.tocoda or m.fine
            if m.jump_text and not encoded:
                self.warnings.append(
                    f"measure {m.number}: text {m.jump_text!r} looks like a jump but is not "
                    "encoded in <sound>; playback order ignores it, please review"
                )
