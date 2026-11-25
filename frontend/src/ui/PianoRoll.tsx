import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Piece } from "../api/types";
import { usePlayerState } from "../audio/hooks";
import type { Player } from "../audio/player";
import { KeyColors } from "../music/keyColors";
import { PianoRollLayout } from "../music/pianoRoll";
import { HEADER_HEIGHT, LABEL_WIDTH, PianoRollPainter } from "./pianoRollPainter";

const ROW_HEIGHT = 10;
const MAX_HEIGHT = 340;
/** Keep the playhead in the left part of the view: scroll when it passes this fraction. */
const FOLLOW_EDGE = 0.85;

/**
 * A piano roll of the piece in performed order: time to the right, pitch up, each note coloured by
 * its place in the key (red do ... purple ti). Click to jump there.
 *
 * Only the visible window is painted on a canvas of the size of the view, so a long piece never
 * needs a huge canvas. While playing, the canvas is repainted every frame for a smooth playhead.
 */
export function PianoRoll({ piece, player }: { piece: Piece; player: Player }) {
  const state = usePlayerState(player);
  const timeline = player.getTimeline();
  const colors = useMemo(() => new KeyColors(piece.key), [piece.key]);
  const [pixelsPerSecond, setPixelsPerSecond] = useState(60);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [follow, setFollow] = useState(true);

  const visible = useMemo(() => new Set(piece.tracks.map((t) => t.id).filter((id) => !hidden.has(id))), [piece.tracks, hidden]);
  const layout = useMemo(
    () => new PianoRollLayout(timeline, colors, { pixelsPerSecond, rowHeight: ROW_HEIGHT, visibleTracks: visible }),
    [timeline, colors, pixelsPerSecond, visible],
  );
  const painter = useMemo(() => new PianoRollPainter(layout, colors), [layout, colors]);
  const muted = useMemo(() => new Set(state.voices.filter((v) => v.muted).map((v) => v.trackId)), [state.voices]);

  const scroller = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  const paint = useCallback(() => {
    const el = scroller.current;
    const target = canvas.current;
    if (!el || !target) return;
    const width = el.clientWidth;
    const height = el.clientHeight;
    const scale = window.devicePixelRatio || 1;
    if (target.width !== Math.round(width * scale) || target.height !== Math.round(height * scale)) {
      target.width = Math.round(width * scale);
      target.height = Math.round(height * scale);
      target.style.width = `${width}px`;
      target.style.height = `${height}px`;
    }
    const ctx = target.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    painter.paint(ctx, {
      width,
      height,
      scrollLeft: el.scrollLeft,
      scrollTop: el.scrollTop,
      playheadSec: player.position,
      mutedTracks: muted,
    });
  }, [painter, player, muted]);

  /** Scroll sideways so the playhead is in view (when following). */
  const followPlayhead = useCallback(() => {
    const el = scroller.current;
    if (!el || !follow) return;
    const x = layout.timeToX(player.position);
    const view = el.clientWidth - LABEL_WIDTH;
    if (x < el.scrollLeft || x > el.scrollLeft + view * FOLLOW_EDGE) el.scrollLeft = Math.max(0, x - view * 0.15);
  }, [layout, player, follow]);

  // Repaint when anything that is drawn changes (also on seek, stop, mute: the player's state changes).
  useEffect(() => {
    followPlayhead();
    paint();
  }, [paint, followPlayhead, state]);

  // While playing, repaint every frame.
  useEffect(() => {
    if (state.status !== "playing") return;
    let frame = requestAnimationFrame(function loop() {
      followPlayhead();
      paint();
      frame = requestAnimationFrame(loop);
    });
    return () => cancelAnimationFrame(frame);
  }, [state.status, paint, followPlayhead]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const observer = new ResizeObserver(paint);
    observer.observe(el);
    return () => observer.disconnect();
  }, [paint]);

  const seekTo = (clientX: number) => {
    const el = scroller.current;
    if (!el) return;
    const x = clientX - el.getBoundingClientRect().left;
    if (x >= LABEL_WIDTH) player.seek(layout.xToTime(x - LABEL_WIDTH + el.scrollLeft));
  };

  const toggle = (trackId: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (!next.delete(trackId)) next.add(trackId);
      return next;
    });

  const legend = useMemo(() => KeyColors.legend(), []);

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h3 className="text-sm font-medium uppercase tracking-wide text-zinc-400">Piano roll</h3>
        <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400">
          {piece.tracks.map((track) => (
            <button
              key={track.id}
              type="button"
              aria-pressed={!hidden.has(track.id)}
              onClick={() => toggle(track.id)}
              className={`rounded-full border px-2 py-0.5 ${hidden.has(track.id) ? "border-zinc-800 text-zinc-600 line-through" : "border-zinc-600 text-zinc-200"}`}
            >
              {track.label}
            </button>
          ))}
          <label className="flex items-center gap-2">
            Zoom
            <input
              type="range"
              aria-label="Piano roll zoom"
              min={20}
              max={200}
              step={10}
              value={pixelsPerSecond}
              onChange={(e) => setPixelsPerSecond(Number(e.target.value))}
              className="w-24"
            />
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            Follow
          </label>
        </div>
      </div>

      <div
        ref={scroller}
        onScroll={paint}
        className="overflow-auto rounded-lg border border-zinc-800 bg-zinc-950"
        style={{ height: Math.min(HEADER_HEIGHT + layout.height, MAX_HEIGHT) }}
      >
        <div style={{ width: LABEL_WIDTH + layout.width, minWidth: "100%", height: HEADER_HEIGHT + layout.height }}>
          <canvas
            ref={canvas}
            role="img"
            aria-label="Piano roll of the piece. Click to jump to that time."
            onClick={(e) => seekTo(e.clientX)}
            style={{ position: "sticky", top: 0, left: 0, display: "block", cursor: "pointer" }}
          />
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-1 text-[11px] text-zinc-400">
        {colors.hasKey ? (
          <>
            {legend.map((color) => (
              <span
                key={color.syllable}
                className="rounded px-1.5 py-0.5 font-medium text-zinc-950"
                style={{ backgroundColor: color.css }}
              >
                {color.syllable}
              </span>
            ))}
            <span className="ml-2 text-zinc-500">Outlined notes are outside the key. Darker = lowered step.</span>
          </>
        ) : (
          <span className="text-zinc-500">No key is set. Set one in Edit to colour the notes by scale degree.</span>
        )}
      </div>
    </section>
  );
}
