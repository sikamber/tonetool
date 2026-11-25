import { describe, expect, it } from "vitest";
import { PlaybackCursor } from "./cursor";
import { describeSection } from "./sections";
import { beatLength, Timeline, TimelineBuilder } from "./timeline";
import { makePiece, type BarSpec } from "./testPieces";

const whole = (pitch: number): BarSpec => ({ notes: { T0: [[pitch, 0, 4]] } });
const build = (piece: ReturnType<typeof makePiece>, scale = 1): Timeline => new TimelineBuilder(piece, scale).build();
const spanOf = (t: Timeline, pitch: number) =>
  t.notes.filter((n) => n.pitch === pitch).map((n) => [round(n.startSec), round(n.startSec + n.durationSec)]);
const round = (x: number) => Math.round(x * 1000) / 1000;

// bars 0-2 repeat with a 1st (bar 2) and 2nd (bar 3) ending, then bars 4-5: same shape as endings.musicxml
const endings = () =>
  makePiece({
    bars: [whole(60), whole(62), whole(64), whole(65), whole(67), whole(69)],
    sections: [[[0, 2]], [[0, 1], [3, 3]], [[4, 5]]],
  });

describe("unrolling", () => {
  it("plays sections in order with a source-measure map", () => {
    const t = build(endings()); // whole-note bars at 120 bpm = 2 s
    expect(t.spans.map((s) => s.sourceMeasure)).toEqual([0, 1, 2, 0, 1, 3, 4, 5]);
    expect(t.duration).toBeCloseTo(16);
    expect(t.spanAt(0).sourceMeasure).toBe(0);
    expect(t.spanAt(6.5).sourceMeasure).toBe(0); // second pass through bar 1
    expect(t.spanAt(15.9).sourceMeasure).toBe(5);
  });

  it("repeats notes with the right times", () => {
    const soprano = build(endings()).notesFor("T0");
    expect(soprano.map((n) => round(n.startSec))).toEqual([0, 2, 4, 6, 8, 10, 12, 14]);
    expect(soprano.map((n) => n.sourceMeasure)).toEqual([0, 1, 2, 0, 1, 3, 4, 5]);
  });

  it("tags spans and notes with sections and finds where sections start", () => {
    const t = build(endings());
    expect(t.sections.map((s) => [s.id, s.startSec, s.endSec])).toEqual([
      ["s1", 0, 6],
      ["s2", 6, 12],
      ["s3", 12, 16],
    ]);
    expect(t.sectionStart("s2")).toBe(6);
    expect(t.sectionAt(5.99).id).toBe("s1");
    expect(t.sectionAt(6).id).toBe("s2");
    expect(t.sectionAt(99).id).toBe("s3");
    expect(t.notes.filter((n) => n.sectionId === "s2").map((n) => n.pitch)).toEqual([60, 62, 65]);
    expect(() => t.sectionStart("nope")).toThrow(/have s1,s2,s3/);
  });

  it("scales time with the tempo", () => {
    const piece = endings();
    expect(build(piece, 0.5).duration).toBeCloseTo(32);
    expect(build(piece, 2).duration).toBeCloseTo(8);
    expect(() => new TimelineBuilder(piece, 0)).toThrow();
  });

  it("rejects segments outside the piece", () => {
    const piece = makePiece({ bars: [whole(60)], sections: [[[0, 3]]] });
    expect(() => build(piece)).toThrow(/outside/);
  });

  it("carries tempo marks forward in notated order", () => {
    const piece = makePiece({
      bars: [whole(60), { ...whole(62), tempo: 60 }, whole(64)],
      sections: [[[0, 0]], [[2, 2]]], // jumps over the bar with the mark; bar 2 still inherits 60
    });
    const t = build(piece);
    expect(t.spans.map((s) => s.endSec - s.startSec)).toEqual([2, 4]);
  });

  it("beats in dotted units in compound meters", () => {
    expect(beatLength({ beat_unit: 8, beats_per_bar: 6 })).toBe(1.5);
    expect(beatLength({ beat_unit: 8, beats_per_bar: 3 })).toBe(0.5);
    expect(beatLength({ beat_unit: 4, beats_per_bar: 4 })).toBe(1);
  });
});

describe("ties", () => {
  // bar = 2 s at 120 bpm, quarter = 0.5 s
  const bars: BarSpec[] = [
    { notes: { T0: [[72, 0, 2], [76, 2, 2, false]] } },
    { notes: { T0: [[76, 0, 4, true]] } },
    { notes: { T0: [[76, 0, 4, true]] } },
  ];

  it("extends a held note through every link of a chain", () => {
    const piece = makePiece({ bars, sections: [[[0, 2]]] });
    const t = build(piece);
    expect(spanOf(t, 76)).toEqual([[1, 6]]);
    expect(t.notes.filter((n) => n.pitch === 76).map((n) => n.attack)).toEqual([true]);
  });

  it("stops where a jump breaks the chain, entering without attack", () => {
    // bar 3 sounds in between, so the tied 76 in bar 2 has nothing to continue
    const piece = makePiece({ bars: [...bars, whole(60)], sections: [[[0, 0]], [[3, 3]], [[2, 2]]] });
    const t = build(piece);
    expect(spanOf(t, 76)).toEqual([[1, 2], [4, 6]]);
    expect(t.notes.filter((n) => n.pitch === 76).map((n) => n.attack)).toEqual([true, false]);
  });

  it("continues through a jump that is contiguous in time", () => {
    const piece = makePiece({ bars, sections: [[[0, 0]], [[2, 2]]] });
    expect(spanOf(build(piece), 76)).toEqual([[1, 4]]);
  });

  it("continues across a section boundary", () => {
    const piece = makePiece({ bars, sections: [[[0, 0]], [[1, 2]]] });
    expect(spanOf(build(piece), 76)).toEqual([[1, 6]]);
  });
});

describe("PlaybackCursor", () => {
  const piece = makePiece({
    bars: [{ notes: { T0: [[60, 0, 2], [62, 2, 2]] } }, { notes: { T0: [[64, 0, 4]] } }],
    sections: [[[0, 1]]],
  });
  const timeline = build(piece); // 60: 0-1s, 62: 1-2s, 64: 2-4s

  it("hands out each note once, in order", () => {
    const cursor = new PlaybackCursor(timeline, 0);
    expect(cursor.takeHeld()).toEqual([]);
    expect(cursor.takeUntil(1.5).map((n) => n.pitch)).toEqual([60, 62]);
    expect(cursor.takeUntil(1.5)).toEqual([]);
    expect(cursor.takeUntil(10).map((n) => n.pitch)).toEqual([64]);
  });

  it("joins notes that are already sounding, without attack and cut to the remainder", () => {
    const cursor = new PlaybackCursor(timeline, 3);
    const held = cursor.takeHeld();
    expect(held.map((n) => [n.pitch, n.startSec, n.durationSec, n.attack])).toEqual([[64, 3, 1, false]]);
    expect(cursor.takeHeld()).toEqual([]);
    expect(cursor.takeUntil(10)).toEqual([]);
  });

  it("starts exactly on a note boundary with that note attacking", () => {
    const cursor = new PlaybackCursor(timeline, 1);
    expect(cursor.takeHeld()).toEqual([]);
    expect(cursor.takeUntil(1.1).map((n) => [n.pitch, n.attack])).toEqual([[62, true]]);
  });
});

describe("describeSection", () => {
  it("uses printed bar numbers", () => {
    const piece = endings();
    expect(describeSection(piece, piece.sections[1]!)).toBe("1-2, 4");
  });
});
