import { describe, expect, it } from "vitest";
import { KeyColors } from "./keyColors";
import { PianoRollLayout, pitchName } from "./pianoRoll";
import { makePiece } from "./testPieces";
import { TimelineBuilder } from "./timeline";

const C_MAJOR = new KeyColors({ tonic: "C", mode: "major" });
// 4/4 at 120 bpm: a quarter is 0.5 s, a bar 2 s
const piece = () =>
  makePiece({
    tracks: ["T0", "T1"],
    bars: [
      { notes: { T0: [[72, 0, 2], [74, 2, 2]], T1: [[48, 0, 4]] } },
      { notes: { T0: [[76, 0, 4]], T1: [[50, 0, 4]] } },
    ],
    sections: [[[0, 0]], [[1, 1]]],
  });
const timeline = () => new TimelineBuilder(piece()).build();
const layout = (extra = {}) => new PianoRollLayout(timeline(), C_MAJOR, { pixelsPerSecond: 100, rowHeight: 10, ...extra });

describe("pitchName", () => {
  it("names pitches with their octave", () => {
    expect([60, 61, 69, 48, 12, 0].map(pitchName)).toEqual(["C4", "C#4", "A4", "C3", "C0", "C-1"]);
  });
});

describe("PianoRollLayout", () => {
  it("puts time to the right and higher notes higher up", () => {
    const l = layout();
    const byPitch = (p: number) => l.rects.find((r) => r.pitch === p)!;
    expect(byPitch(72).x).toBe(0);
    expect(byPitch(74).x).toBe(100); // 1 s at 100 px/s
    expect(byPitch(76).x).toBe(200);
    expect(byPitch(76).y).toBeLessThan(byPitch(72).y);
    expect(byPitch(72).y - byPitch(74).y).toBe(20); // two semitones, 10 px a row
    expect(byPitch(72).width).toBe(99); // 1 s minus a 1 px gap
    expect(byPitch(72).height).toBe(9);
  });

  it("covers the whole piece and all the pitches with a margin", () => {
    const l = layout();
    expect(l.width).toBe(400); // 4 s
    expect([l.lowPitch, l.highPitch]).toEqual([47, 77]);
    expect(l.height).toBe((77 - 47 + 1) * 10);
    expect(l.rows).toHaveLength(31);
    expect(l.rows[0]!.pitch).toBe(77); // highest row first
    expect(l.rows.at(-1)!.pitch).toBe(47);
    expect(l.rows.every((row, i) => row.y === i * 10)).toBe(true);
  });

  it("labels C rows, marks black keys and shades the tonic rows", () => {
    const l = layout();
    expect(l.rows.filter((r) => r.label).map((r) => r.label)).toEqual(["C5", "C4", "C3"]);
    expect(l.rows.find((r) => r.pitch === 61 || r.pitch === 49)!.isBlackKey).toBe(true);
    expect(l.rows.find((r) => r.pitch === 62)!.isBlackKey).toBe(false);
    expect(l.rows.filter((r) => r.isTonic).map((r) => r.pitch)).toEqual([72, 60, 48]);
    const noKey = new PianoRollLayout(timeline(), new KeyColors(null), { pixelsPerSecond: 100, rowHeight: 10 });
    expect(noKey.rows.some((r) => r.isTonic)).toBe(false);
  });

  it("colours each note by its place in the key", () => {
    const l = layout();
    expect(l.rects.find((r) => r.pitch === 72)!.color.syllable).toBe("do");
    expect(l.rects.find((r) => r.pitch === 74)!.color.syllable).toBe("re");
    expect(l.rects.find((r) => r.pitch === 76)!.color.syllable).toBe("mi");
  });

  it("draws only the visible voices but keeps the pitch range of all of them", () => {
    const l = layout({ visibleTracks: new Set(["T0"]) });
    expect(new Set(l.rects.map((r) => r.trackId))).toEqual(new Set(["T0"]));
    expect([l.lowPitch, l.highPitch]).toEqual([47, 77]); // the bass is hidden, the range does not jump
  });

  it("always has at least an octave of rows", () => {
    const one = makePiece({ bars: [{ notes: { T0: [[60, 0, 4]] } }], sections: [[[0, 0]]] });
    const l = new PianoRollLayout(new TimelineBuilder(one).build(), C_MAJOR, { pixelsPerSecond: 50, rowHeight: 8 });
    expect(l.highPitch - l.lowPitch).toBeGreaterThanOrEqual(12);
    expect(l.lowPitch).toBeLessThan(60);
    expect(l.highPitch).toBeGreaterThan(60);
    const empty = makePiece({ bars: [{ notes: {} }], sections: [[[0, 0]]] });
    expect(new PianoRollLayout(new TimelineBuilder(empty).build(), C_MAJOR, { pixelsPerSecond: 50, rowHeight: 8 }).rects).toEqual([]);
  });

  it("marks where the sections start", () => {
    expect(layout().sections).toEqual([
      { id: "s1", name: "S1", x: 0 },
      { id: "s2", name: "S2", x: 200 },
    ]);
  });

  it("converts between time and x", () => {
    const l = layout();
    expect(l.timeToX(2.5)).toBe(250);
    expect(l.xToTime(250)).toBe(2.5);
  });

  it("finds the notes in a scrolled window, including long ones that began before it", () => {
    const l = layout();
    const pitches = (x0: number, x1: number) => l.rectsBetween(x0, x1).map((r) => r.pitch).sort();
    expect(pitches(0, 50)).toEqual([48, 72]); // the bass note spans all of bar 1
    expect(pitches(150, 190)).toEqual([48, 74]);
    expect(pitches(250, 300)).toEqual([50, 76]); // bar 2; the first bass note ended at x = 199
    expect(pitches(1000, 1100)).toEqual([]);
    expect(pitches(0, 400)).toHaveLength(l.rects.length);
  });
});
