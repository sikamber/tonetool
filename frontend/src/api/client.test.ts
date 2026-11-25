import { describe, expect, it } from "vitest";
import { ApiError, isUnauthorized } from "./client";

describe("isUnauthorized", () => {
  it("is true only for a 401 from the server", () => {
    expect(isUnauthorized(new ApiError(401, ["login required"]))).toBe(true);
    expect(isUnauthorized(new ApiError(403, ["no"]))).toBe(false);
    expect(isUnauthorized(new ApiError(422, ["bad"]))).toBe(false);
    expect(isUnauthorized(new Error("401"))).toBe(false);
    expect(isUnauthorized(undefined)).toBe(false);
  });
});

describe("ApiError", () => {
  it("joins its messages into the error text", () => {
    const error = new ApiError(429, ["too many failed attempts", "try again in 60 seconds"]);
    expect(error.message).toBe("too many failed attempts; try again in 60 seconds");
    expect(error.status).toBe(429);
    expect(error.messages).toHaveLength(2);
  });
});
