import type { Piece } from "../api/types";
import { DEFAULT_INSTRUMENT_ID, instrumentById, type Instrument, type NoteEvent } from "./instruments";

export interface VoiceSettings {
  trackId: string;
  volume: number; // 0..1
  pan: number; // -1 (left) .. 1 (right)
  muted: boolean;
  instrumentId: string;
}

/** Every track of a piece at the defaults: full volume, centred, unmuted, default instrument. */
export function defaultVoices(piece: Piece): VoiceSettings[] {
  return piece.tracks.map((t) => ({
    trackId: t.id,
    volume: 1,
    pan: 0,
    muted: false,
    instrumentId: DEFAULT_INSTRUMENT_ID,
  }));
}

/** Time constant for parameter changes, so sliders don't click. */
const SMOOTHING = 0.01;

/**
 * One voice's signal path: notes -> session gain -> volume -> pan -> destination.
 *
 * The session gain exists so that notes already scheduled can be silenced instantly when playback
 * stops or jumps: `restart()` fades out the old session and begins a fresh one.
 */
export class VoiceChannel {
  private readonly volume: GainNode;
  private readonly panner: StereoPannerNode;
  private session: GainNode;
  private instrument: Instrument;

  constructor(
    private readonly ctx: BaseAudioContext,
    settings: VoiceSettings,
    destination: AudioNode,
  ) {
    this.volume = ctx.createGain();
    this.panner = ctx.createStereoPanner();
    this.volume.connect(this.panner).connect(destination);
    this.session = this.newSession();
    this.instrument = instrumentById(settings.instrumentId);
    this.apply(settings, true);
  }

  /**
   * Push new settings to the audio graph (takes effect at once, including for held notes). Changes
   * are smoothed to avoid clicks, except when `immediate`, used for the initial values.
   */
  apply(settings: VoiceSettings, immediate = false): void {
    const now = this.ctx.currentTime;
    const volume = settings.muted ? 0 : settings.volume;
    if (immediate) {
      this.volume.gain.setValueAtTime(volume, now);
      this.panner.pan.setValueAtTime(settings.pan, now);
    } else {
      this.volume.gain.setTargetAtTime(volume, now, SMOOTHING);
      this.panner.pan.setTargetAtTime(settings.pan, now, SMOOTHING);
    }
    this.instrument = instrumentById(settings.instrumentId); // applies to notes scheduled from now on
  }

  play(note: NoteEvent): void {
    this.instrument.play(this.ctx, this.session, note);
  }

  /** Silence everything scheduled so far and start a clean session. */
  restart(): void {
    const old = this.session;
    old.gain.cancelScheduledValues(this.ctx.currentTime);
    old.gain.setTargetAtTime(0, this.ctx.currentTime, 0.005);
    setTimeout(() => old.disconnect(), 200);
    this.session = this.newSession();
  }

  disconnect(): void {
    this.session.disconnect();
    this.volume.disconnect();
    this.panner.disconnect();
  }

  private newSession(): GainNode {
    const session = this.ctx.createGain();
    session.connect(this.volume);
    return session;
  }
}
