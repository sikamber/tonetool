import { describe, expect, it } from "vitest";
import { hashForPieceId, pieceIdFromHash } from "./pieceHash";

describe("piece hash", () => {
  it("decodes ids with Danish characters", () => {
    expect(pieceIdFromHash("#Juletr%C3%A6et")).toBe("Juletræet");
    expect(pieceIdFromHash("#bl%C3%A5b%C3%A6r-p%C3%A5-%C3%A6r%C3%B8")).toBe("blåbær-på-ærø");
  });

  it("round-trips", () => {
    for (const id of ["simple", "Juletræet", "blåbær-på-ærø"]) {
      expect(pieceIdFromHash(hashForPieceId(id))).toBe(id);
    }
  });

  it("treats an empty or malformed hash as no selection", () => {
    expect(pieceIdFromHash("")).toBeNull();
    expect(pieceIdFromHash("#")).toBeNull();
    expect(pieceIdFromHash("#%E0%A4%A")).toBeNull();
  });
});
