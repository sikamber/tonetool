import type { Piece } from "../api/types";
import type { VoiceSettings } from "../audio/voiceChannel";

export type PracticeKind = "tutti" | "solo" | "prominent" | "stereo";

/** File-name-safe version of `text`: letters (any script) and digits are kept, runs of the rest become `_`. */
export function slug(text: string): string {
  return text.replace(/[^\p{L}\p{N}_]+/gu, "_").replace(/^_+|_+$/g, "");
}

export interface PracticeFile {
  kind: PracticeKind;
  trackId: string | null; // the featured voice; null for the tutti file
  name: string; // file name without extension
  voices: VoiceSettings[]; // the complete mix for this file
}

/**
 * The practice files for one piece: a tutti, plus for every voice the voice alone, the voice
 * prominent, and the voice panned left against the rest panned right. A port of `practice.py`.
 *
 * `base` carries what is shared by every file (here: each voice's instrument); volume, pan and
 * mute in it are ignored, since each file defines its own.
 *
 * `othersVolume` is the *combined* level of all the other voices in the prominent files, relative to
 * the featured voice. Voices add up, so with n other voices each one is scaled by 1/sqrt(n). The
 * stereo files use the same rule so that the featured voice on the left is about as loud as
 * everyone else together on the right.
 */
export class PracticeSet {
  static readonly STEREO_PAN = 1;

  constructor(
    private readonly piece: Piece,
    private readonly base: readonly VoiceSettings[],
    private readonly othersVolume = 0.3,
  ) {
    if (othersVolume < 0) throw new Error("othersVolume must not be negative");
  }

  /** Name prefix shared by everything exported from this piece. */
  get prefix(): string {
    return slug(this.piece.title) || "practice";
  }

  /** Tutti first, then each voice's solo, prominent and stereo files. A single voice only gets the tutti. */
  files(): PracticeFile[] {
    const files: PracticeFile[] = [
      { kind: "tutti", trackId: null, name: `${this.prefix}_tutti`, voices: this.mix(() => ({})) },
    ];
    if (this.piece.tracks.length < 2) return files;

    const slugs = this.voiceSlugs();
    const share = 1 / Math.sqrt(this.piece.tracks.length - 1);
    const kinds = ["solo", "prominent", "stereo"] as const;
    for (const track of this.piece.tracks) {
      for (const kind of kinds) {
        files.push({
          kind,
          trackId: track.id,
          name: `${this.prefix}_${slugs.get(track.id)}_${kind}`,
          voices: this.mix((id) => {
            const featured = id === track.id;
            switch (kind) {
              case "solo":
                return { muted: !featured };
              case "prominent":
                return { volume: featured ? 1 : this.othersVolume * share };
              case "stereo":
                return featured
                  ? { pan: -PracticeSet.STEREO_PAN }
                  : { pan: PracticeSet.STEREO_PAN, volume: share };
            }
          }),
        });
      }
    }
    return files;
  }

  /** Every voice reset to volume 1, centre, unmuted, then adjusted by `change`; instruments are kept. */
  private mix(change: (trackId: string) => Partial<VoiceSettings>): VoiceSettings[] {
    return this.base.map((voice) => ({
      ...voice,
      volume: 1,
      pan: 0,
      muted: false,
      ...change(voice.trackId),
    }));
  }

  /** File-name part for each track id: its label, with the id added if labels collide. */
  private voiceSlugs(): Map<string, string> {
    const slugs = new Map(this.piece.tracks.map((t) => [t.id, slug(t.label) || t.id] as const));
    if (new Set(slugs.values()).size < slugs.size) {
      return new Map([...slugs].map(([id, s]) => [id, `${s}_${id}`] as const));
    }
    return slugs;
  }
}
