import type { KeyColors } from "../music/keyColors";
import type { PianoRollLayout } from "../music/pianoRoll";

/** Width of the pitch-label column and height of the section header, in pixels. */
export const LABEL_WIDTH = 48;
export const HEADER_HEIGHT = 22;

export interface PaintView {
  /** Size of the visible area in CSS pixels. */
  width: number;
  height: number;
  scrollLeft: number;
  scrollTop: number;
  /** Where the playhead is, in seconds; null to draw none. */
  playheadSec: number | null;
  /** Voices drawn dimmed. */
  mutedTracks: ReadonlySet<string>;
}

const COLORS = {
  background: "#09090b",
  panel: "#18181b",
  blackKey: "rgba(255, 255, 255, 0.035)",
  tonicRow: "rgba(239, 68, 68, 0.12)",
  octaveLine: "rgba(255, 255, 255, 0.12)",
  sectionLine: "rgba(255, 255, 255, 0.2)",
  label: "#a1a1aa",
  sectionName: "#d4d4d8",
  outline: "rgba(255, 255, 255, 0.75)",
  playhead: "#fbbf24",
};

/**
 * Draws the visible part of a piano roll on a canvas. All the geometry is in the layout; this only
 * turns it into pixels for the current scroll position: rows, section lines, notes, the playhead,
 * and on top of them the pitch labels (with a swatch of each row's colour) and the section header.
 */
export class PianoRollPainter {
  constructor(
    private readonly layout: PianoRollLayout,
    private readonly colors: KeyColors,
  ) {}

  paint(ctx: CanvasRenderingContext2D, view: PaintView): void {
    const { width, height } = view;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = COLORS.background;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.beginPath();
    ctx.rect(LABEL_WIDTH, HEADER_HEIGHT, width - LABEL_WIDTH, height - HEADER_HEIGHT);
    ctx.clip();
    this.paintRows(ctx, view);
    this.paintSectionLines(ctx, view);
    this.paintNotes(ctx, view);
    this.paintPlayhead(ctx, view);
    ctx.restore();

    this.paintLabels(ctx, view);
    this.paintHeader(ctx, view);
  }

  private paintRows(ctx: CanvasRenderingContext2D, { width, height, scrollTop }: PaintView): void {
    const rowHeight = this.rowHeight;
    for (const row of this.layout.rows) {
      const y = HEADER_HEIGHT + row.y - scrollTop;
      if (y + rowHeight < HEADER_HEIGHT || y > height) continue;
      if (row.isTonic || row.isBlackKey) {
        ctx.fillStyle = row.isTonic ? COLORS.tonicRow : COLORS.blackKey;
        ctx.fillRect(LABEL_WIDTH, y, width - LABEL_WIDTH, rowHeight);
      }
      if (row.label) {
        ctx.fillStyle = COLORS.octaveLine;
        ctx.fillRect(LABEL_WIDTH, y + rowHeight - 1, width - LABEL_WIDTH, 1);
      }
    }
  }

  private paintSectionLines(ctx: CanvasRenderingContext2D, { height, scrollLeft }: PaintView): void {
    ctx.fillStyle = COLORS.sectionLine;
    for (const mark of this.layout.sections) {
      ctx.fillRect(Math.round(LABEL_WIDTH + mark.x - scrollLeft), HEADER_HEIGHT, 1, height - HEADER_HEIGHT);
    }
  }

  private paintNotes(ctx: CanvasRenderingContext2D, view: PaintView): void {
    const { width, scrollLeft, scrollTop, mutedTracks } = view;
    for (const note of this.layout.rectsBetween(scrollLeft, scrollLeft + width - LABEL_WIDTH)) {
      const x = LABEL_WIDTH + note.x - scrollLeft;
      const y = HEADER_HEIGHT + note.y - scrollTop;
      ctx.globalAlpha = mutedTracks.has(note.trackId) ? 0.22 : 1;
      ctx.fillStyle = note.color.css;
      ctx.fillRect(x, y, note.width, note.height);
      if (!note.color.inKey) {
        ctx.strokeStyle = COLORS.outline;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, y + 0.5, note.width - 1, note.height - 1);
      }
    }
    ctx.globalAlpha = 1;
  }

  private paintPlayhead(ctx: CanvasRenderingContext2D, { height, scrollLeft, playheadSec }: PaintView): void {
    if (playheadSec === null) return;
    ctx.fillStyle = COLORS.playhead;
    ctx.fillRect(Math.round(LABEL_WIDTH + this.layout.timeToX(playheadSec) - scrollLeft) - 1, HEADER_HEIGHT, 2, height - HEADER_HEIGHT);
  }

  private paintLabels(ctx: CanvasRenderingContext2D, { height, scrollTop }: PaintView): void {
    ctx.fillStyle = COLORS.panel;
    ctx.fillRect(0, HEADER_HEIGHT, LABEL_WIDTH, height - HEADER_HEIGHT);
    ctx.font = "9px ui-monospace, monospace";
    ctx.textBaseline = "middle";
    const rowHeight = this.rowHeight;
    for (const row of this.layout.rows) {
      const y = HEADER_HEIGHT + row.y - scrollTop;
      if (y + rowHeight < HEADER_HEIGHT || y > height) continue;
      ctx.fillStyle = this.colors.colorOf(row.pitch).css; // a swatch of the colour of this row's notes
      ctx.fillRect(0, y, 5, rowHeight - 1);
      if (row.label) {
        ctx.fillStyle = COLORS.label;
        ctx.fillText(row.label, 9, y + rowHeight / 2);
      }
    }
  }

  private paintHeader(ctx: CanvasRenderingContext2D, { width, scrollLeft }: PaintView): void {
    ctx.fillStyle = COLORS.panel;
    ctx.fillRect(0, 0, width, HEADER_HEIGHT);
    ctx.save();
    ctx.beginPath();
    ctx.rect(LABEL_WIDTH, 0, width - LABEL_WIDTH, HEADER_HEIGHT);
    ctx.clip();
    ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
    ctx.textBaseline = "middle";
    ctx.fillStyle = COLORS.sectionName;
    for (const mark of this.layout.sections) {
      ctx.fillText(mark.name, LABEL_WIDTH + mark.x - scrollLeft + 5, HEADER_HEIGHT / 2);
    }
    ctx.restore();
  }

  private get rowHeight(): number {
    return this.layout.rowHeight;
  }
}
