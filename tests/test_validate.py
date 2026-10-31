import copy, json
import pytest
import validate

LOG = {"viewport": {"x": 0, "y": 100, "width": 2000, "height": 1000},
       "events": [{"t": 1.0, "name": "go"}, {"t": 6.0, "name": "go"}],
       "rects": {"title": {"x": 100, "y": 100, "width": 400, "height": 50}}}
EDIT = {
    "take": "take", "size": [1080, 1350],
    "brand": {"accent": "#0d9488", "background": ["#fff", "#eee", "#ddd"]},
    "window": {"x": 40, "y": 356, "w": 1000, "h": 934, "bar": 52, "r": 22},
    "shots": {"t": {"fit": ["title"]}, "fixed": {"cx": 500, "cy": 400, "w": 800}},
    "scenes": [
        {"card": "title", "dur": 2},
        {"take": [["go-0.5", "go#1"]], "camera": [["go", "t"], ["go#1", "fixed"]],
         "captions": [{"at": 0.2, "until": -0.1, "text": "Hello"}],
         "toasts": [{"at": 0.1, "until": 1, "keys": ["Alt", "R"]}]},
        {"card": "end", "dur": 3},
    ],
    "audio": {"music": None},
}

def check(edit):
    return validate.validate(edit, ".", log=LOG)

def broken(change):
    e = copy.deepcopy(EDIT); change(e); return check(e)

def test_a_good_edit_has_no_problems():
    assert check(EDIT) == []

@pytest.mark.parametrize("change, expect", [
    (lambda e: e.pop("take"), "take: missing"),
    (lambda e: e["window"].update(w=2000), "does not fit"),
    (lambda e: e["brand"].update(background=["#fff"]), "brand.background"),
    (lambda e: e["shots"]["t"]["fit"].append("nope"), "shots.t: no rect 'nope'"),
    (lambda e: e["shots"].update(bad={"cx": 1}), "shots.bad: needs either"),
    (lambda e: e["scenes"][1]["camera"].append(["go", "zoom"]), "scenes[1].camera[2]: no shot 'zoom'"),
    (lambda e: e["scenes"][1]["take"][0].__setitem__(1, "go#5"), "the take has 2 'go' events"),
    (lambda e: e["scenes"][1]["take"][0].__setitem__(1, "go-0.9"), "ends (0.10s) before it starts"),
    (lambda e: e["scenes"][1]["take"][0].__setitem__(1, 99), "after the take"),
    (lambda e: e["scenes"][0].update(card="intro"), "not a card template"),
    (lambda e: e["scenes"][0].pop("dur"), "scenes[0].dur"),
    (lambda e: e["scenes"].append({"card": "end", "take": []}), "exactly one of"),
    (lambda e: e["scenes"][1]["captions"][0].update(text=""), "captions[0].text: missing"),
    (lambda e: e["scenes"][1]["captions"][0].update(until=-9), "ends before it starts"),
    (lambda e: e["scenes"][1]["toasts"][0].update(at=20, until=30), "starts after the scene ends"),
    (lambda e: e["scenes"].append({"images": ["missing.png"], "dur": 2}), "missing.png not found"),
    (lambda e: e["audio"].update(music="loud"), 'audio.music: "auto", null'),
    (lambda e: e.update(subtitles={"burn": True, "colour": "red"}), "subtitles: unknown option colour"),
    (lambda e: e.update(formats=["4:5", "21:9"]), "formats: '21:9'"),
    (lambda e: e.update(format="3:2"), "format: '3:2'"),
    (lambda e: e["audio"].update(music={"file": "nope.mp3"}), "audio.music.file: nope.mp3 not found"),
])
def test_problems_are_found_and_located(change, expect):
    problems = broken(change)
    assert any(expect in p for p in problems), problems

def test_music_without_a_licence_is_a_problem(tmp_path):
    (tmp_path / "bed.mp3").write_bytes(b"x")
    e = copy.deepcopy(EDIT); e["audio"]["music"] = {"file": "bed.mp3"}
    problems = validate.validate(e, tmp_path, log=LOG)
    assert any("no licence recorded" in p for p in problems)
    e["audio"]["music"]["license"] = "CC0-1.0"
    assert validate.validate(e, tmp_path, log=LOG) == []

def test_missing_take_files_are_reported(tmp_path):
    problems = validate.validate(EDIT, tmp_path)
    assert any("take.json not found" in p for p in problems)
