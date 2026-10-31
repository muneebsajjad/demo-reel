"""End to end: a synthetic take through the real layer renderer and compositor. Checks what the
viewer would notice (the camera frames the right thing, sound lands at the right moment, the video
is the right length) rather than exact pixels, which differ between machines' fonts."""
import json, pathlib, shutil, subprocess, sys
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "layers"))
import render as layers_render

def chrome_available():
    try:
        layers_render.chrome(); return True
    except SystemExit:
        return False

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and chrome_available()), reason="needs ffmpeg and Chrome")

# take: 800x600 at 10 fps; a 100 px "browser bar", then the page with a red box; a beep at 1-2 s
VIEWPORT = {"x": 0, "y": 100, "width": 800, "height": 500}
RED = {"x": 500, "y": 200, "width": 100, "height": 80}

def make_take(d):
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=white:s=800x600:r=10:d=4",
        "-f", "lavfi", "-i", "aevalsrc='if(between(t,1,2),0.5*sin(2*PI*1000*t),0)':s=48000:d=4",
        "-vf", "drawbox=x=0:y=0:w=800:h=100:color=0x333333:t=fill,"
               f"drawbox=x={RED['x']}:y={100 + RED['y']}:w={RED['width']}:h={RED['height']}:color=red:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "take.mov")], check=True)
    (d / "take.json").write_text(json.dumps({"viewport": VIEWPORT, "rects": {"red": {**RED, "t": 0}},
                                             "events": [{"t": 1.0, "name": "beep"}, {"t": 3.5, "name": "stop"}]}))

EDIT = {
    "size": [320, 400], "fps": 10, "take": "take", "transition": 0.2,
    "brand": {"name": "Test", "accent": "#0d9488", "background": ["#ffffff", "#f4fbfa", "#e6f4f1"]},
    "window": {"x": 10, "y": 110, "w": 300, "h": 270, "bar": 20, "r": 8, "url": "example.com"},
    "shots": {"red": {"fit": ["red"], "pad": 20}},
    "scenes": [
        {"take": [["beep-0.5", "beep+1.5"]], "camera": [["beep-0.5", "red"]],
         "captions": [{"at": 0.1, "until": -0.1, "kicker": "Test", "text": "A <b>caption</b>"}]},
        {"card": "end", "dur": 0.6, "end": {"points": ["one"], "pill": "example.com"}},
    ],
    "audio": {"music": None, "loudness": -16},
    "subtitles": {"burn": True},
}

@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    d = tmp_path_factory.mktemp("render")
    make_take(d)
    (d / "edit.json").write_text(json.dumps(EDIT))
    (d / "build").mkdir()
    (d / "build" / "subtitles.srt").write_text("1\n00:00:00,600 --> 00:00:01,400\nA test subtitle\n")
    py = sys.executable
    subprocess.run([py, str(ROOT / "layers/render.py"), str(d / "edit.json")], check=True, capture_output=True)
    out = d / "out.mp4"
    r = subprocess.run([py, str(ROOT / "compose/compose.py"), str(d / "edit.json"), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return out

def frame_at(video, t, w=320, h=400):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(int)

def test_length(rendered):
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(rendered)], capture_output=True, text=True).stdout)
    assert d == pytest.approx(2.6, abs=0.15)

def test_camera_frames_the_red_box(rendered):
    f = frame_at(rendered, 1.7)                        # no subtitle on screen at this moment
    # shot: box 480..620 x 180..300 (pad 20) seen through a 300x250 viewport at (10, 130)
    vx, vy, vw, vh = 10, 130, 300, 250
    red = (f[..., 0] > 180) & (f[..., 1] < 90) & (f[..., 2] < 90)
    red[:vy] = False                                   # not the window's red close button
    ys, xs = np.nonzero(red)
    assert len(xs) > 500, "the red box should fill much of the window"
    assert xs.mean() == pytest.approx(vx + vw / 2, abs=6)
    assert ys.mean() == pytest.approx(vy + vh / 2, abs=6)
    assert (xs.max() - xs.min()) / vw == pytest.approx(100 / 140, abs=0.06)
    assert xs.min() > vx and xs.max() < vx + vw and ys.max() < vy + vh   # all inside the window

def test_the_caption_is_drawn_above_the_window(rendered):
    f = frame_at(rendered, 1.0)
    band = f[60:330, 20:300]                           # where the caption sits (top 76 px + 250)
    assert (band.sum(2) < 200).mean() > 0.002          # some dark caption text

def test_subtitles_are_burned_in_and_exported(rendered):
    vx, vy, vw, vh = 10, 130, 300, 250
    pill = lambda f: (f[vy + vh - 60: vy + vh - 5, vx: vx + vw].sum(2) < 120).mean()   # dark pill near the bottom
    assert pill(frame_at(rendered, 1.0)) > 0.05            # during the cue
    assert pill(frame_at(rendered, 1.9)) < 0.01            # after it
    assert rendered.with_suffix(".srt").read_text().count("A test subtitle") == 1

def test_sound_lands_where_the_edit_puts_it(rendered):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(rendered), "-ac", "1", "-ar", "8000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32)
    rms = lambda t0, t1: float(np.sqrt((a[int(t0 * 8000):int(t1 * 8000)] ** 2).mean()))
    # the beep is at take 1.0-2.0 s; the scene starts at take 0.5 s, so it plays at 0.5-1.5 s
    assert rms(0.65, 1.35) > 0.05
    assert rms(0.0, 0.4) < rms(0.65, 1.35) / 20
    assert rms(1.65, 2.4) < rms(0.65, 1.35) / 20

def test_parallel_chunks_match_a_single_process_render(tmp_path_factory):
    """Rendering in chunks must give the same video as one process: same length, same frames."""
    d = tmp_path_factory.mktemp("parallel")
    make_take(d)
    edit = {**EDIT, "fps": 30, "subtitles": None}
    (d / "edit.json").write_text(json.dumps(edit))
    py = sys.executable
    subprocess.run([py, str(ROOT / "layers/render.py"), str(d / "edit.json")], check=True, capture_output=True)
    outs = {}
    for jobs in (1, 2):
        out = d / f"out{jobs}.mp4"
        r = subprocess.run([py, str(ROOT / "compose/compose.py"), str(d / "edit.json"), "--out", str(out),
                            "--jobs", str(jobs)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        if jobs == 2: assert "2 parallel chunks" in r.stdout
        outs[jobs] = out
    count = lambda v: int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(v)],
                                         capture_output=True, text=True).stdout)
    assert count(outs[1]) == count(outs[2]) == 78
    for t in (0.5, 1.29, 1.31, 2.2):                    # around the chunk boundary (frame 39) and either side
        a, b = frame_at(outs[1], t), frame_at(outs[2], t)
        assert 10 * np.log10(255 ** 2 / max(((a - b) ** 2).mean(), 1e-9)) > 35
