/** Instruments: how one note is turned into sound. Swappable per voice, even mid-playback. */

export interface NoteEvent {
  pitch: number; // MIDI note number
  when: number; // AudioContext time the note starts
  duration: number; // seconds
  /** False: joins a note already held, so there is no strike (and no percussive decay). */
  attack: boolean;
}

export interface Instrument {
  readonly id: string;
  readonly label: string;
  /**
   * Schedules one note into `output`. Uses only standard nodes, so it works in a live context and
   * in an OfflineAudioContext alike. Every node it starts it also stops, once the note has died away.
   */
  play(ctx: BaseAudioContext, output: AudioNode, note: NoteEvent): void;
}

export const midiToHz = (pitch: number): number => 440 * 2 ** ((pitch - 69) / 12);
