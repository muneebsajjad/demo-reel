import pytest
import timeline
from timeline import Frame, ease, take_time

EVENTS = [{"t": 1.0, "name": "read"}, {"t": 2.0, "name": "sentence", "n": 0},
          {"t": 5.5, "name": "sentence", "n": 1}, {"t": 9.25, "name": "zoom on"}]

def test_ease_is_clamped_and_smooth():
    assert ease(-1) == 0 and ease(0) == 0 and ease(1) == 1 and ease(2) == 1
    assert ease(0.5) == pytest.approx(0.5)
    assert ease(0.01) < 0.001                       # starts with no speed

@pytest.mark.parametrize("v, want", [
    (3, 3.0), (2.5, 2.5), ("read", 1.0), ("read+1", 2.0), ("sentence#1-0.15", 5.35),
    ("sentence#0", 2.0), ("zoom on", 9.25), ("zoom on + 0.5", 9.75), (" sentence#1 - 1 ", 4.5),
])
def test_take_times(v, want):
    assert take_time(v, EVENTS) == pytest.approx(want)

def test_take_time_errors_say_what_is_there():
    with pytest.raises(ValueError, match="2 'sentence' events"):
        take_time("sentence#2", EVENTS)
    with pytest.raises(ValueError, match="0 'missing' events"):
        take_time("missing", EVENTS)
    with pytest.raises(ValueError):
        take_time(True, EVENTS)
    with pytest.raises(ValueError):
        take_time(None, EVENTS)

def test_build_lays_scenes_end_to_end():
    scenes = [{"card": "title", "dur": 2.0},
              {"take": [["read", "read+3"], [7, 8]], "camera": [["read", "a"]],
               "captions": [{"at": 0.2, "until": -0.5, "text": "x"}]},
              {"card": "end", "dur": 1.5}]
    total = timeline.build(scenes, EVENTS)
    assert [s["start"] for s in scenes] == [0, 2.0, 6.0]
    assert scenes[1]["dur"] == pytest.approx(4.0)
    assert scenes[1]["captions"][0]["until"] == pytest.approx(3.5)       # counted back from the end
    assert scenes[1]["camera"][0][0] == 1.0
    assert total == pytest.approx(7.5)

def test_src_time_crosses_pieces():
    s = {"take": [[1.0, 4.0], [7.0, 8.0]]}
    assert timeline.src_time(s, 0) == 1.0
    assert timeline.src_time(s, 2.9) == pytest.approx(3.9)
    assert timeline.src_time(s, 3.5) == pytest.approx(7.5)              # into the second piece
    assert timeline.src_time(s, 4.5) == pytest.approx(8.5)              # past the end keeps running

# ---- shots ---------------------------------------------------------------------------------------
RECTS = {"title": {"x": 100, "y": 100, "width": 400, "height": 50},
         "card": {"x": 1200, "y": 120, "width": 300, "height": 2}}
SHOTS = {"close": {"cx": 500, "cy": 400, "w": 600},
         "both": {"fit": ["title", {"rect": "card", "dh": 200}], "pad": 20},
         "huge": {"cx": 0, "cy": 0, "w": 99999}}

@pytest.fixture
def geo():
    return Frame(2000, 1000, 1.25, RECTS, SHOTS)

def test_rect_adjustments(geo):
    assert geo.rect("title") == (100, 100, 400, 50)
    assert geo.rect({"rect": "card", "dx": -10, "dh": 200}) == (1190, 120, 300, 202)
    assert geo.rect({"x": 1, "y": 2, "width": 3, "height": 4}) == (1, 2, 3, 4)
    with pytest.raises(KeyError):
        geo.rect("nope")

def test_fit_covers_every_rect_with_padding():
    cx, cy, w = Frame(3000, 1500, 1.25, RECTS, SHOTS).shot("both")
    h = w / 1.25
    assert cx - w / 2 <= 100 - 20 and cx + w / 2 >= 1500 + 20
    assert cy - h / 2 <= 100 - 20 and cy + h / 2 >= 322 + 20

def test_a_fit_too_big_for_the_page_is_clamped(geo):
    cx, cy, w = geo.shot("both")                     # needs 1440 wide; the page allows 1250
    assert w == pytest.approx(1250)

def test_shots_stay_inside_the_page(geo):
    cx, cy, w = geo.shot("huge")
    h = w / 1.25
    assert w <= 1000 * 1.25 and w <= 2000
    assert cx - w / 2 >= 0 and cy - h / 2 >= 0 and cx + w / 2 <= 2000 and cy + h / 2 <= 1000

def test_box_never_goes_negative(geo):
    x0, y0, x1, y1 = geo.box(625 - 1e-12, 500 - 1e-12, 1250)
    assert x0 >= 0 and y0 >= 0 and x1 <= 2000 and y1 <= 1000

def test_camera_holds_then_eases_between_keys(geo):
    keys = [[0, "close"], [2, "close"], [4, "both"]]
    assert geo.camera(keys, -1) == pytest.approx(geo.shot("close"))
    assert geo.camera(keys, 1) == pytest.approx(geo.shot("close"))
    assert geo.camera(keys, 4) == pytest.approx(geo.shot("both"))
    assert geo.camera(keys, 9) == pytest.approx(geo.shot("both"))
    mid = geo.camera(keys, 3)
    a, b = geo.shot("close"), geo.shot("both")
    assert min(a[2], b[2]) < mid[2] < max(a[2], b[2])
    assert mid[2] == pytest.approx((a[2] * b[2]) ** 0.5, rel=1e-6)      # halfway in log width
    with pytest.raises(KeyError):
        geo.camera([[0, "missing"]], 0)
