import { useEffect, useState, useSyncExternalStore } from "react";
import type { Piece } from "../api/types";
import { Player, type PlayerState } from "./player";

/** Creates a Player for the piece (after mount, so React StrictMode's double mount is safe). */
export function usePlayer(piece: Piece): Player | null {
  const [player, setPlayer] = useState<Player | null>(null);
  useEffect(() => {
    const created = new Player(piece);
    setPlayer(created);
    return () => created.dispose();
  }, [piece]);
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
