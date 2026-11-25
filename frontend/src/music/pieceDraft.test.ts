import { describe, expect, it } from "vitest";
import { errorMessages } from "../api/client";
import { formatRanges, parseRanges, PieceDraft } from "./pieceDraft";
import { makePiece } from "./testPieces";

// six bars, two sections: A = bars 1-3, B = bars 4-6; bars 1-3 carry lyric lines 1 and 2, bars 4-6 line 1
const piece = () =>
  makePiece({
    tracks: ["T0", "T1"],
    bars: Array.from({ length: 6 }, (_, i) => ({
      notes: { T0: [[60, 0, 4, false, i < 3 ? [["1", "a"], ["2", "b"]] : [["1", "c"]]]] },
    })),
    sections: [[[0, 2]], [[3, 5]]],
  });

describe("parseRanges", () => {
  it("reads ranges and single bars, counting from 1", () => {
    expect(parseRanges("1-12, 15", 24)).toEqual({ ok: true, segments: [{ start: 0, end: 11 }, { start: 14, end: 14 }] });
    expect(parseRanges(" 3 ", 6)).toEqual({ ok: true, segments: [{ start: 2, end: 2 }] });
    expect(parseRanges("1 - 2;4", 6)).toEqual({ ok: true, segments: [{ start: 0, end: 1 }, { start: 3, end: 3 }] });
  });

  it.each([
    ["", /at least one/],
    ["abc", /not a bar/],
    ["0-3", /start at 1/],
    ["5-3", /backwards/],
    ["2-9", /past the last bar \(6\)/],
    ["1-", /not a bar/],
  ])("rejects %j", (text, message) => {
    const result = parseRanges(text, 6);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(message);
  });

  it("round-trips through formatRanges", () => {
    const segments = [{ start: 0, end: 11 }, { start: 14, end: 14 }];
    expect(formatRanges(segments)).toBe("1-12, 15");
    expect(parseRanges(formatRanges(segments), 24)).toEqual({ ok: true, segments });
  });
});

describe("PieceDraft", () => {
  it("starts clean and is not changed by operations (immutable)", () => {
    const original = piece();
    const draft = PieceDraft.from(original);
    draft.setTitle("x").addSection().removeSection("s1");
    expect(draft.dirty).toBe(false);
    expect(draft.piece).toBe(original);
  });

  it("edits the title and tracks, and is clean again when changed back", () => {
    const draft = PieceDraft.from(piece());
    const edited = draft.setTitle("Ny titel").setTrack("T1", { label: "Alt 1", voice: "A" });
    expect(edited.dirty).toBe(true);
    expect(edited.toEdits().title).toBe("Ny titel");
    expect(edited.toEdits().tracks).toEqual([
      { id: "T0", label: "T0", voice: "other" },
      { id: "T1", label: "Alt 1", voice: "A" },
    ]);
    expect(edited.setTitle("Test").setTrack("T1", { label: "T1", voice: "other" }).dirty).toBe(false);
  });

  it("adds a section over the whole piece with a free id", () => {
    const added = PieceDraft.from(piece()).addSection();
    const section = added.piece.sections.at(-1)!;
    expect(section).toMatchObject({ id: "s3", segments: [{ start: 0, end: 5 }], lyric_number: null });
    expect(new Set(added.piece.sections.map((s) => s.id)).size).toBe(3);
    // an id that is already taken is skipped
    const crowded = PieceDraft.from(piece()).renameSection("s2", "B");
    crowded.piece.sections[1]!.id = "s3";
    expect(crowded.addSection().piece.sections.at(-1)!.id).toBe("s4");
  });

  it("removes sections but never the last one", () => {
    const draft = PieceDraft.from(piece());
    const one = draft.removeSection("s1");
    expect(one.piece.sections.map((s) => s.id)).toEqual(["s2"]);
    expect(one.removeSection("s2")).toBe(one);
  });

  it("moves sections within the order", () => {
    const draft = PieceDraft.from(piece());
    expect(draft.moveSection("s2", -1).piece.sections.map((s) => s.id)).toEqual(["s2", "s1"]);
    expect(draft.moveSection("s1", -1)).toBe(draft);
    expect(draft.moveSection("s2", 1)).toBe(draft);
    expect(draft.moveSection("nope", 1)).toBe(draft);
    expect(draft.moveSection("s2", -1).dirty).toBe(true);
  });

  it("changes name, bars and lyric line of one section", () => {
    const edited = PieceDraft.from(piece())
      .renameSection("s1", "Vers 1")
      .setSegments("s1", [{ start: 0, end: 1 }])
      .setLyricNumber("s2", "1");
    expect(edited.piece.sections.map((s) => [s.name, s.segments, s.lyric_number ?? null])).toEqual([
      ["Vers 1", [{ start: 0, end: 1 }], null],
      ["S2", [{ start: 3, end: 5 }], "1"],
    ]);
  });

  it("lists the lyric lines present in a section's bars", () => {
    const draft = PieceDraft.from(piece());
    expect(draft.availableLyricNumbers("s1")).toEqual(["1", "2"]);
    expect(draft.availableLyricNumbers("s2")).toEqual(["1"]);
    expect(draft.setSegments("s1", [{ start: 0, end: 5 }]).availableLyricNumbers("s1")).toEqual(["1", "2"]);
    expect(draft.availableLyricNumbers("nope")).toEqual([]);
  });

  it("reverts, and rebases on what the server saved", () => {
    const draft = PieceDraft.from(piece()).setTitle("x");
    expect(draft.revert().dirty).toBe(false);
    expect(draft.revert().piece.title).toBe("Test");
    const saved = { ...draft.piece };
    const rebased = draft.savedAs(saved);
    expect(rebased.dirty).toBe(false);
    expect(rebased.revert().piece.title).toBe("x");
  });
});

describe("errorMessages", () => {
  it("passes a plain message through", () => {
    expect(errorMessages("segment 0-99 outside 0-5", "fallback")).toEqual(["segment 0-99 outside 0-5"]);
  });

  it("flattens request-validation errors", () => {
    const detail = [
      { loc: ["body", "title"], msg: "String should have at least 1 character", type: "string_too_short" },
      { loc: ["body", "sections", 0, "segments"], msg: "Value error, segment start 3 > end 1" },
    ];
    expect(errorMessages(detail, "fallback")).toEqual([
      "title: String should have at least 1 character",
      "sections.0.segments: segment start 3 > end 1",
    ]);
  });

  it("falls back when there is nothing to show", () => {
    expect(errorMessages(undefined, "500 Internal Server Error")).toEqual(["500 Internal Server Error"]);
    expect(errorMessages([], "x")).toEqual(["x"]);
  });
});
