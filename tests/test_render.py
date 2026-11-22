import wave

import numpy as np
import pytest

from tonetool.render import MixSettings, Renderer, TrackMix

from . import scorebuilder as sb


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def test_renders_expected_length(import_score):
    piece = import_score(sb.simple_score(), bpm=120)  # 4 bars * 2 s = 8 s
    audio = Renderer(piece).render()
    assert audio.shape[1] == 2
    assert 8.0 < len(audio) / 44100 < 9.5  # plus release tail
    assert rms(audio) > 0.01


def test_mute_and_volume_change_levels(import_score):
    piece = import_score(sb.simple_score())
    full = rms(Renderer(piece).render())
    soprano_only = rms(Renderer(piece, MixSettings(tracks={"A": TrackMix(mute=True)})).render())
    quiet_alto = rms(Renderer(piece, MixSettings(tracks={"A": TrackMix(volume=0.1)})).render())
    assert soprano_only < full
    assert soprano_only < quiet_alto < full


def test_pan_places_sound_in_one_channel(import_score):
    piece = import_score(sb.simple_score())
    settings = MixSettings(tracks={"S": TrackMix(pan=-1.0), "A": TrackMix(mute=True)})
    audio = Renderer(piece, settings).render()
    assert rms(audio[:, 0]) > 0.01
    assert rms(audio[:, 1]) < 1e-4


def test_focus_on_puts_focus_left_and_louder(import_score):
    piece = import_score(sb.simple_score())
    mixes = MixSettings.focus_on(["A"], others_volume=0.2).resolve(piece)
    assert mixes["T1"].volume == 1.0 and mixes["T1"].pan < 0
    assert mixes["T0"].volume == 0.2 and mixes["T0"].pan > 0


def test_specific_key_beats_voice_kind_beats_wildcard(import_score):
    piece = import_score(sb.simple_score())
    settings = MixSettings(
        tracks={"*": TrackMix(volume=0.1), "S": TrackMix(volume=0.5), "Soprano": TrackMix(volume=0.9)}
    )
    mixes = settings.resolve(piece)
    assert mixes["T0"].volume == 0.9
    assert mixes["T1"].volume == 0.1


def test_unknown_track_is_an_error(import_score):
    piece = import_score(sb.simple_score())
    with pytest.raises(KeyError, match="Tenor"):
        MixSettings(tracks={"Tenor": TrackMix()}).resolve(piece)


def test_section_loops_and_count_in_extend_duration(import_score):
    piece = import_score(sb.endings_score(), bpm=120)  # section A = 4 bars = 8 s
    base = Renderer(piece, MixSettings(section="s1")).timeline().duration
    looped = Renderer(piece, MixSettings(section="s1", loops=3)).timeline().duration
    assert looped == pytest.approx(3 * base)
    plain = len(Renderer(piece, MixSettings(section="s1")).render())
    counted = len(Renderer(piece, MixSettings(section="s1", count_in_beats=4)).render())
    assert (counted - plain) / 44100 == pytest.approx(2.0, abs=0.01)  # 4 beats at 120 bpm


def test_metronome_adds_clicks_in_silent_passage(import_score):
    parts = ["Soprano"]
    bars = [sb.Bar(notes={"Soprano": "R/w"})]
    piece = import_score((parts, bars), bpm=120)
    assert rms(Renderer(piece).render()) == 0
    assert rms(Renderer(piece, MixSettings(metronome=True)).render()) > 0.001


def test_wav_file_is_valid(import_score, tmp_path):
    piece = import_score(sb.simple_score())
    path = Renderer(piece, MixSettings(count_in_beats=4)).render_to_wav(tmp_path / "out.wav")
    with wave.open(str(path)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2, 2, 44100)
        assert wav.getnframes() > 44100


def test_mp3_output_is_valid_and_sized_by_bitrate(import_score, tmp_path):
    piece = import_score(sb.simple_score(), bpm=120)  # ~8.6 s with tail
    renderer = Renderer(piece)
    path = renderer.render_to_file(tmp_path / "out.mp3", bitrate_kbps=128)
    data = path.read_bytes()
    assert data[0] == 0xFF and data[1] & 0xE0 == 0xE0  # MPEG frame sync
    seconds = len(renderer.render()) / 44100
    assert len(data) == pytest.approx(seconds * 128_000 / 8, rel=0.05)


def test_output_format_follows_suffix(import_score, tmp_path):
    piece = import_score(sb.simple_score())
    assert Renderer(piece).render_to_file(tmp_path / "a.WAV").read_bytes()[:4] == b"RIFF"
    with pytest.raises(ValueError, match="unsupported"):
        Renderer(piece).render_to_file(tmp_path / "a.ogg")


def test_note_entering_mid_hold_has_no_attack_ramp():
    from tonetool.render import AdditiveSynth

    synth = AdditiveSynth()
    struck = synth.render_note(69, 1.0, 44100, attack=True)
    entering = synth.render_note(69, 1.0, 44100, attack=False)
    window = slice(0, int(0.005 * 44100))  # first 5 ms: the struck note is still ramping up
    assert np.abs(entering[window]).max() > 3 * np.abs(struck[window]).max()
    assert entering[0] == pytest.approx(0.0)  # still faded in a few ms: no click
