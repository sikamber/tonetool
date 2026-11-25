import { describe, expect, it } from "vitest";
import { PracticeSet } from "../export/practiceSet";
import { makePiece } from "../music/testPieces";
import { instrumentById } from "./instruments";
import { defaultVoices } from "./voiceChannel";

const piece = () => makePiece({ tracks: ["T0", "T1", "T2"], bars: [{ notes: {} }], sections: [[[0, 0]]] });

describe("defaultVoices", () => {
  it("starts every voice at full volume, centred, unmuted, on the piano", () => {
    expect(defaultVoices(piece())).toEqual(
      ["T0", "T1", "T2"].map((trackId) => ({ trackId, volume: 1, pan: 0, muted: false, instrumentId: "piano" })),
    );
    expect(() => instrumentById(defaultVoices(piece())[0]!.instrumentId)).not.toThrow();
  });

  it("is what the practice-set export plays: every file is on the piano", () => {
    const files = new PracticeSet(piece(), defaultVoices(piece())).files();
    expect(files.length).toBeGreaterThan(1);
    for (const file of files) for (const voice of file.voices) expect(voice.instrumentId).toBe("piano");
  });
});
