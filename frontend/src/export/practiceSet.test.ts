import { describe, expect, it } from "vitest";
import type { Piece } from "../api/types";
import type { VoiceSettings } from "../audio/voiceChannel";
import { makePiece } from "../music/testPieces";
import { PracticeSet, slug } from "./practiceSet";

const voicesFor = (piece: Piece, instrumentId = "choir"): VoiceSettings[] =>
  piece.tracks.map((t) => ({ trackId: t.id, volume: 0.4, pan: 0.3, muted: true, instrumentId }));

const choir = (labels: string[], title = "Test"): Piece => {
  const piece = makePiece({ tracks: labels.map((_, i) => `T${i}`), bars: [{ notes: {} }], sections: [[[0, 0]]] });
  piece.title = title;
  piece.tracks.forEach((t, i) => (t.label = labels[i]!));
  return piece;
};

const byName = (set: PracticeSet) => Object.fromEntries(set.files().map((f) => [f.name, f]));

describe("slug", () => {
  it("keeps Danish letters and collapses the rest", () => {
    expect(slug("Blåbær på Ærø!")).toBe("Blåbær_på_Ærø");
    expect(slug("  ?! ")).toBe("");
  });
});

describe("PracticeSet", () => {
  it("makes a tutti plus solo/prominent/stereo for every voice, named after piece and voice", () => {
    const piece = choir(["Sopran", "Alt", "Tenor", "Bas"], "Sønderjysk sang");
    const files = new PracticeSet(piece, voicesFor(piece)).files();
    expect(files).toHaveLength(1 + 4 * 3);
    expect(files[0]!.name).toBe("Sønderjysk_sang_tutti");
    expect(files.map((f) => f.name)).toContain("Sønderjysk_sang_Alt_prominent");
  });

  it("gives a single voice only the tutti", () => {
    const piece = choir(["Solo"]);
    expect(new PracticeSet(piece, voicesFor(piece)).files().map((f) => f.kind)).toEqual(["tutti"]);
  });

  it("tutti resets the mixer but keeps instruments", () => {
    const piece = choir(["S", "A"]);
    const tutti = new PracticeSet(piece, voicesFor(piece, "organ")).files()[0]!;
    expect(tutti.voices).toEqual(
      piece.tracks.map((t) => ({ trackId: t.id, volume: 1, pan: 0, muted: false, instrumentId: "organ" })),
    );
  });

  it("solo mutes everyone else", () => {
    const piece = choir(["S", "A", "T"]);
    const solo = byName(new PracticeSet(piece, voicesFor(piece)))["Test_A_solo"]!;
    expect(solo.voices.map((v) => [v.trackId, v.muted])).toEqual([["T0", true], ["T1", false], ["T2", true]]);
  });

  it("prominent scales the others so together they sit at othersVolume", () => {
    const piece = choir(["S", "A", "T", "B"]);
    const file = byName(new PracticeSet(piece, voicesFor(piece), 0.3))["Test_S_prominent"]!;
    const [featured, ...others] = file.voices;
    expect(featured!.volume).toBe(1);
    const each = 0.3 / Math.sqrt(3);
    others.forEach((v) => expect(v.volume).toBeCloseTo(each));
    // incoherent sum of the others' levels equals othersVolume
    expect(Math.sqrt(others.reduce((sum, v) => sum + v.volume ** 2, 0))).toBeCloseTo(0.3);
  });

  it("stereo puts the voice hard left and the others hard right, balanced", () => {
    const piece = choir(["S", "A", "T", "B"]);
    const file = byName(new PracticeSet(piece, voicesFor(piece)))["Test_T_stereo"]!;
    const [featured, others] = [file.voices[2]!, file.voices.filter((_, i) => i !== 2)];
    expect([featured.pan, featured.volume]).toEqual([-1, 1]);
    others.forEach((v) => expect([v.pan, v.volume]).toEqual([1, 1 / Math.sqrt(3)]));
  });

  it("adds the track id when two labels collide", () => {
    const piece = choir(["Alt", "Alt"]);
    const names = new PracticeSet(piece, voicesFor(piece)).files().map((f) => f.name);
    expect(names).toContain("Test_Alt_T0_solo");
    expect(names).toContain("Test_Alt_T1_solo");
  });

  it("rejects a negative background volume", () => {
    const piece = choir(["S", "A"]);
    expect(() => new PracticeSet(piece, voicesFor(piece), -1)).toThrow();
  });
});
