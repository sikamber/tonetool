/**
 * Test-only: a fake Web Audio context that records the graph an instrument builds, and an
 * analytic estimate of what that graph sounds like.
 *
 * Real audio cannot be rendered where there is no audio backend, and rendering would not say
 * whether anything sounds *good* anyway. What can be checked is the design: that the graph is
 * clean (everything started is stopped, the tail is silent), that the instruments are equally
 * loud, and that the spectrum has the intended shape (formants, decaying partials). The estimate
 * sums the power of each spectral line through the gains and biquad filters on its way to the
 * output, using the Web Audio specification's own filter formulas. It ignores vibrato.
 */

type EventKind = "set" | "ramp" | "target";

interface ParamEvent {
  kind: EventKind;
  time: number;
  value: number;
  timeConstant: number;
}

export class FakeParam {
  readonly events: ParamEvent[] = [];

  constructor(
    readonly owner: FakeNode,
    public value: number,
  ) {}

  setValueAtTime(value: number, time: number): this {
    return this.add({ kind: "set", time, value, timeConstant: 0 });
  }

  linearRampToValueAtTime(value: number, time: number): this {
    return this.add({ kind: "ramp", time, value, timeConstant: 0 });
  }

  setTargetAtTime(value: number, time: number, timeConstant: number): this {
    return this.add({ kind: "target", time, value, timeConstant });
  }

  /** The value at `t`: the automation timeline evaluated like a browser would. */
  valueAt(t: number): number {
    let held = this.value;
    let target: { t0: number; v0: number; goal: number; tc: number } | null = null;
    let last = 0;
    const inMode = (time: number): number =>
      target ? target.goal + (target.v0 - target.goal) * Math.exp(-(time - target.t0) / target.tc) : held;
    for (const event of this.events) {
      if (event.kind === "ramp") {
        const from = inMode(last);
        if (t <= event.time) return event.time === last ? event.value : from + ((event.value - from) * (t - last)) / (event.time - last);
        held = event.value;
        target = null;
        last = event.time;
      } else {
        if (t < event.time) return inMode(t);
        if (event.kind === "set") {
          held = event.value;
          target = null;
        } else {
          target = { t0: event.time, v0: inMode(event.time), goal: event.value, tc: event.timeConstant };
        }
        last = event.time;
      }
    }
    return inMode(t);
  }

  private add(event: ParamEvent): this {
    this.events.push(event);
    this.events.sort((a, b) => a.time - b.time); // stable: equal times keep their order
    return this;
  }
}

export class FakeNode {
  readonly outputs = new Set<FakeNode | FakeParam>();
  onended: (() => void) | null = null;

  constructor(readonly kind: string) {}

  connect<T extends FakeNode | FakeParam>(destination: T): T {
    this.outputs.add(destination);
    return destination;
  }

  disconnect(): void {
    this.outputs.clear();
  }
}

export class FakeGain extends FakeNode {
  readonly gain = new FakeParam(this, 1);
  constructor() {
    super("gain");
  }
}

export class FakeBiquad extends FakeNode {
  type: "lowpass" | "highpass" | "bandpass" = "lowpass";
  readonly frequency = new FakeParam(this, 350);
  readonly Q = new FakeParam(this, 1);
  constructor() {
    super("biquad");
  }
}

export class FakeSource extends FakeNode {
  type: "sine" | "sawtooth" = "sine";
  loop = false;
  buffer: FakeBuffer | null = null;
  readonly frequency = new FakeParam(this, 440);
  readonly detune = new FakeParam(this, 0);
  startTime: number | null = null;
  stopTime: number | null = null;
  constructor(kind: "oscillator" | "buffer") {
    super(kind);
  }
  start(when: number): void {
    this.startTime = when;
  }
  stop(when: number): void {
    this.stopTime = when;
  }
}

export class FakeBuffer {
  private readonly data: Float32Array;
  constructor(readonly length: number, readonly sampleRate: number) {
    this.data = new Float32Array(length);
  }
  getChannelData(): Float32Array {
    return this.data;
  }
}

export class FakeContext {
  readonly sampleRate = 44100;
  readonly destination = new FakeNode("destination");
  readonly nodes: FakeNode[] = [];

  private track<T extends FakeNode>(node: T): T {
    this.nodes.push(node);
    return node;
  }
  createGain = () => this.track(new FakeGain());
  createBiquadFilter = () => this.track(new FakeBiquad());
  createOscillator = () => this.track(new FakeSource("oscillator"));
  createBufferSource = () => this.track(new FakeSource("buffer"));
  createBuffer = (_channels: number, length: number, sampleRate: number) => new FakeBuffer(length, sampleRate);

  get sources(): FakeSource[] {
    return this.nodes.filter((n): n is FakeSource => n instanceof FakeSource);
  }

