import { describe, expect, it } from "vitest";
import { keyLabel, TONICS, tonicPitchClass } from "./key";

describe("tonicPitchClass", () => {
  it("reads naturals, sharps and flats", () => {
    expect(TONICS.map(tonicPitchClass)).toEqual([0, 1, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11]);
  });

  it("wraps around the octave", () => {
    expect(tonicPitchClass("Cb")).toBe(11);
    expect(tonicPitchClass("B#")).toBe(0);
  });

  it.each(["H", "c", "", "C##", "Bbb", "Cx"])("rejects %j", (tonic) => {
    expect(() => tonicPitchClass(tonic)).toThrow(/not a tonic/);
  });
});

describe("keyLabel", () => {
  it("names the key or says there is none", () => {
    expect(keyLabel({ tonic: "Bb", mode: "major" })).toBe("Bb major");
    expect(keyLabel({ tonic: "F#", mode: "minor" })).toBe("F# minor");
    expect(keyLabel(null)).toBe("no key");
    expect(keyLabel(undefined)).toBe("no key");
  });
});
