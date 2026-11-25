import type { Piece } from "../api/types";
import { PlaybackCursor } from "../music/cursor";
import { Timeline, TimelineBuilder, type ScheduledNote } from "../music/timeline";
import { defaultVoices, VoiceChannel, type VoiceSettings } from "./voiceChannel";

export type PlayerStatus = "stopped" | "playing" | "paused";

/** Everything the UI renders from. A new object is created on every change. */
export interface PlayerState {
  status: PlayerStatus;
  tempoScale: number;
  voices: readonly VoiceSettings[];
}

const TICK_MS = 25;
const LOOKAHEAD_SEC = 0.15;
/** Hidden tabs throttle timers (to ~1 s), so schedule much further ahead while hidden. */
const HIDDEN_LOOKAHEAD_SEC = 2;
/** Gap between pressing play and the first sound, so nothing is scheduled in the past. */
const START_LEAD_SEC = 0.05;

/**
 * Plays a piece with Web Audio: one `VoiceChannel` per track, a look-ahead scheduler, and
 * transport (play / pause / stop / seek / start from section).
 *
 * UI code subscribes with `useSyncExternalStore(player.subscribe, player.getState)`. The playback
 * position changes continuously, so it is read on demand via `position` instead of being state.
 */
export class Player {
  private readonly ctx = new AudioContext();
  private readonly master: GainNode;
  private readonly channels = new Map<string, VoiceChannel>();
  private timeline: Timeline;
  private state: PlayerState;
  private readonly listeners = new Set<() => void>();

  private cursor: PlaybackCursor | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private resumeAt = 0; // timeline position (seconds) when stopped or paused
  private startedAtPosition = 0; // timeline position at the moment of the last start
  private startedAtContext = 0; // AudioContext time of that moment

  constructor(private readonly piece: Piece) {
    this.timeline = new TimelineBuilder(piece).build();
    // Headroom: voices add up, so scale the sum by 1/sqrt(n). No compressor: its behaviour
    // differs between browsers.
    this.master = this.ctx.createGain();
    this.master.gain.value = 1 / Math.sqrt(Math.max(1, piece.tracks.length));
    this.master.connect(this.ctx.destination);

    const voices = defaultVoices(piece);
    for (const voice of voices) this.channels.set(voice.trackId, new VoiceChannel(this.ctx, voice, this.master));
    this.state = { status: "stopped", tempoScale: 1, voices };
  }

  // --- state for the UI -------------------------------------------------------------------

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getState = (): PlayerState => this.state;

  get duration(): number {
    return this.timeline.duration;
  }

  getTimeline(): Timeline {
    return this.timeline;
  }

  /** Current position in seconds, compensated for output latency so it matches what is heard. */
  get position(): number {
    if (this.state.status !== "playing") return this.resumeAt;
    const elapsed = this.ctx.currentTime - this.startedAtContext - this.outputLatency();
    return clamp(this.startedAtPosition + elapsed, this.startedAtPosition, this.duration);
  }

  // --- transport --------------------------------------------------------------------------

  async play(): Promise<void> {
    if (this.state.status === "playing") return;
    await this.ctx.resume(); // must follow a user gesture (autoplay policy)
    this.begin(this.resumeAt >= this.duration ? 0 : this.resumeAt);
  }

  pause(): void {
    if (this.state.status !== "playing") return;
    this.resumeAt = this.position;
    this.halt("paused");
  }

  stop(): void {
    this.resumeAt = 0;
    this.halt("stopped");
  }

  /** Jump to a position; keeps playing if it was playing. */
  seek(seconds: number): void {
    const target = clamp(seconds, 0, this.duration);
    if (this.state.status === "playing") this.begin(target);
    else this.resumeAt = target;
    this.emit({});
  }

  /** Start (or jump to) the start of a section and play. */
  async playFromSection(sectionId: string): Promise<void> {
    const start = this.timeline.sectionStart(sectionId);
    await this.ctx.resume();
    this.begin(start);
  }

  // --- mixing -----------------------------------------------------------------------------

  setVoice(trackId: string, change: Partial<Omit<VoiceSettings, "trackId">>): void {
    const voices = this.state.voices.map((v) => (v.trackId === trackId ? { ...v, ...change } : v));
    const updated = voices.find((v) => v.trackId === trackId);
    if (!updated) throw new Error(`no track ${JSON.stringify(trackId)}`);
    this.channels.get(trackId)!.apply(updated);
    this.emit({ voices });
  }

  /** Change the tempo (1 = as notated). The musical position is kept. */
  setTempoScale(scale: number): void {
    const wasPlaying = this.state.status === "playing";
    const position = this.position;
    const ratio = this.state.tempoScale / scale; // timeline times are proportional to 1/scale
    this.timeline = new TimelineBuilder(this.piece, scale).build();
    this.resumeAt = position * ratio;
    this.state = { ...this.state, tempoScale: scale };
    if (wasPlaying) this.begin(this.resumeAt);
    this.emit({});
  }

  dispose(): void {
    this.halt("stopped");
    this.listeners.clear();
    for (const channel of this.channels.values()) channel.disconnect();
    void this.ctx.close();
  }

  // --- scheduling -------------------------------------------------------------------------

  private begin(position: number): void {
    this.silence();
    this.resumeAt = position;
    this.startedAtPosition = position;
    this.startedAtContext = this.ctx.currentTime + START_LEAD_SEC;
    this.cursor = new PlaybackCursor(this.timeline, position);
    for (const note of this.cursor.takeHeld()) this.schedule(note);
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.emit({ status: "playing" });
    this.tick();
  }

  private tick(): void {
    if (!this.cursor) return;
    const lookahead = typeof document !== "undefined" && document.hidden ? HIDDEN_LOOKAHEAD_SEC : LOOKAHEAD_SEC;
    const horizon = this.startedAtPosition + (this.ctx.currentTime - this.startedAtContext) + lookahead;
    for (const note of this.cursor.takeUntil(horizon)) this.schedule(note);
    if (this.position >= this.duration) {
      this.stop();
    }
  }

  private schedule(note: ScheduledNote): void {
    this.channels.get(note.trackId)?.play({
      pitch: note.pitch,
      when: this.startedAtContext + (note.startSec - this.startedAtPosition),
      duration: note.durationSec,
      attack: note.attack,
    });
  }

  /** Stop the scheduler and silence everything already handed to the audio graph. */
  private silence(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.cursor = null;
    for (const channel of this.channels.values()) channel.restart();
  }

  private halt(status: PlayerStatus): void {
    this.silence();
    this.emit({ status });
  }

  private outputLatency(): number {
    const ctx = this.ctx as AudioContext & { outputLatency?: number };
    return ctx.outputLatency ?? ctx.baseLatency ?? 0;
  }

  private emit(change: Partial<PlayerState>): void {
    this.state = { ...this.state, ...change };
    for (const listener of this.listeners) listener();
  }
}

const clamp = (x: number, low: number, high: number): number => Math.min(high, Math.max(low, x));
