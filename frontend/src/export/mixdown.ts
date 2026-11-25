import { VoiceChannel, type VoiceSettings } from "../audio/voiceChannel";
import type { Timeline } from "../music/timeline";
import { limitPeak, type Pcm } from "./encoders";

/**
 * Renders a timeline with a given mix to audio, faster than real time, using the same instruments
 * and voice channels as live playback.
 *
 * Unlike live playback there is no 1/sqrt(n) headroom on the output. As in the Python renderer the
 * result is only scaled down if it would clip, so a solo voice is quieter than the tutti.
 */
export class Mixdown {
  static readonly SAMPLE_RATE = 44100;
  /** Room after the last note for instrument release tails. All files get it, so lengths match. */
  static readonly TAIL_SEC = 0.5;

  constructor(private readonly timeline: Timeline) {}

  async render(voices: readonly VoiceSettings[]): Promise<Pcm> {
    const sampleRate = Mixdown.SAMPLE_RATE;
    const frames = Math.ceil((this.timeline.duration + Mixdown.TAIL_SEC) * sampleRate);
    const ctx = new OfflineAudioContext(2, frames, sampleRate);
    for (const voice of voices) {
      if (voice.muted || voice.volume <= 0) continue;
      const channel = new VoiceChannel(ctx, voice, ctx.destination);
      for (const note of this.timeline.notesFor(voice.trackId)) {
        channel.play({ pitch: note.pitch, when: note.startSec, duration: note.durationSec, attack: note.attack });
      }
    }
    const buffer = await ctx.startRendering();
    const pcm: Pcm = {
      sampleRate,
      channels: [buffer.getChannelData(0), buffer.getChannelData(1)],
    };
    limitPeak(pcm);
    return pcm;
  }
}
