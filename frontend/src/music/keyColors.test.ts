import { describe, expect, it } from "vitest";
import { KeyColors } from "./keyColors";

const C_MAJOR = new KeyColors({ tonic: "C", mode: "major" });
const hueOf = (colors: KeyColors, pitch: number) => colors.colorOf(pitch).hue;

describe("KeyColors", () => {
  it("runs from red do to purple ti through the major scale", () => {
    const scale = [60, 62, 64, 65, 67, 69, 71].map((p) => C_MAJOR.colorOf(p));
    expect(scale.map((c) => c.syllable)).toEqual(["do", "re", "mi", "fa", "sol", "la", "ti"]);
    expect(scale[0]!.hue).toBe(0); // red
    expect(scale[6]!.hue).toBe(280); // purple
    const hues = scale.map((c) => c.hue);
    expect(hues).toEqual([...hues].sort((a, b) => a - b)); // hues only go up the rainbow
    expect(new Set(hues).size).toBe(7);
    expect(scale.every((c) => c.inKey)).toBe(true);
  });

  it("gives the same note the same colour in every octave", () => {
    for (const pitch of [36, 48, 60, 72, 84]) expect(C_MAJOR.colorOf(pitch)).toEqual(C_MAJOR.colorOf(pitch + 12));
    expect(C_MAJOR.colorOf(0).syllable).toBe("do");
    expect(C_MAJOR.colorOf(127).syllable).toBe("sol"); // 127 = G9
  });

  it("is relative to the tonic: do is red in every key", () => {
    const dMajor = new KeyColors({ tonic: "D", mode: "major" });
    expect(dMajor.colorOf(62).syllable).toBe("do");
    expect(dMajor.colorOf(62).hue).toBe(0);
    expect(dMajor.colorOf(66).syllable).toBe("mi"); // F#
    expect(dMajor.colorOf(73).syllable).toBe("ti"); // C#
    const bFlat = new KeyColors({ tonic: "Bb", mode: "major" });
    expect(bFlat.colorOf(58).syllable).toBe("do");
    expect(bFlat.colorOf(69).syllable).toBe("ti"); // A
  });

  it("colours major and minor keys alike (do-based): only what counts as in the key differs", () => {
    const cMinor = new KeyColors({ tonic: "C", mode: "minor" });
    for (let pitch = 60; pitch < 72; pitch++) {
      const { inKey: _a, ...major } = C_MAJOR.colorOf(pitch);
      const { inKey: _b, ...minor } = cMinor.colorOf(pitch);
      expect(minor).toEqual(major);
    }
    expect(C_MAJOR.colorOf(63).inKey).toBe(false); // Eb is not in C major
    expect(cMinor.colorOf(63).inKey).toBe(true);
    expect(cMinor.colorOf(64).inKey).toBe(false); // E natural is not in C minor
  });

  it("makes a lowered step the same hue as the plain step but darker (me vs mi)", () => {
    const mi = C_MAJOR.colorOf(64);
    const me = C_MAJOR.colorOf(63);
    expect(me.syllable).toBe("me");
    expect(me.hue).toBe(mi.hue);
    expect(me.lightness).toBeLessThan(mi.lightness);
    for (const [lowered, plain] of [[61, 62], [68, 69], [70, 71]] as const) {
      expect(hueOf(C_MAJOR, lowered)).toBe(hueOf(C_MAJOR, plain)); // ra/re, le/la, te/ti
      expect(C_MAJOR.colorOf(lowered).lightness).toBeLessThan(C_MAJOR.colorOf(plain).lightness);
    }
  });

  it("makes the raised fi brighter than fa, in the same hue", () => {
    const fa = C_MAJOR.colorOf(65);
    const fi = C_MAJOR.colorOf(66);
    expect(fi.syllable).toBe("fi");
    expect(fi.hue).toBe(fa.hue);
    expect(fi.lightness).toBeGreaterThan(fa.lightness);
  });

  it("outlines only the notes outside the key's scale", () => {
    const chromatic = [61, 63, 66, 68, 70];
    expect(chromatic.map((p) => C_MAJOR.colorOf(p).inKey)).toEqual([false, false, false, false, false]);
  });

  it("is neutral without a key", () => {
    const none = new KeyColors(null);
    expect(none.hasKey).toBe(false);
    expect(none.colorOf(60)).toEqual(none.colorOf(61));
    expect(none.colorOf(60).syllable).toBe("");
    expect(new KeyColors(undefined).hasKey).toBe(false);
  });

  it("has a legend with a colour for each of the twelve steps", () => {
    const legend = KeyColors.legend();
    expect(legend.map((c) => c.syllable)).toEqual(["do", "ra", "re", "me", "mi", "fa", "fi", "sol", "le", "la", "te", "ti"]);
    expect(legend.map((c) => c.css)).toEqual([60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71].map((p) => C_MAJOR.colorOf(p).css));
    expect(legend[0]!.css).toMatch(/^hsl\(0 /); // red
  });
});
