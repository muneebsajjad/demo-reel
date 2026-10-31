import json, subprocess, shutil
import numpy as np
import pytest
import autopick, music

SR = 48000

def scenes(captions, cuts=4, moves=0):
    return [{"captions": [{"text": c, "kicker": ""} for c in captions], "camera": [[0, "a"]] * (moves + 1)}] + \
           [{"card": "x"}] * (cuts - 1)

def test_profile_reads_mood_from_captions_and_pace():
    calm = autopick.profile({}, scenes(["Read quietly, in private", "Listen and focus"]), None, SR, 60)
    assert calm["mood"] == "calm" and calm["energy"] < 0.3 and calm["voice"] == 0
    fast = autopick.profile({}, scenes(["Launch in seconds", "New: boost your team"], cuts=20), None, SR, 30)
    assert fast["mood"] == "upbeat" and fast["energy"] > calm["energy"]

def test_profile_mood_can_be_set_and_voice_lowers_energy():
    s = scenes(["anything"])
    p = autopick.profile({"audio": {"music": {"auto": True, "mood": "cinematic"}}}, s, None, SR, 30)
    assert p["mood"] == "cinematic"
    voice = np.zeros((30 * SR, 2), np.float32); voice[: 20 * SR] = 0.2
    pv = autopick.profile({"audio": {"music": {"auto": True, "mood": "cinematic"}}}, s, voice, SR, 30)
    assert pv["voice"] > 0.6 and pv["energy"] < p["energy"]

def test_profile_defaults_to_focused_with_no_hints():
    assert autopick.profile({}, scenes(["Table of contents"]), None, SR, 30)["mood"] == "focused"

PROFILE = dict(length=30, voice=0.0, pace=10, mood="focused", energy=0.35, bpm=(75, 105), words=["ambient"])
GOOD = dict(duration=75, bpm=90, beat=0.5, energy=0.35, brightness=1200, swing_db=1.0, busy=1.0, intro=0.5)

def test_score_prefers_a_close_fit_and_explains_the_rest():
    best, terms = autopick.score(GOOD, PROFILE)
    assert best < 0.05 and max(terms.values()) < 0.05
    for change, term in [({"bpm": 130}, "tempo"), ({"energy": 0.9}, "energy"), ({"swing_db": 9}, "swing"),
                         ({"duration": 10}, "length"), ({"intro": 12}, "intro")]:
        s, t = autopick.score({**GOOD, **change}, PROFILE)
        assert s > best and t[term] > 0.25, change

def test_score_accepts_half_and_double_time():
    assert autopick.score({**GOOD, "bpm": 180}, PROFILE)[1]["tempo"] == 0      # double of 90
    assert autopick.score({**GOOD, "bpm": 45}, PROFILE)[1]["tempo"] == 0       # half of 90

def test_busy_bright_tracks_are_penalised_only_under_a_voice():
    busy = {**GOOD, "busy": 4, "brightness": 4000}
    assert autopick.score(busy, PROFILE)[1]["voice"] == 0
    assert autopick.score(busy, {**PROFILE, "voice": 0.8})[1]["voice"] > 1

def test_meta_score_uses_tempo_tags():
    near = autopick.meta_score({"bpm": 90, "words": 1}, PROFILE)[0]
    far = autopick.meta_score({"bpm": 130, "words": 0}, PROFILE)[0]
    unknown = autopick.meta_score({}, PROFILE)[0]
    assert near < unknown < far

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_features_find_the_tempo_of_a_click_track(tmp_path):
    sr, bpm = 22050, 100
    y = np.zeros(sr * 20, np.float32)
    for i in range(0, len(y), int(sr * 60 / bpm)):
        y[i:i + 400] = np.hanning(800)[400:] * np.sin(np.arange(400) * 0.3)
    wav = tmp_path / "click.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", str(wav)],
                   input=y.tobytes(), check=True)
    f = autopick.features(wav)
    assert min(abs(f["bpm"] - bpm), abs(f["bpm"] - 2 * bpm), abs(f["bpm"] - bpm / 2)) < 4
    assert f["duration"] == pytest.approx(20, abs=0.2)

def test_the_bundled_library_covers_every_mood():
    lib = [json.loads(music.sidecar(t).read_text()) for t in sorted(autopick.LIBRARY.glob("*.mp3"))]
    assert 4 <= len(lib) <= 12
    for t in lib:
        assert t["license"] in ("CC0-1.0", "PD") and t["source"].startswith("https://")
    covered = {m for t in lib for m in t["moods"]}
    assert covered >= set(autopick.MOODS)
    assert sum(p.stat().st_size for p in autopick.LIBRARY.glob("*.mp3")) < 12e6
