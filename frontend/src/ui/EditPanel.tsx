import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useSavePiece } from "../api/hooks";
import { formatRanges, parseRanges, PieceDraft, sameSegments, VOICE_KINDS } from "../music/pieceDraft";
import { describeSection } from "../music/sections";
import type { Section, VoiceKind } from "../api/types";
import { buttonClass } from "./FilePicker";

const input = "rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm";

interface Props {
  pieceId: string;
  draft: PieceDraft;
  onChange: (draft: PieceDraft) => void;
}

/** Edit a piece's title, voices and sections. Changes show in the player at once; Save stores them. */
export function EditPanel({ pieceId, draft, onChange }: Props) {
  const save = useSavePiece(pieceId);
  const errors = save.error instanceof ApiError ? save.error.messages : save.error ? [save.error.message] : [];
  const { piece } = draft;

  return (
    <section className="space-y-6 rounded-lg border border-amber-400/40 bg-zinc-900 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-medium uppercase tracking-wide text-zinc-400">Edit piece</h3>
        <div className="flex items-center gap-3">
          {draft.dirty && <span className="text-xs text-amber-300">Unsaved changes</span>}
          <button type="button" className={buttonClass} disabled={!draft.dirty || save.isPending} onClick={() => { save.reset(); onChange(draft.revert()); }}>
            Revert
          </button>
          <button
            type="button"
            disabled={!draft.dirty || save.isPending}
            onClick={() => save.mutate(draft.toEdits())}
            className="rounded-md bg-amber-400 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {errors.length > 0 && (
        <ul role="alert" className="space-y-1 rounded-md border border-red-400/40 bg-red-400/10 p-3 text-sm text-red-300">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}

      <label className="block text-sm text-zinc-400">
        Title
        <input
          value={piece.title}
          onChange={(e) => onChange(draft.setTitle(e.target.value))}
          className={`${input} mt-1 block w-full`}
        />
      </label>

      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Voices</h4>
        <ul className="space-y-2">
          {piece.tracks.map((track) => (
            <li key={track.id} className="flex flex-wrap items-center gap-3">
              <span className="w-8 font-mono text-xs text-zinc-500">{track.id}</span>
              <input
                aria-label={`${track.id} label`}
                value={track.label}
                onChange={(e) => onChange(draft.setTrack(track.id, { label: e.target.value }))}
                className={`${input} w-40`}
              />
              <select
                aria-label={`${track.id} voice kind`}
                value={track.voice ?? "other"}
                onChange={(e) => onChange(draft.setTrack(track.id, { voice: e.target.value as VoiceKind }))}
                className={input}
              >
                {VOICE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
          Sections <span className="normal-case text-zinc-600">(played in this order; bars count from 1)</span>
        </h4>
        <ul className="space-y-3">
          {piece.sections.map((section, index) => (
            <SectionRow key={section.id} draft={draft} section={section} index={index} onChange={onChange} />
          ))}
        </ul>
        <button type="button" className={`${buttonClass} mt-3`} onClick={() => onChange(draft.addSection())}>
          Add section
        </button>
      </div>
    </section>
  );
}

function SectionRow({
  draft,
  section,
  index,
  onChange,
}: {
  draft: PieceDraft;
  section: Section;
  index: number;
  onChange: (draft: PieceDraft) => void;
}) {
  const { piece } = draft;
  const measureCount = piece.measures.length;
  const [text, setText] = useState(() => formatRanges(section.segments));
  const parsed = parseRanges(text, measureCount);

  // Follow changes that did not come from typing here (revert, a reloaded piece).
  useEffect(() => {
    const current = parseRanges(text, measureCount);
    if (!(current.ok && sameSegments(current.segments, section.segments))) setText(formatRanges(section.segments));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section.segments]);

  const lines = draft.availableLyricNumbers(section.id);
  const lyric = section.lyric_number ?? "";
  const printed = describeSection(piece, section);
  const typed = formatRanges(section.segments);
  const last = piece.sections.length - 1;

  return (
    <li className="grid gap-x-3 gap-y-2 rounded-md border border-zinc-800 p-3 sm:grid-cols-[1fr_1fr_auto]">
      <label className="text-xs text-zinc-500">
        Name
        <input
          value={section.name}
          onChange={(e) => onChange(draft.renameSection(section.id, e.target.value))}
          className={`${input} mt-1 block w-full text-zinc-100`}
        />
      </label>
      <label className="text-xs text-zinc-500">
        Bars
        <input
          value={text}
          aria-invalid={!parsed.ok}
          onChange={(e) => {
            setText(e.target.value);
            const result = parseRanges(e.target.value, measureCount);
            if (result.ok) onChange(draft.setSegments(section.id, result.segments));
          }}
          className={`${input} mt-1 block w-full text-zinc-100 ${parsed.ok ? "" : "border-red-400"}`}
        />
        {!parsed.ok && <span className="text-red-400">{parsed.error}</span>}
        {parsed.ok && printed !== typed && <span className="text-zinc-500">printed as {printed}</span>}
      </label>
      <div className="flex items-end gap-2">
        <button type="button" aria-label="Move up" disabled={index === 0} className={buttonClass} onClick={() => onChange(draft.moveSection(section.id, -1))}>
          ↑
        </button>
        <button type="button" aria-label="Move down" disabled={index === last} className={buttonClass} onClick={() => onChange(draft.moveSection(section.id, 1))}>
          ↓
        </button>
        <button type="button" aria-label="Remove section" disabled={last === 0} className={buttonClass} onClick={() => onChange(draft.removeSection(section.id))}>
          Remove
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500 sm:col-span-3">
        <label className="flex items-center gap-2">
          Lyric line
          <select
            value={lyric}
            onChange={(e) => onChange(draft.setLyricNumber(section.id, e.target.value || null))}
            className={`${input} text-zinc-100`}
          >
            <option value="">none</option>
            {lines.map((line) => (
              <option key={line} value={line}>
                line {line}
              </option>
            ))}
            {lyric && !lines.includes(lyric) && <option value={lyric}>line {lyric} (not in these bars)</option>}
          </select>
        </label>
        <span
          className={`rounded-full border px-2 py-0.5 ${section.source === "user" ? "border-amber-400/50 text-amber-300" : "border-zinc-700"}`}
          title={section.source === "user" ? "Set by a person" : "Suggested from the score"}
        >
          {section.source ?? "auto"}
        </span>
      </div>
    </li>
  );
}
