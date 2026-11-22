# tonetool

Choir practice tool. Prototype stage: import a MusicXML score, review its structure
(sections, repeats, jumps), and export a practice audio file as MP3 or WAV (e.g. "alto loud on the left, everyone
else quiet on the right, 80% tempo, 4-beat count-in, metronome").

## Design

- **MusicXML is the immutable source for notes.** `piece.json` is the final authority for sections
  and playback order; the importer only *suggests* them (`"source": "auto"`).
- Measures are referenced by 0-based document-order index, never printed number.
- Notes live in the measures, keyed by track: `Measure.voices[track_id]` is a `VoiceMeasure`
  (what that voice sings in that bar; empty if it rests, never missing). `Track` is just id/label/voice kind, so the measure count
  exists in one place; `Piece.voice_measures(track_id)` gives the horizontal view of one voice.
- Playback order is a flat list of measure ranges (expresses voltas, D.S./coda, anything).
- Ties are stored as a flag on the continuing note (`tied`), not merged at import. The timeline
  resolves them in *performed* order: a `tied` note extends the held note of the same pitch if one
  ends exactly where it starts; otherwise (a jump or loop landed mid-tie) it sounds without an attack.
- `models.py` (Piece, Track, Section, PlaybackOrder) · `structure.py` (lxml: repeats, endings,
  `<sound>` jumps, rehearsal marks → suggestions) · `importer.py` (music21 notes + structure →
  Piece) · `timeline.py` (unroll order → absolute-time events + time→measure map) ·
  `render.py` (Synth + Renderer → MP3/WAV) · `cli.py` (thin wrapper).

## Usage

```bash
uv sync
uv run tonetool import examples/endings.musicxml      # -> examples/endings.piece.json
uv run tonetool show examples/endings.piece.json      # tracks, sections, order, warnings
uv run tonetool render examples/endings.piece.json -o out.mp3 \
    --volume A=1:-0.6 --volume '*=0.25:0.6' --tempo 0.8 --count-in 4 --metronome
uv run tonetool render examples/endings.piece.json --section s1 --loops 3   # default: .mp3 next to the json
uv run pytest
```

Output format follows the `-o` suffix (`.mp3` default, `.wav`); `--bitrate` sets MP3 kbps (default 192).

`--volume TRACK=VOL[:PAN]`: TRACK is a track id (`T0`, `T1`, ...), label, voice letter (`S/A/T/B`),
or `*` for everything else. Full settings can be given as JSON via `--params` (see `MixSettings`).

To correct a wrong suggestion, edit `sections` / `playback_order` in the JSON and set `"source": "user"`.

## Known limits

- Audio is a plain additive-synth tone (no soundfont/FluidSynth yet). MP3 encoding is bundled (`lameenc`), so ffmpeg isn't needed.
- Tempo is read per measure (mid-measure tempo changes are ignored); lyrics are not imported.
- Text-only jumps ("D.S. al Coda" without `<sound>` attributes) are warned about, not followed.
- Tests use synthetic scores from `tests/scorebuilder.py`; real exporter output (MuseScore, etc.)
  still needs to be tried.
