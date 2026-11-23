import wave
from pathlib import Path

import numpy as np
import pytest

from tonetool.cli import main
from tonetool.practice import PracticeSet
from tonetool.render import MixSettings, Renderer

from . import scorebuilder as sb


def by_name(files):
    return {f.name: f for f in files}


def test_a_set_has_tutti_plus_three_files_per_voice(import_score):
    piece = import_score(sb.simple_score(), title="My Song")
    names = [f.name for f in PracticeSet(piece).files()]
    assert names == [
        "My_Song_tutti",
        "My_Song_Soprano_solo",
        "My_Song_Soprano_prominent",
        "My_Song_Soprano_stereo",
        "My_Song_Alto_solo",
        "My_Song_Alto_prominent",
        "My_Song_Alto_stereo",
    ]


def test_each_kind_defines_its_mix(import_score):
    piece = import_score(sb.simple_score())
    files = by_name(PracticeSet(piece, others_volume=0.25).files())

    tutti = files["Test_tutti"].settings.resolve(piece)
    assert all(mix.volume == 1.0 and mix.pan == 0.0 and not mix.mute for mix in tutti.values())

    solo = files["Test_Soprano_solo"].settings.resolve(piece)
    assert not solo["T0"].mute and solo["T1"].mute  # only the soprano plays

    prominent = files["Test_Alto_prominent"].settings.resolve(piece)
    assert prominent["T1"].volume == 1.0 and prominent["T0"].volume == 0.25
    assert not prominent["T0"].mute and prominent["T0"].pan == prominent["T1"].pan == 0.0

    stereo = files["Test_Soprano_stereo"].settings.resolve(piece)
    assert stereo["T0"].pan == -1.0 and stereo["T1"].pan == 1.0  # voice left, the rest right
    assert stereo["T0"].volume == stereo["T1"].volume == 1.0


def test_shared_options_apply_to_every_file_but_a_base_track_mix_does_not(import_score):
    from tonetool.render import TrackMix

    piece = import_score(sb.simple_score())
    base = MixSettings(tempo_scale=0.8, count_in_beats=4, metronome=True)
    base.tracks = {"S": TrackMix(volume=0.1)}  # would conflict with the per-file mixes
    for file in PracticeSet(piece, base).files():
        assert (file.settings.tempo_scale, file.settings.count_in_beats, file.settings.metronome) == (0.8, 4, True)
        assert "S" not in file.settings.tracks
    assert base.tracks == {"S": TrackMix(volume=0.1)}  # the caller's settings are untouched


def test_the_audio_matches_the_description(import_score):
    piece = import_score(sb.simple_score())
    files = by_name(PracticeSet(piece).files())

    def render(name):
        return Renderer(piece, files[name].settings).render()

    def rms(a):
        return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))

    tutti, solo_s, solo_a = render("Test_tutti"), render("Test_Soprano_solo"), render("Test_Alto_solo")
    assert rms(solo_s) < rms(tutti) and rms(solo_a) < rms(tutti)
    assert not np.allclose(solo_s, solo_a)  # different voices

    # stereo: the soprano is on the left only, the alto on the right only
    stereo = render("Test_Soprano_stereo")
    left, right = stereo[:, 0], stereo[:, 1]
    assert np.corrcoef(left, solo_s[:, 0])[0, 1] > 0.99
    assert np.corrcoef(right, solo_a[:, 0])[0, 1] > 0.99
    assert abs(np.corrcoef(left, solo_a[:, 0])[0, 1]) < 0.5

    # prominent: the featured voice is louder than the rest, which are still audible
    prominent = render("Test_Soprano_prominent")
    assert rms(prominent) < rms(tutti)
    assert rms(prominent) > rms(solo_s)


def test_export_creates_the_folder_and_writes_every_file(import_score, tmp_path):
    piece = import_score(sb.simple_score())
    folder = tmp_path / "new" / "practice"
    written: list[Path] = []
    paths = PracticeSet(piece).export(folder, fmt="wav", on_written=written.append)
    assert folder.is_dir()
    assert paths == written and len(paths) == 7
    assert {p.name for p in paths} == {f"{f.name}.wav" for f in PracticeSet(piece).files()}
    with wave.open(str(paths[0])) as wav:
        assert (wav.getnchannels(), wav.getframerate()) == (2, 44100)


def test_export_can_write_mp3(import_score, tmp_path):
    piece = import_score(sb.simple_score())
    paths = PracticeSet(piece).export(tmp_path, fmt="mp3", bitrate_kbps=128)
    assert all(p.suffix == ".mp3" and p.read_bytes()[0] == 0xFF for p in paths)


def test_unknown_format_is_rejected(import_score, tmp_path):
    with pytest.raises(ValueError, match="unsupported format"):
        PracticeSet(import_score(sb.simple_score())).export(tmp_path, fmt="ogg")


