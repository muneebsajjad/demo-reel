import json
import numpy as np
import pytest
import layout, subtitles

EDIT = {"take": "t", "build": "build", "window": {"x": 40, "y": 356, "w": 1000, "h": 934, "bar": 52, "r": 22, "url": "x.com"},
        "shots": {"a": {"fit": ["r"], "dy": -100, "1:1": {"dy": 20}, "16:9": {"pad": 5}}}, "scenes": []}

@pytest.mark.parametrize("fmt", list(layout.PRESETS))
def test_every_preset_fits_its_canvas(fmt):
    e = layout.resolve(EDIT, fmt)
    w, size = e["window"], e["size"]
    assert w["x"] >= 0 and w["y"] >= 0 and w["x"] + w["w"] <= size[0] and w["y"] + w["h"] <= size[1]
    c = e["layout"]["caption"]
    assert c["left"] + c["width"] <= size[0] and c["top"] + c["height"] <= size[1]
    if fmt == "16:9":
        assert c["left"] + c["width"] <= w["x"]                       # caption beside the window
    else:
        assert c["top"] + c["height"] <= w["y"]                       # caption above the window
    assert e["window"]["url"] == "x.com"

def test_own_format_keeps_the_edits_window_other_formats_use_presets():
    own = layout.resolve(EDIT)
    assert own["format"] == "4:5" and own["window"]["y"] == 356 and own["build"] == "build"
    sq = layout.resolve(EDIT, "1:1")
    assert sq["size"] == [1080, 1080] and sq["build"] == "build/1x1" and sq["baseBuild"] == "build"

def test_shots_take_their_per_format_adjustments():
    assert layout.resolve(EDIT, "4:5")["shots"]["a"] == {"fit": ["r"], "dy": -100}
    assert layout.resolve(EDIT, "1:1")["shots"]["a"] == {"fit": ["r"], "dy": 20}
    assert layout.resolve(EDIT, "16:9")["shots"]["a"] == {"fit": ["r"], "dy": -100, "pad": 5}

def test_unknown_format_is_refused():
    with pytest.raises(ValueError, match="unknown format"):
        layout.resolve(EDIT, "2:1")

# ---- subtitles -----------------------------------------------------------------------------------
def words(spec):
    out, t = [], 0.0
    for token in spec.split():
        if token.startswith("|"):           # a pause
            t += float(token[1:]); continue
        out.append({"text": token, "start": t, "end": t + 0.3}); t += 0.35
    return out

def test_cues_break_at_sentences_pauses_and_length():
    cues = subtitles.group(words("Hello there. This is |1.0 after a pause and then a rather long line that goes on and on"))
    texts = [c["text"] for c in cues]
    assert texts[0] == "Hello there."
    assert texts[1] == "This is"
    assert all(len(t) <= subtitles.MAX_CHARS + 14 for t in texts)
    assert " ".join(texts).split() == "Hello there. This is after a pause and then a rather long line that goes on and on".split()

def test_a_sentence_end_just_past_the_limit_is_kept_together():
    cues = subtitles.group(words("and he checks to see if it is robbers or just wind."))
    assert cues[-1]["text"].endswith("wind.") and len(cues[-1]["text"].split()) > 2

def test_cues_never_cross_a_scene_change():
    w = words("one two three four")                         # 0.0, 0.35, 0.70, 1.05
    cues = subtitles.group(w, bounds=[0.70 + 0.45])
    assert [c["text"] for c in cues] == ["one two", "three four"]

def test_srt_round_trip(tmp_path):
    cues = [{"start": 1.5, "end": 3.25, "text": "First line."}, {"start": 3661.0, "end": 3662.5, "text": "Later"}]
    subtitles.write_srt(cues, tmp_path / "x.srt")
    text = (tmp_path / "x.srt").read_text()
    assert "00:00:01,500 --> 00:00:03,250" in text and "01:01:01,000 --> 01:01:02,500" in text
    back = subtitles.read_srt(tmp_path / "x.srt")
    assert back == cues

def test_read_srt_accepts_hand_edits(tmp_path):
    (tmp_path / "x.srt").write_text("1\n00:00:01.000 --> 00:00:02.000\nTwo\nlines\n\n\n2\n00:00:03,000 --> 00:00:04,000\n\n")
    assert subtitles.read_srt(tmp_path / "x.srt") == [{"start": 1.0, "end": 2.0, "text": "Two lines"}]
