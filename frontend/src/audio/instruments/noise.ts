const cache = new WeakMap<BaseAudioContext, AudioBuffer>();

const SECONDS = 1;

/** One second of white noise, the same every time (a fixed pseudo-random sequence), so exports are reproducible. */
function noiseBuffer(ctx: BaseAudioContext): AudioBuffer {
  let buffer = cache.get(ctx);
  if (!buffer) {
    buffer = ctx.createBuffer(1, Math.round(ctx.sampleRate * SECONDS), ctx.sampleRate);
    const data = buffer.getChannelData(0);
    let state = 123456789;
    for (let i = 0; i < data.length; i++) {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0; // a linear congruential generator
      data[i] = (state / 0xffffffff) * 2 - 1;
    }
    cache.set(ctx, buffer);
  }
  return buffer;
}

/**
 * A looping noise source that plays from `when` to `stopAt`. It starts at a point in the buffer
 * that depends on `when`, so notes do not all play the same noise.
 */
export function noiseSource(ctx: BaseAudioContext, when: number, stopAt: number): AudioBufferSourceNode {
  const source = ctx.createBufferSource();
  source.buffer = noiseBuffer(ctx);
  source.loop = true;
  source.start(when, (Math.abs(when) * 7919) % SECONDS);
  source.stop(stopAt);
  return source;
}
