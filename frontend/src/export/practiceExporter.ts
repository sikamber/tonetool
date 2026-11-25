import { zipSync } from "fflate";
import type { Piece } from "../api/types";
import type { PlayerState } from "../audio/player";
import { defaultVoices, type VoiceSettings } from "../audio/voiceChannel";
import { TimelineBuilder, type Timeline } from "../music/timeline";
import { encode, MIME, type AudioFormat } from "./encoders";
import { Mixdown } from "./mixdown";
import { PracticeSet } from "./practiceSet";

export interface ExportedFile {
  name: string; // including extension
  bytes: Uint8Array;
  mime: string;
}

export type Progress = (done: number, total: number, name: string) => void;

/**
 * Exports a piece as audio files using the player's current settings.
 *
 * `single` is the mix as it sounds right now (every voice's volume, pan, mute and instrument, at
 * the current tempo). `zip` is the same set of files as `tonetool practice`: tutti plus each voice
 * solo / prominent / stereo. It ignores the player's settings and always uses the defaults (as
 * notated tempo, default instrument), so the set is the same whatever the mixer looks like.
 */
export class PracticeExporter {
  constructor(private readonly piece: Piece) {}

  async single(state: PlayerState, format: AudioFormat): Promise<ExportedFile> {
    const name = `${new PracticeSet(this.piece, state.voices).prefix}_mix`;
    return this.renderFile(this.timeline(state), state.voices, name, format);
  }

  async zip(format: AudioFormat, onProgress?: Progress): Promise<ExportedFile> {
    const set = new PracticeSet(this.piece, defaultVoices(this.piece));
    const files = set.files();
    const timeline = new TimelineBuilder(this.piece).build();
    const entries: Record<string, [Uint8Array, { level: 0 }]> = {};
    for (const [i, file] of files.entries()) {
      onProgress?.(i, files.length, file.name);
      const exported = await this.renderFile(timeline, file.voices, file.name, format);
      entries[exported.name] = [exported.bytes, { level: 0 }]; // audio is already compressed: just store
    }
    onProgress?.(files.length, files.length, "");
    return { name: `${set.prefix}_practice.zip`, bytes: zipSync(entries), mime: MIME.zip };
  }

  private timeline(state: PlayerState): Timeline {
    return new TimelineBuilder(this.piece, state.tempoScale).build();
  }

  private async renderFile(
    timeline: Timeline,
    voices: readonly VoiceSettings[],
    name: string,
    format: AudioFormat,
  ): Promise<ExportedFile> {
    const pcm = await new Mixdown(timeline).render(voices);
    return { name: `${name}.${format}`, bytes: await encode(pcm, format), mime: MIME[format] };
  }
}

/** Hand a file to the browser's download mechanism. */
export function downloadFile(file: ExportedFile): void {
  const url = URL.createObjectURL(new Blob([file.bytes as BlobPart], { type: file.mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
