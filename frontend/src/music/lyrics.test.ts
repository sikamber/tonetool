import { describe, expect, it } from "vitest";
import { LyricsView } from "./lyrics";
import { makePiece, type BarSpec, type LyricSpec } from "./testPieces";
import { TimelineBuilder } from "./timeline";

// 4/4 at 120 bpm: a quarter note is 0.5 s
const syl = (text: string, syllabic: LyricSpec[2] = "single", number = "1"): LyricSpec[] => [[number, text, syllabic]];
const bar = (...notes: [number, number, number, boolean | undefined, LyricSpec[]][]): BarSpec => ({ notes: { T0: notes } });
const q = (offset: number, lyrics: LyricSpec[] | null, duration = 1): [number, number, number, boolean | undefined, LyricSpec[]] => [
  60,
  offset,
  duration,
  undefined,
  lyrics ?? [],
];

const view = (piece: ReturnType<typeof makePiece>) => new LyricsView(new TimelineBuilder(piece).build(), "T0");
const texts = (v: LyricsView) => v.sections.map((s) => s.lines.map((l) => l.words.map((w) => w.syllables.map((x) => x.text).join(""))));

describe("LyricsView", () => {
  it("joins the syllables of a word, whatever their flags say about where it begins", () => {
    // like the real score: "Ju" and "le" and "træ" are all 'middle', "et" has no flag
    const piece = makePiece({
      bars: [bar(q(0, syl("Ju", "middle")), q(1, syl("le", "middle")), q(2, syl("træ", "middle")), q(3, syl("et")))],
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    expect(texts(view(piece))).toEqual([[["Juletræet"]]]);
  });

  it("starts a new line after sentence-ending punctuation", () => {
    const piece = makePiece({
      bars: [bar(q(0, syl("Hej,")), q(1, syl("du.")), q(2, syl("Og")), q(3, syl("så")))],
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    expect(texts(view(piece))).toEqual([[["Hej,", "du."], ["Og", "så"]]]);
  });

  it("starts a new line where the voice rests for a beat or more", () => {
    const piece = makePiece({
      bars: [bar(q(0, syl("a")), q(1, syl("b"), 0.5), q(2, syl("c")), q(3, syl("d"), 0.5))], // rest of half a beat after d
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    // b ends at 1.5 and c starts at 2: a rest of half a beat is not a break
    expect(texts(view(piece))).toEqual([[["a", "b", "c", "d"]]]);
    const rest = makePiece({
      bars: [bar(q(0, syl("a")), q(2, syl("b")))], // one beat of rest between a and b
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    expect(texts(view(rest))).toEqual([[["a"], ["b"]]]);
  });

  it("gives each section the lyric line it sings", () => {
    const piece = makePiece({
      bars: [bar(q(0, [["1", "one"], ["2", "two"]]), q(1, [["1", "uno"], ["2", "dos"]]))],
      sections: [[[0, 0]], [[0, 0]]],
      lyricNumbers: ["1", "2"],
    });
    expect(texts(view(piece))).toEqual([[["one", "uno"]], [["two", "dos"]]]);
  });

  it("leaves out sections without lyrics and is empty when there are none", () => {
    const piece = makePiece({ bars: [bar(q(0, syl("a")))], sections: [[[0, 0]]] });
    expect(view(piece).isEmpty).toBe(true);
    expect(view(piece).sections).toEqual([]);
  });

  it("finds the syllable being sung at a time", () => {
    const piece = makePiece({
      bars: [bar(q(0, syl("a")), q(1, syl("b")), q(2, syl("c")))],
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    const v = view(piece);
    expect(v.syllableAt(0)?.text).toBe("a");
    expect(v.syllableAt(0.9)?.text).toBe("b");
    expect(v.syllableAt(1.0)?.text).toBe("c"); // b starts at 0.5 s, c at 1.0 s
    expect(v.syllableAt(99)?.text).toBe("c");
  });

  it("lists the lines across sections and finds the one being sung", () => {
    const piece = makePiece({
      bars: [bar(q(0, [["1", "a."], ["2", "x."]]), q(2, [["1", "b"], ["2", "y"]]))],
      sections: [[[0, 0]], [[0, 0]]],
      lyricNumbers: ["1", "2"],
    });
    const v = view(piece); // each pass is 2 s long: lines start at 0, 1, 2 and 3 s
    expect(v.lines.map((l) => [l.section.id, l.words[0]!.syllables[0]!.text])).toEqual([
      ["s1", "a."], ["s1", "b"], ["s2", "x."], ["s2", "y"],
    ]);
    expect([-1, 0, 0.9, 1, 2.4, 3, 99].map((t) => v.lineIndexAt(t))).toEqual([0, 0, 0, 1, 2, 3, 3]);
  });

  it("reads another voice and follows the tempo", () => {
    const piece = makePiece({
      tracks: ["T0", "T1"],
      bars: [{ notes: { T0: [[60, 0, 4, undefined, syl("x")]], T1: [[64, 0, 4, undefined, syl("y")]] } }],
      sections: [[[0, 0]]],
      lyricNumbers: ["1"],
    });
    const slow = new LyricsView(new TimelineBuilder(piece, 0.5).build(), "T1");
    expect(texts(slow)).toEqual([[["y"]]]);
    expect(slow.sections[0]!.lines[0]!.words[0]!.syllables[0]!.endSec).toBeCloseTo(4);
  });
});
