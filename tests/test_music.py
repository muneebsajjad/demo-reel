import json, pathlib
import numpy as np
import pytest
import music

def rec(**kw):
    return {"path": pathlib.Path("track.mp3"), **kw}

@pytest.mark.parametrize("lic", ["CC0-1.0", "PD", "Pixabay", "Generated-MIT", "Purchased"])
def test_licences_without_credit_pass(lic):
    assert music.check(rec(license=lic))["ok"]

def test_attribution_licences_need_a_credit():
    with pytest.raises(music.LicenseError, match="needs a published credit"):
        music.check(rec(license="CC-BY-4.0"))
    assert music.check(rec(license="CC-BY-4.0", credit="\"T\" by A, CC BY 4.0"))["credit"]

@pytest.mark.parametrize("lic, why", [("CC-BY-NC-4.0", "non-commercial"), ("CC-BY-ND-4.0", "no derivatives"),
                                      ("CC-BY-NC-ND-3.0", "non-commercial")])
def test_unfit_licences_are_refused_unless_allowed(lic, why):
    with pytest.raises(music.LicenseError, match=why):
        music.check(rec(license=lic, credit="c"))
    assert music.check(rec(license=lic, credit="c"), allow={lic})

def test_missing_and_unknown_licences_are_refused():
    with pytest.raises(music.LicenseError, match="no licence recorded"):
        music.check(rec())
    with pytest.raises(music.LicenseError, match="unknown licence"):
        music.check(rec(license="WTFPL"))

def test_licence_names_read_naturally():
    assert music.LICENSES["CC-BY-NC-SA-4.0"]["name"] == "CC BY-NC-SA 4.0"
    assert music.LICENSES["CC-BY-ND-3.0"]["name"] == "CC BY-ND 3.0"

def test_sidecar_is_read_and_the_edit_wins(tmp_path):
    t = tmp_path / "bed.mp3"; t.write_bytes(b"")
    music.sidecar(t).write_text(json.dumps({"title": "Bed", "license": "CC-BY-4.0", "credit": "c"}))
    r = music.load({"file": "bed.mp3", "title": "Better title", "gainDb": -10}, tmp_path)
    assert r["title"] == "Better title" and r["license"] == "CC-BY-4.0" and "gainDb" not in r

def test_credits_text_says_whether_to_publish():
    text = music.credits_text(rec(title="T", artist="A", source="https://x", license="CC-BY-4.0", credit="CREDIT"),
                              music.LICENSES["CC-BY-4.0"])
    assert "Publish this credit" in text and "CREDIT" in text
    assert "No credit is required" in music.credits_text(rec(title="T", license="CC0-1.0"), music.LICENSES["CC0-1.0"])
    assert "redistribute" in music.credits_text(rec(title="T", license="Pixabay"), music.LICENSES["Pixabay"])

# ---- signal --------------------------------------------------------------------------------------
SR = 8000

def tone(seconds, f=440):
    t = np.arange(int(seconds * SR)) / SR
    return np.stack([np.sin(2 * np.pi * f * t)] * 2, 1).astype(np.float32) * 0.5

def test_fit_trims_and_fades():
    out = music.fit(tone(10), 3 * SR, SR, fade_out=1.0)
    assert out.shape == (3 * SR, 2)
    assert abs(out[0]).max() == 0 and abs(out[-1]).max() < 1e-3                    # faded both ends
    assert np.abs(out[SR:2 * SR]).max() == pytest.approx(0.5, abs=0.01)             # untouched middle

def test_fit_loops_a_short_track_without_gaps():
    out = music.fit(tone(2), 7 * SR, SR, fade_in=0, fade_out=0, xfade=0.5)
    assert out.shape == (7 * SR, 2)
    win = SR // 10
    rms = [np.sqrt((out[i:i + win] ** 2).mean()) for i in range(0, len(out) - win, win)]
    assert min(rms) > 0.2                                                            # never drops out

def test_fit_start_skips_an_intro():
    track = np.concatenate([np.zeros((2 * SR, 2), np.float32), tone(3)])
    out = music.fit(track, SR, SR, start=2.0, fade_in=0, fade_out=0)
    assert np.abs(out).max() > 0.4
    with pytest.raises(ValueError):
        music.fit(track, SR, SR, start=99)

def test_ducking_lowers_music_only_under_speech():
    voice = np.zeros((6 * SR, 2), np.float32)
    voice[2 * SR:4 * SR] = tone(2, 220) * 0.4                                       # speech from 2 s to 4 s
    g = music.speech_gain(voice, SR, duck_db=-12)[:, 0]
    assert g[int(1 * SR)] == pytest.approx(1, abs=1e-3)                              # before: full
    assert 20 * np.log10(g[int(3 * SR)]) == pytest.approx(-12, abs=0.5)              # under speech: ducked
    assert g[int(5.9 * SR)] > 0.9                                                    # after: back up
    assert np.all(np.abs(np.diff(g)) < 0.01)                                         # smooth, no clicks
