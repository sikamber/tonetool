/**
 * What these tests can and cannot say: they run the real instrument code against a fake Web Audio
 * context (testing/graph.ts) and *model* the result: which nodes exist, when they start and stop,
 * and the steady-state spectrum and loudness of the graph. That catches clicks, leaks, instruments
 * of very different loudness, and a formant or decay that is not where it was meant to be. It cannot
 * say whether the result sounds good. That takes ears.
 */
import { describe, expect, it } from "vitest";
import { INSTRUMENTS, instrumentById, type NoteEvent } from "./index";
import { db, FakeContext, FakeGain, FakeParam, FakeSource, soundAt, type Sound } from "./testing/graph";

/** The modelled loudness (RMS) every instrument is calibrated to. */
const TARGET_RMS = 0.18;
const WHEN = 1;
const PITCHES = [45, 57, 69, 81];
const SUSTAINED = ["choir", "choir-aah", "strings", "organ", "flute"];

const play = (id: string, pitch: number, extra: Partial<NoteEvent> = {}): FakeContext => {
  const ctx = new FakeContext();
  instrumentById(id).play(ctx.asAudioContext(), ctx.asOutput(), { pitch, when: WHEN, duration: 2, attack: true, ...extra });
  return ctx;
};

/** Modelled loudness over the first 0.6 s after the attack (a piano decays, so this is an average). */
const loudness = (ctx: FakeContext): number => {
  const probes = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6];
  return Math.sqrt(probes.reduce((sum, p) => sum + soundAt(ctx, WHEN + p).rms ** 2, 0) / probes.length);
};

const f0 = (pitch: number) => 440 * 2 ** ((pitch - 69) / 12);

describe.each(INSTRUMENTS.map((i) => [i.id]))("%s", (id) => {
  it.each([[0.02], [0.3], [2]])("builds a clean graph for a %s s note", (duration) => {
    for (const pitch of [36, 60, 96]) {
      const ctx = play(id, pitch, { duration });
      const end = WHEN + duration;
      const sources = ctx.sources;
      expect(sources.length).toBeGreaterThan(0);
      for (const source of sources) {
        expect(source.startTime, "every source is started").not.toBeNull();
        expect(source.stopTime, "every source is stopped").not.toBeNull();
        expect(source.startTime!).toBeGreaterThanOrEqual(WHEN);
        // tones ring until the note is over; a piano's hammer noise is deliberately cut short
        if (source.kind === "oscillator") expect(source.stopTime!).toBeGreaterThan(end);
        else expect(source.stopTime!).toBeGreaterThan(source.startTime!);
        expect(source.stopTime!).toBeLessThanOrEqual(end + 1); // the release is short
      }
      const stop = Math.max(...sources.map((s) => s.stopTime!));
      expect(soundAt(ctx, WHEN).rms, "silent at the start").toBeLessThan(1e-9);
      expect(soundAt(ctx, stop - 1e-6).rms, "silent when the nodes are stopped, so no click").toBeLessThan(1e-3);
      for (const t of [WHEN + 0.01, WHEN + duration / 2, end, end + 0.05]) expect(Number.isFinite(soundAt(ctx, t).rms)).toBe(true);
    }
  });

  it("does not make many nodes for a note", () => {
    for (const pitch of [36, 60, 96]) expect(play(id, pitch).nodes.length).toBeLessThanOrEqual(32);
  });

  it.each(PITCHES)("is about as loud as the others at pitch %i", (pitch) => {
    const ratio = db(loudness(play(id, pitch)), TARGET_RMS);
    expect(Math.abs(ratio)).toBeLessThan(1.5);
  });

  it("is not silent or lost at the top of a soprano's range (C6)", () => {
    const high = db(loudness(play(id, 84)), TARGET_RMS);
    expect(high).toBeGreaterThan(-3);
    expect(high).toBeLessThan(3);
  });
});

