import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Piece } from "../api/types";
import { Player, type PlayerState } from "./player";

/**
 * One Player for the component's lifetime (created after mount, so React StrictMode's double mount
 * is safe), kept in step with `piece` as it is edited: only a change to the sections or the notes
 * rebuilds the timeline, so typing a title does not stop the music.
 */
export function usePlayer(piece: Piece): Player | null {
  const [player, setPlayer] = useState<Player | null>(null);
  const first = useRef(piece);
  useEffect(() => {
    const created = new Player(first.current);
    setPlayer(created);
    return () => created.dispose();
  }, []);
  useEffect(() => {
    player?.updatePiece(piece);
  }, [player, piece]);
  return player;
}

export function usePlayerState(player: Player): PlayerState {
  return useSyncExternalStore(player.subscribe, player.getState);
}

export interface PlaybackPosition {
  seconds: number; // rounded to 0.1 s so the UI re-renders only when the display changes
  sectionId: string;
}

/** The playback position and current section, followed with requestAnimationFrame. */
export function usePlaybackPosition(player: Player): PlaybackPosition {
  const { status, tempoScale } = usePlayerState(player);
  const read = (): PlaybackPosition => {
    const seconds = player.position;
    return { seconds: Math.round(seconds * 10) / 10, sectionId: player.getTimeline().sectionAt(seconds).id };
  };
  const [position, setPosition] = useState(read);

  useEffect(() => {
    const update = () =>
      setPosition((previous) => {
        const next = read();
        return next.seconds === previous.seconds && next.sectionId === previous.sectionId ? previous : next;
      });
    update();
    if (status !== "playing") return;
    let frame = requestAnimationFrame(function loop() {
      update();
      frame = requestAnimationFrame(loop);
    });
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player, status, tempoScale]);

  return position;
}
