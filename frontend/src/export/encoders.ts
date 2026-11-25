import { Mp3Encoder } from "@breezystack/lamejs";

export type AudioFormat = "mp3" | "wav";

/** Decoded stereo audio: one Float32Array per channel. */
export interface Pcm {
  sampleRate: number;
  channels: Float32Array[];
}

/** Largest sample the exports may reach (matches the Python renderer). */
export const PEAK_CEILING = 0.95;

/** Scale the audio down if it exceeds `ceiling`. Never boosts, so relative levels between files hold. */
export function limitPeak(pcm: Pcm, ceiling = PEAK_CEILING): void {
  let peak = 0;
  for (const channel of pcm.channels) for (const sample of channel) peak = Math.max(peak, Math.abs(sample));
  if (peak <= ceiling) return;
  const gain = ceiling / peak;
  for (const channel of pcm.channels) for (let i = 0; i < channel.length; i++) channel[i]! *= gain;
}

function toInt16(samples: Float32Array, from = 0, to = samples.length): Int16Array {
  const out = new Int16Array(to - from);
  for (let i = from; i < to; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]!));
    out[i - from] = Math.round(clamped * 32767);
  }
  return out;
}

/** 16-bit PCM WAV. */
export function encodeWav(pcm: Pcm): Uint8Array {
  const channelCount = pcm.channels.length;
  const frames = pcm.channels[0]?.length ?? 0;
  const dataBytes = frames * channelCount * 2;
  const out = new Uint8Array(44 + dataBytes);
  const view = new DataView(out.buffer);
  const text = (offset: number, value: string) => [...value].forEach((c, i) => (out[offset + i] = c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, channelCount, true);
  view.setUint32(24, pcm.sampleRate, true);
  view.setUint32(28, pcm.sampleRate * channelCount * 2, true);
  view.setUint16(32, channelCount * 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, dataBytes, true);
  const ints = pcm.channels.map((channel) => toInt16(channel));
  let offset = 44;
  for (let frame = 0; frame < frames; frame++) {
    for (const channel of ints) {
      view.setInt16(offset, channel[frame]!, true);
      offset += 2;
    }
  }
  return out;
}

const MP3_BLOCK = 1152;
const BLOCKS_PER_YIELD = 200;

/** MP3 (stereo or mono). Yields to the event loop now and then so the page stays responsive. */
export async function encodeMp3(pcm: Pcm, kbps = 192): Promise<Uint8Array> {
  const channelCount = pcm.channels.length;
  if (channelCount < 1 || channelCount > 2) throw new Error("MP3 export supports mono or stereo");
  const encoder = new Mp3Encoder(channelCount, pcm.sampleRate, kbps);
  const frames = pcm.channels[0]!.length;
  const parts: Uint8Array[] = [];
  for (let start = 0, block = 0; start < frames; start += MP3_BLOCK, block++) {
    const end = Math.min(frames, start + MP3_BLOCK);
    const left = toInt16(pcm.channels[0]!, start, end);
    const part = channelCount === 2 ? encoder.encodeBuffer(left, toInt16(pcm.channels[1]!, start, end)) : encoder.encodeBuffer(left);
    if (part.length > 0) parts.push(part);
    if (block % BLOCKS_PER_YIELD === BLOCKS_PER_YIELD - 1) await new Promise((resolve) => setTimeout(resolve));
  }
  parts.push(encoder.flush());
  return concat(parts);
}

export async function encode(pcm: Pcm, format: AudioFormat): Promise<Uint8Array> {
  return format === "wav" ? encodeWav(pcm) : encodeMp3(pcm);
}

export const MIME: Record<AudioFormat | "zip", string> = {
  mp3: "audio/mpeg",
  wav: "audio/wav",
  zip: "application/zip",
};

function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}