describe("attacks", () => {
  it.each(SUSTAINED)("%s starts softly and does not click in", (id) => {
    const ctx = play(id, 60);
    expect(soundAt(ctx, WHEN + 0.002).rms).toBeLessThan(0.3 * soundAt(ctx, WHEN + 0.4).rms);
  });

  it.each(SUSTAINED)("%s joins a held note at once, without a re-strike", (id) => {
    const ctx = play(id, 60, { attack: false });
    expect(soundAt(ctx, WHEN + 0.006).rms).toBeGreaterThan(0.9 * soundAt(ctx, WHEN + 0.1).rms);
  });

  it("a piano note that joins a held one is quieter and has no hammer", () => {
    const struck = play("piano", 60);
    const joined = play("piano", 60, { attack: false });
    expect(struck.sources.some((s) => s.kind === "buffer")).toBe(true);
    expect(joined.sources.some((s) => s.kind === "buffer")).toBe(false);
    expect(soundAt(joined, WHEN + 0.05).rms).toBeLessThan(0.5 * soundAt(struck, WHEN + 0.05).rms);
  });
});

/** The vibrato oscillator of a note: it only drives parameters, and its depth is a gain. */
const vibratoOf = (ctx: FakeContext) => {
  for (const source of ctx.sources) {
    for (const out of source.outputs) {
      if (!(out instanceof FakeGain)) continue;
      const targets = [...out.outputs].filter((o): o is FakeParam => o instanceof FakeParam);
      if (targets.length > 0) return { hz: source.frequency.value, depth: out.gain, targets };
    }
  }
  return null;
};

describe("vibrato", () => {
  it.each(["choir", "choir-aah", "strings", "flute"])("%s has vibrato that sets in after a straight start", (id) => {
    const ctx = play(id, 60);
    const vibrato = vibratoOf(ctx)!;
    expect(vibrato).not.toBeNull();
    expect(vibrato.hz).toBeGreaterThan(4);
    expect(vibrato.hz).toBeLessThan(7);
    expect(vibrato.depth.valueAt(WHEN + 0.1)).toBe(0);
    const full = vibrato.depth.valueAt(WHEN + 1.2);
    expect(full).toBeGreaterThanOrEqual(8);
    expect(full).toBeLessThanOrEqual(20);
    // it modulates the pitch of every oscillator that makes the tone, and nothing else
    const tone = ctx.sources.filter((s) => s.kind === "oscillator" && s.outputs.size > 0 && ![...s.outputs].some((o) => o instanceof FakeGain && [...o.outputs].some((x) => x instanceof FakeParam)));
    expect(vibrato.targets.length).toBe(tone.length);
    for (const target of vibrato.targets) expect(target.owner).toBeInstanceOf(FakeSource);
  });

  it.each(["choir", "strings", "flute"])("%s vibrato is already under way when joining a held note", (id) => {
    const vibrato = vibratoOf(play(id, 60, { attack: false }))!;
    expect(vibrato.depth.valueAt(WHEN + 0.06)).toBeGreaterThanOrEqual(8);
  });

  it.each(["organ", "piano"])("%s has none", (id) => {
    expect(vibratoOf(play(id, 60))).toBeNull();
  });
});

const share = (sound: Sound, lo: number, hi: number) => sound.band(lo, hi) / sound.rms ** 2;

