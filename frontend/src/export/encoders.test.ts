import { describe, expect, it } from "vitest";
import { encodeMp3, encodeWav, limitPeak, type Pcm } from "./encoders";

const sine = (seconds: number, amplitude = 0.5, sampleRate = 44100): Pcm => {
  const left = Float32Array.from({ length: Math.round(seconds * sampleRate) }, (_, i) =>
    amplitude * Math.sin((2 * Math.PI * 440 * i) / sampleRate),
  );
  return { sampleRate, channels: [left, left.map((x) => -x)] };
};

describe("limitPeak", () => {
  it("scales down loud audio to the ceiling", () => {
    const pcm: Pcm = { sampleRate: 1, channels: [Float32Array.of(2, -1), Float32Array.of(0.5, 0)] };
    limitPeak(pcm, 0.95);
    expect(pcm.channels[0]![0]).toBeCloseTo(0.95);
    expect(pcm.channels[0]![1]).toBeCloseTo(-0.475);
    expect(pcm.channels[1]![0]).toBeCloseTo(0.2375);
  });

  it("never boosts quiet audio", () => {
    const pcm: Pcm = { sampleRate: 1, channels: [Float32Array.of(0.1, -0.2)] };
    limitPeak(pcm);
    expect(Array.from(pcm.channels[0]!)).toEqual([expect.closeTo(0.1), expect.closeTo(-0.2)]);
  });
});

describe("encodeWav", () => {
  it("writes a valid 16-bit stereo header and interleaved samples", () => {
    const bytes = encodeWav({ sampleRate: 44100, channels: [Float32Array.of(1, 0), Float32Array.of(-1, 0.5)] });
    const view = new DataView(bytes.buffer);
    const text = (at: number) => String.fromCharCode(...bytes.slice(at, at + 4));
    expect([text(0), text(8), text(12), text(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(view.getUint16(22, true)).toBe(2); // channels
    expect(view.getUint32(24, true)).toBe(44100);
    expect(view.getUint32(40, true)).toBe(8); // 2 frames * 2 channels * 2 bytes
    expect(bytes.length).toBe(44 + 8);
    expect([44, 46, 48, 50].map((at) => view.getInt16(at, true))).toEqual([32767, -32767, 0, 16384]);
  });
});

describe("encodeMp3", () => {
  it("produces MP3 frames of roughly the expected size", async () => {
    const bytes = await encodeMp3(sine(2), 128);
    expect(bytes[0]).toBe(0xff);
    expect(bytes[1]! & 0xe0).toBe(0xe0); // frame sync
    const expected = (128_000 / 8) * 2; // bitrate * seconds
    expect(bytes.length).toBeGreaterThan(expected * 0.8);
    expect(bytes.length).toBeLessThan(expected * 1.2);
  });
});