def test_a_single_voice_piece_only_gets_the_tutti(import_score):
    piece = import_score((["Soprano"], [sb.Bar(notes={"Soprano": "C5/w"})]))
    assert [f.kind for f in PracticeSet(piece).files()] == ["tutti"]


def test_clashing_voice_names_get_the_track_id_added(import_score):
    bars = [sb.Bar(notes={"Soprano": "C5/w"})]
    piece = import_score((["Soprano", "Soprano"], bars))
    names = {f.name for f in PracticeSet(piece).files()}
    assert {"Test_Soprano_T0_solo", "Test_Soprano_T1_solo"} <= names


def test_file_names_keep_unicode_letters_and_drop_path_characters(import_score):
    piece = import_score(sb.simple_score(), title="Juletræet med sin pynt")
    piece.tracks[0].label = "Soprano/Alto (voice 1)"
    names = {f.name for f in PracticeSet(piece).files()}
    assert "Juletræet_med_sin_pynt_tutti" in names
    assert "Juletræet_med_sin_pynt_Soprano_Alto_voice_1_solo" in names


def test_the_cli_writes_a_practice_folder_next_to_the_piece_by_default(import_score, tmp_path, capsys):
    piece = import_score(sb.simple_score())
    path = tmp_path / "song.piece.json"
    piece.save(path)
    main(["practice", str(path), "--format", "wav", "--tempo", "2.0"])
    folder = tmp_path / "practice"
    assert len(list(folder.glob("*.wav"))) == 7
    assert "7 files in" in capsys.readouterr().out
    # --tempo is shared by every file: at 2x speed the 8 s piece takes ~4 s
    with wave.open(str(folder / "Test_tutti.wav")) as wav:
        assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0 + 0.58, abs=0.2)


def test_the_cli_takes_an_output_folder_and_the_others_volume(import_score, tmp_path):
    piece = import_score(sb.simple_score())
    path = tmp_path / "song.piece.json"
    piece.save(path)
    target = tmp_path / "elsewhere"
    main(["practice", str(path), "-o", str(target), "--format", "wav", "--others-volume", "0.5"])
    assert len(list(target.glob("*.wav"))) == 7
    assert not (tmp_path / "practice").exists()


FIVE_VOICES = (
    ["Soprano", "Alto 1", "Alto 2", "Tenor", "Bass"],
    [
        sb.Bar(
            notes={
                "Soprano": "E5/q F5/q G5/q A5/q",
                "Alto 1": "C5/q D5/q E5/q F5/q",
                "Alto 2": "A4/q B4/q C5/q D5/q",
                "Tenor": "E4/q F4/q G4/q A4/q",
                "Bass": "C3/q D3/q E3/q F3/q",
            }
        )
        for _ in range(4)
    ],
)


def rms(audio):
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def test_the_other_voices_are_scaled_by_how_many_there_are(import_score):
    piece = import_score(FIVE_VOICES)
    files = by_name(PracticeSet(piece, others_volume=0.3).files())  # four other voices

    prominent = files["Test_Tenor_prominent"].settings.resolve(piece)
    assert prominent["T3"].volume == 1.0
    assert prominent["T0"].volume == pytest.approx(0.3 / 2)  # 0.3 combined / sqrt(4)

    stereo = files["Test_Tenor_stereo"].settings.resolve(piece)
    assert stereo["T3"].pan == -1.0 and stereo["T3"].volume == 1.0
    assert stereo["T0"].pan == 1.0 and stereo["T0"].volume == pytest.approx(0.5)  # 1 / sqrt(4)


def test_prominent_voice_stands_out_by_about_the_requested_margin(import_score):
    piece = import_score(FIVE_VOICES)
    for file in PracticeSet(piece, others_volume=0.3).files():
        if file.kind != "prominent":
            continue
        featured = file.track_id
        assert featured is not None
        solo = file.settings.model_copy(deep=True)
        solo.tracks = {featured: file.settings.tracks[featured], "*": file.settings.tracks["*"].model_copy(update={"mute": True})}
        background = file.settings.model_copy(deep=True)
        background.tracks = {featured: file.settings.tracks[featured].model_copy(update={"mute": True}), "*": file.settings.tracks["*"]}
        ratio = rms(Renderer(piece, background).render()) / rms(Renderer(piece, solo).render())
        # all the others together are well below the featured voice (about 0.3), not level with it
        assert 0.15 < ratio < 0.5, (featured, ratio)


def test_stereo_balances_the_two_ears(import_score):
    piece = import_score(FIVE_VOICES)
    for file in PracticeSet(piece).files():
        if file.kind != "stereo":
            continue
        audio = Renderer(piece, file.settings).render()
        ratio = rms(audio[:, 1]) / rms(audio[:, 0])  # everyone else (right) vs the featured voice (left)
        assert 0.7 < ratio < 1.4, (file.name, ratio)  # within about 3 dB; unscaled it was ~2x