describe("choir", () => {
  it("ooh keeps its energy low, with almost nothing above 1.3 kHz", () => {
    for (const pitch of [48, 57]) {
      const sound = soundAt(play("choir", pitch), WHEN + 0.5);
      expect(share(sound, 150, 450)).toBeGreaterThan(0.5);
      expect(share(sound, 1300, 22050)).toBeLessThan(0.05);
    }
  });

  it("aah has several times more energy at 450-1300 Hz than ooh", () => {
    for (const pitch of [48, 57]) {
      const ooh = soundAt(play("choir", pitch), WHEN + 0.5);
      const aah = soundAt(play("choir-aah", pitch), WHEN + 0.5);
      expect(share(aah, 450, 1300)).toBeGreaterThan(2.5 * share(ooh, 450, 1300));
    }
  });

  it("puts a formant at the vowel's frequency (the first is where the filter is set)", () => {
    const frequencies = (id: string) =>
      play(id, 48).nodes.filter((n) => n.kind === "biquad").map((n) => (n as unknown as { frequency: FakeParam }).frequency.value);
    expect(frequencies("choir")).toEqual(expect.arrayContaining([300, 870, 2240]));
    expect(frequencies("choir-aah")).toEqual(expect.arrayContaining([730, 1090, 2440]));
  });

  it("lets the first formant follow a high note, so the vowel does not disappear", () => {
    const bandpass = (pitch: number) =>
      play("choir", pitch).nodes.filter((n) => n.kind === "biquad" && (n as unknown as { type: string }).type === "bandpass")
        .map((n) => (n as unknown as { frequency: FakeParam }).frequency.value);
    expect(bandpass(48)[0]).toBe(300);
    const high = bandpass(81); // 880 Hz, far above the ooh formant
    expect(high[0]).toBeGreaterThan(f0(81));
    expect([...high].sort((a, b) => a - b)).toEqual(high); // the formants stay in order
  });

  it("has only a little breath noise", () => {
    const sound = soundAt(play("choir", 57), WHEN + 0.5);
    expect(sound.noisePower / sound.rms ** 2).toBeLessThan(0.01);
    expect(sound.noisePower).toBeGreaterThan(0);
  });
});

describe("piano", () => {
  it("has partials that are slightly sharp of the harmonics", () => {
    const hz = play("piano", 57).sources.filter((s) => s.kind === "oscillator").map((s) => s.frequency.value).sort((a, b) => a - b);
    expect(Math.abs(hz[0]! - f0(57))).toBeLessThan(0.1); // the first partial is only a hair sharp
    hz.forEach((value, i) => {
      if (i === 0) return;
      expect(value).toBeGreaterThan((i + 1) * f0(57));
      expect(value).toBeLessThan((i + 1) * f0(57) * 1.03); // sharper the higher the partial, but only by a few percent
    });
  });

  it("lets the high partials die away much faster than the fundamental", () => {
    const ctx = play("piano", 57);
    const partial = (sound: Sound, n: number) => sound.lines.filter((l) => Math.abs(l.hz - n * f0(57)) < 30 + 3 * n).reduce((s, l) => s + l.power, 0);
    const ratio = (t: number) => {
      const sound = soundAt(ctx, WHEN + t);
      return partial(sound, 6) / partial(sound, 1);
    };
    expect(ratio(1.5)).toBeLessThan(0.1 * ratio(0.05));
  });

  it("rings longer in the bass than in the treble", () => {
    const kept = (pitch: number) => {
      const ctx = play("piano", pitch, { duration: 4 });
      return soundAt(ctx, WHEN + 2).rms / soundAt(ctx, WHEN + 0.1).rms;
    };
    expect(kept(36)).toBeGreaterThan(kept(84));
  });
});

describe("flute", () => {
  it("is nearly a pure tone with a little breath", () => {
    const sound = soundAt(play("flute", 69), WHEN + 0.6);
    const line = (n: number) => sound.lines.filter((l) => Math.abs(l.hz - n * 440) < 1).reduce((s, l) => s + l.power, 0);
    expect(line(1)).toBeGreaterThan(10 * line(2));
    expect(line(1)).toBeGreaterThan(100 * line(3));
    const noise = sound.noisePower / sound.rms ** 2;
    expect(noise).toBeGreaterThan(0.0005);
    expect(noise).toBeLessThan(0.05);
  });
});

describe("instrument list", () => {
  it("has unique ids and a default that exists", () => {
    const ids = INSTRUMENTS.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("choir");
    expect(() => instrumentById("kazoo")).toThrow(/no instrument/);
  });
});