  /** Cast for passing to code that expects the DOM types. */
  asAudioContext(): BaseAudioContext {
    return this as unknown as BaseAudioContext;
  }

  asOutput(): AudioNode {
    return this.destination as unknown as AudioNode;
  }
}

/** |H| of a biquad at `hz`, from the formulas in the Web Audio specification. */
export function biquadMagnitude(type: FakeBiquad["type"], frequency: number, q: number, hz: number, sampleRate: number): number {
  const w0 = (2 * Math.PI * frequency) / sampleRate;
  const cos = Math.cos(w0);
  const sin = Math.sin(w0);
  // for low/high-pass Q is in dB, for band-pass it is a plain ratio
  const alpha = type === "bandpass" ? sin / (2 * q) : sin / (2 * 10 ** (q / 20));
  let b: [number, number, number];
  if (type === "lowpass") b = [(1 - cos) / 2, 1 - cos, (1 - cos) / 2];
  else if (type === "highpass") b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2];
  else b = [alpha, 0, -alpha];
  const a: [number, number, number] = [1 + alpha, -2 * cos, 1 - alpha];
  const w = (2 * Math.PI * hz) / sampleRate;
  const magnitude = (c: [number, number, number]) =>
    Math.hypot(c[0] + c[1] * Math.cos(w) + c[2] * Math.cos(2 * w), -(c[1] * Math.sin(w) + c[2] * Math.sin(2 * w)));
  return magnitude(b) / magnitude(a);
}

export interface SpectralLine {
  hz: number;
  power: number;
}

export interface Sound {
  lines: SpectralLine[];
  /** Power of the noise (broadband, so not a line). */
  noisePower: number;
  /** Power inside a band: lines whose frequency is within it. */
  band(lo: number, hi: number): number;
  rms: number;
}

/** What the graph sounds like at time `t` (steady state; vibrato ignored). */
export function soundAt(ctx: FakeContext, t: number): Sound {
  const nyquist = ctx.sampleRate / 2;
  const lines: SpectralLine[] = [];
  let noisePower = 0;
  const grid = Array.from({ length: Math.floor(nyquist / 25) }, (_, i) => (i + 1) * 25);

  for (const source of ctx.sources) {
    if (source.startTime === null || t < source.startTime || (source.stopTime !== null && t >= source.stopTime)) continue;
    const paths = pathsToDestination(source, ctx.destination);
    if (paths.length === 0) continue; // e.g. a vibrato oscillator: it only drives parameters

    const response = (path: FakeNode[], hz: number): number =>
      path.reduce((gain, node) => {
        if (node instanceof FakeGain) return gain * node.gain.valueAt(t);
        if (node instanceof FakeBiquad) {
          return gain * biquadMagnitude(node.type, node.frequency.valueAt(t), node.Q.valueAt(t), hz, ctx.sampleRate);
        }
        return gain;
      }, 1);

    if (source.kind === "buffer") {
      const data = source.buffer!.getChannelData();
      const variance = data.reduce((sum, x) => sum + x * x, 0) / data.length;
      for (const path of paths) {
        const meanSquare = grid.reduce((sum, hz) => sum + response(path, hz) ** 2, 0) / grid.length;
        noisePower += variance * meanSquare;
      }
      continue;
    }

    const f0 = source.frequency.valueAt(t) * 2 ** (source.detune.value / 1200);
    const harmonics = source.type === "sawtooth" ? Math.floor(nyquist / f0) : 1;
    for (let n = 1; n <= harmonics; n++) {
      const amplitude = source.type === "sawtooth" ? 2 / (Math.PI * n) : 1;
      for (const path of paths) {
        const hz = n * f0;
        lines.push({ hz, power: (amplitude * response(path, hz)) ** 2 / 2 });
      }
    }
  }

  const linePower = lines.reduce((sum, l) => sum + l.power, 0);
  return {
    lines,
    noisePower,
    band: (lo, hi) => lines.filter((l) => l.hz >= lo && l.hz < hi).reduce((sum, l) => sum + l.power, 0),
    rms: Math.sqrt(linePower + noisePower),
  };
}

/** Every route from `from` to `to` through nodes (not through parameters: those carry modulation). */
function pathsToDestination(from: FakeNode, to: FakeNode, seen: FakeNode[] = []): FakeNode[][] {
  if (seen.includes(from)) return [];
  const here = [...seen, from];
  const paths: FakeNode[][] = [];
  for (const next of from.outputs) {
    if (!(next instanceof FakeNode)) continue;
    if (next === to) paths.push(here);
    else paths.push(...pathsToDestination(next, to, here));
  }
  return paths;
}

/** The decibel ratio of two amplitudes. */
export const db = (a: number, b: number): number => 20 * Math.log10(a / b);
