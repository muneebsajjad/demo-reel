"""Compose the final video from an edit file: the recorded take framed in a window on a brand
background, a camera that moves between shots, captions, key toasts, still cards, image scenes,
and the take's own sound cut to match.

    python compose/compose.py edit.json [--out renders/demo.mp4] [--stills 1.2,6.5,...]

--stills writes PNGs of those output times to <build>/stills/ instead of rendering the video:
use it to check framing before the full render. See docs/edit-format.md for the edit file.
"""
import json, math, pathlib, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

args = sys.argv[1:]
EDIT_PATH = pathlib.Path(args[0]).resolve()
BASE = EDIT_PATH.parent
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import layout
FORMAT = args[args.index("--format") + 1] if "--format" in args else None
EDIT = layout.resolve(json.loads(EDIT_PATH.read_text()), FORMAT)
BUILD = BASE / EDIT.get("build", "build")
LAYERS = BUILD / "layers"
OUT = pathlib.Path(args[args.index("--out") + 1]).resolve() if "--out" in args else \
    BASE / "renders" / f"demo-{layout.slug(EDIT['format'])}.mp4"
STILLS = [float(x) for x in args[args.index("--stills") + 1].split(",")] if "--stills" in args else None
# --audio-only <video>: rebuild only the sound (e.g. another music track) onto an existing render
AUDIO_ONLY = pathlib.Path(args[args.index("--audio-only") + 1]).resolve() if "--audio-only" in args else None
CREDITS = OUT.with_suffix(".credits.txt")
# --pick-music [N]: only choose music for this video (write <build>/music-choice.json), no render
PICK_ONLY = "--pick-music" in args
PICK_COUNT = int(args[args.index("--pick-music") + 1]) if PICK_ONLY and len(args) > args.index("--pick-music") + 1 \
    and args[args.index("--pick-music") + 1].isdigit() else 3
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import music

import validate as _validate
_problems = _validate.validate(EDIT, BASE)
if _problems:
    print(f"{EDIT_PATH.name}: {len(_problems)} problem{'s' * (len(_problems) != 1)}")
    for _p in _problems: print("  -", _p)
    sys.exit(1)

W, H = EDIT.get("size", [1080, 1350])
FPS = EDIT.get("fps", 30)
XF = EDIT.get("transition", 0.4)
TAKE = BASE / (EDIT["take"] + ".mov")
LOG = json.loads((BASE / (EDIT["take"] + ".json")).read_text())
VP = LOG["viewport"]                                   # page viewport inside the recording, px
PAGE = (VP["x"], VP["y"], VP["width"], VP["height"])
RECTS = LOG.get("rects", {})
WIN = EDIT["window"]
VX, VY = WIN["x"], WIN["y"] + WIN["bar"]
VW, VH = WIN["w"], WIN["h"] - WIN["bar"]
ASPECT = VW / VH
SCENES = json.loads((LAYERS / "index.json").read_text())   # scenes with layer ids filled in

def load(path):
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255

BG = load(LAYERS / "bg.png")

m = Image.new("L", (VW, VH), 0)
ImageDraw.Draw(m).rounded_rectangle([0, -40, VW - 1, VH - 1], radius=WIN["r"], fill=255)
VMASK = (np.asarray(m).astype(np.float32) / 255)[..., None]

from timeline import ease, src_time
import timeline

GEO = timeline.Frame(PAGE[2], PAGE[3], ASPECT, RECTS, EDIT.get("shots", {}))
EVENTS = LOG.get("events", [])
TOTAL = timeline.build(SCENES, EVENTS)

class Reader:
    """Frames of the take's page viewport from `start`, in order, at FPS."""
    def __init__(self, start, dur):
        self.start, (x, y, w, h) = start, PAGE
        self.size = (w, h)
        self.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{max(0, start):.3f}", "-i", str(TAKE),
                                   "-t", f"{dur:.3f}", "-vf", f"fps={FPS},crop={w}:{h}:{x}:{y}",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)      # it is fine to stop reading early
        self.n, self.cur = -1, None
    def at(self, t):
        want = max(0, round((t - max(0, self.start)) * FPS))
        while self.n < want:
            buf = self.p.stdout.read(self.size[0] * self.size[1] * 3)
            if len(buf) < self.size[0] * self.size[1] * 3: break
            self.cur = Image.frombuffer("RGB", self.size, buf, "raw", "RGB", 0, 1)
            self.n += 1
        return self.cur

readers = {}
def take_view(si, local):
    s = SCENES[si]
    st = src_time(s, local)
    acc, piece = 0, len(s["take"]) - 1
    for i, (a, b) in enumerate(s["take"]):
        if local <= acc + (b - a): piece = i; break
        acc += b - a
    if (si, piece) not in readers:
        a, b = s["take"][piece]
        readers[(si, piece)] = Reader(a - XF, (b - a) + 2 * XF + 0.3)
    img = readers[(si, piece)].at(st)
    view = img.resize((VW, VH), Image.LANCZOS, box=GEO.box(*GEO.camera(s["camera"], st)))
    return np.asarray(view).astype(np.float32) / 255

def window_with(view):
    out = BG[..., :3].copy()
    out[VY:VY + VH, VX:VX + VW] = out[VY:VY + VH, VX:VX + VW] * (1 - VMASK) + view * VMASK
    return out

def over(dst, src, alpha=1.0, dy=0):
    if dy: src = np.roll(src, int(round(dy)), 0)
    a = src[..., 3:4] * alpha
    return dst * (1 - a) + src[..., :3] * a

def push(layer, k):
    if abs(k - 1) < 1e-4: return layer[..., :3]
    im = Image.fromarray((layer[..., :3] * 255).astype(np.uint8))
    w, h = W / k, H / k
    im = im.resize((W, H), Image.LANCZOS, box=((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2))
    return np.asarray(im).astype(np.float32) / 255

# ---- image scenes: stills of the product over the dimmed window, optionally revealing a second ---
class ImageScene:
    def __init__(self, s):
        self.s = s
        width = s.get("width", 480)
        # no taller than 92% of the window: measure the tallest image at this width, shrink if needed
        tallest = max(Image.open(BASE / p).size[1] / Image.open(BASE / p).size[0] for p in s["images"])
        width = int(min(width, VH * 0.92 / tallest * 1.08))     # the empty bottom is trimmed below
        ims = []
        for p in s["images"]:
            im = Image.open(BASE / p).convert("RGB")
            a = np.asarray(im).astype(int)
            bgc = a[-1, a.shape[1] // 2]
            rows = np.where(np.abs(a - bgc).sum(2).max(1) > 12)[0]       # trim empty bottom
            im = im.crop((0, 0, im.width, min(im.height, rows.max() + im.width // 20)))
            ims.append(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS))
        self.h = max(i.height for i in ims)
        def padded(i):                       # same height for all, filled with each one's own background
            a = np.asarray(i).astype(np.float32) / 255
            if a.shape[0] < self.h:
                a = np.concatenate([a, np.repeat(a[-1:], self.h - a.shape[0], 0)])
            return a
        self.imgs = [padded(i) for i in ims]
        self.w = width
        self.x, self.y = VX + (VW - width) // 2, VY + (VH - self.h) // 2     # centred in the window
        pm = Image.new("L", (width, self.h), 0)
        ImageDraw.Draw(pm).rounded_rectangle([0, 0, width - 1, self.h - 1], radius=16, fill=255)
        self.mask = np.asarray(pm).astype(np.float32)[..., None] / 255
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle([self.x, self.y + 18, self.x + width, self.y + self.h + 18], radius=18, fill=150)
        self.shadow = np.asarray(sh.filter(ImageFilter.GaussianBlur(26))).astype(np.float32)[..., None] / 255
        rv = s.get("reveal")
        if rv:
            k = width / rv.get("srcWidth", width)
            yy, xx = np.mgrid[0:self.h, 0:width]
            self.dist = np.hypot(xx - rv["from"][0] * k, yy - rv["from"][1] * k)
        self.backdrop = None
    def frame(self, local, behind):
        if self.backdrop is None:
            if behind is not None:
                im = Image.fromarray((behind * 255).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
                self.backdrop = window_with(np.asarray(im).astype(np.float32) / 255)
            else:
                self.backdrop = BG[..., :3].copy()
        base = self.backdrop.copy()
        dim = ease(local / 0.5) * 0.28
        v = base[VY:VY + VH, VX:VX + VW]
        base[VY:VY + VH, VX:VX + VW] = v * (1 - dim * VMASK) + 0.06 * dim * VMASK
        base = base * (1 - self.shadow * 0.55 * ease(local / 0.5))
        img = self.imgs[0]
        rv = self.s.get("reveal")
        if rv and len(self.imgs) > 1:
            r = ease((local - rv["at"]) / rv.get("dur", 0.75)) * (math.hypot(self.w, self.h) + 10)
            k = np.clip((r - self.dist) / 2.5, 0, 1)[..., None]
            img = self.imgs[0] * (1 - k) + self.imgs[1] * k
        a = ease(local / 0.4)
        y0 = int(self.y + (1 - ease(local / 0.45)) * 24)
        reg = base[y0:y0 + self.h, self.x:self.x + self.w]
        base[y0:y0 + self.h, self.x:self.x + self.w] = reg * (1 - self.mask * a) + img * self.mask * a
        return base

images = {i: ImageScene(s) for i, s in enumerate(SCENES) if "images" in s}
cards = {s["card"]: load(LAYERS / f"{s['card']}.png") for s in SCENES if s.get("card")}
SUBS = json.loads((LAYERS / "subtitles.json").read_text()) if (LAYERS / "subtitles.json").exists() else []
overlays = {c["id"]: load(LAYERS / f"{c['id']}.png") for c in SUBS}
for s in SCENES:
    for c in s.get("captions", []) + s.get("toasts", []):
        overlays[c["id"]] = load(LAYERS / f"{c['id']}.png")

last_view = None                     # the most recent window content, for image scenes to sit over
def scene_frame(si, local):
    global last_view
    s = SCENES[si]
    if s.get("card"):
        k = s.get("push", 0.022)
        if si == len(SCENES) - 1: return push(cards[s["card"]], 1 + k - k * ease(local / 1.2))
        return push(cards[s["card"]], 1 + k * ease(local / s["dur"]))
    if "take" in s:
        v = take_view(si, local)
        last_view = v
        return window_with(v)
    return images[si].frame(local, last_view)

DIP = None
def frame(t):
    global DIP
    if DIP is None:
        col = np.array(EDIT.get("dip", [205, 219, 234]), np.float32) / 255
        DIP = window_with(np.ones((VH, VW, 3), np.float32) * col)
    out = None
    for si in range(1, len(SCENES)):
        b = SCENES[si]["start"]
        if abs(t - b) < XF / 2 and "take" in SCENES[si] and "take" in SCENES[si - 1]:
            # two parts of the take: dip through the page colour rather than overlap two layouts
            k = abs(t - b) / (XF / 2)
            j = si if t >= b else si - 1
            out = DIP * (1 - ease(k)) + scene_frame(j, t - SCENES[j]["start"]) * ease(k)
            break
    if out is None:
        acc, wsum = None, 0
        for si, s in enumerate(SCENES):
            a, b = s["start"] - XF / 2, s["start"] + s["dur"] + XF / 2
            if si == 0: a = 0
            if si == len(SCENES) - 1: b = TOTAL + 1
            if not (a <= t < b): continue
            w = min(1, (t - a) / XF if si else 1, (b - t) / XF if si < len(SCENES) - 1 else 1)
            f = scene_frame(si, t - s["start"]) * w
            acc, wsum = (f if acc is None else acc + f), wsum + w
        out = acc / max(wsum, 1e-6)
    for c in SUBS:
        if c["start"] - 0.1 <= t <= c["end"] + 0.1:
            a = min(1, (t - c["start"] + 0.1) / 0.1, (c["end"] + 0.1 - t) / 0.1)
            if a > 0: out = over(out, overlays[c["id"]], a)
    for s in SCENES:
        for c in s.get("captions", []):
            t0, t1 = s["start"] + c["at"], s["start"] + c["until"]
            if t0 <= t <= t1 + 0.3:
                a = ease((t - t0) / 0.45) * (1 - ease((t - t1) / 0.3))
                if a > 0: out = over(out, overlays[c["id"]], a, (1 - ease((t - t0) / 0.5)) * 18)
        for c in s.get("toasts", []):
            t0, t1 = s["start"] + c["at"], s["start"] + c["until"]
            if t0 <= t <= t1 + 0.3:
                a = ease((t - t0) / 0.3) * (1 - ease((t - t1) / 0.3))
                if a > 0: out = over(out, overlays[c["id"]], a, (1 - ease((t - t0) / 0.35)) * 14)
    return out

# ---- sound -----------------------------------------------------------------------------------
def auto_music(spec, voice, sr):
    """Choose a bed for this video (or reuse the choice already made) and return a music block."""
    import autopick
    choice_file = BUILD / "music-choice.json"
    p = autopick.profile(EDIT, SCENES, voice, sr, TOTAL)
    if spec.get("mood"): p = autopick.profile({"audio": {"music": spec}}, SCENES, voice, sr, TOTAL)
    if choice_file.exists() and not PICK_ONLY:
        choice = json.loads(choice_file.read_text())
        if pathlib.Path(choice["file"]).exists():
            print(f"music (auto, chosen before): {choice['title']}  — delete {choice_file.name} to choose again")
            return {**spec, "file": choice["file"], "gainDb": spec.get("gainDb", choice["gainDb"])}
    print(f"video: {p['length']:.0f}s, voice {p['voice']:.0%} of it, {p['pace']} changes/min -> "
          f"mood {p['mood']}, energy {p['energy']}, {p['bpm'][0]}-{p['bpm'][1]} bpm")
    folders = [BASE / f for f in spec.get("folders", ["music"])]
    ranked = autopick.pick(p, folders, online=spec.get("online", "auto"), count=PICK_COUNT)
    if not ranked:
        if PICK_ONLY: raise SystemExit("no usable music found: add your own with `reel music add`, or set music to null")
        print("music: nothing suitable found; rendering without music"); return None
    usable = [e for e in ranked if e[3] is not None]
    show = ranked[:PICK_COUNT] + [e for e in usable[:1] if e not in ranked[:PICK_COUNT]]
    for e in show: print(f"  {ranked.index(e) + 1}. " + autopick.describe(e, p))
    ranked = show
    gain = spec.get("gainDb", -20 if p["voice"] > 0.1 else -12)       # alone, the bed carries the video
    shortlist = [dict(file=str(e[3]) if e[3] else None, title=e[4]["title"], artist=e[4].get("artist"),
                      source=e[4].get("source"), license=e[4].get("license"), score=e[0], features=e[2])
                 for e in ranked]
    BUILD.mkdir(parents=True, exist_ok=True)
    if not usable:
        choice_file.write_text(json.dumps(dict(file=None, profile=p, shortlist=shortlist), indent=2, default=str))
        msg = ("none of the best matches can be downloaded by script. Download one from its link, then "
               "`reel music add <file> --candidate N` (N from the list above) and render again.")
        if PICK_ONLY: raise SystemExit(msg)
        print("music: " + msg + " Rendering without music for now.")
        return None
    best = usable[0]
    choice = dict(file=str(best[3]), title=best[4]["title"], gainDb=gain, profile=p, shortlist=shortlist)
    choice_file.write_text(json.dumps(choice, indent=2, default=str))
    return {**spec, "file": choice["file"], "gainDb": gain}

def soundtrack():
    sr = 48000
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(TAKE), "-vn", "-ac", "2", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    src = np.frombuffer(raw, np.float32).reshape(-1, 2) if raw else np.zeros((sr, 2), np.float32)
    out = np.zeros((int((TOTAL + 0.5) * sr), 2), np.float32)
    for s in SCENES:
        if "take" not in s: continue
        o = s["start"]
        for a, b in s["take"]:
            lead = max(0, int(-a * sr))                     # a piece may start before the recording
            seg = np.concatenate([np.zeros((lead, 2), np.float32), src[max(0, int(a * sr)):int(b * sr)]])
            n = min(len(seg) // 2, int(0.06 * sr))
            if n: seg[:n] *= np.linspace(0, 1, n)[:, None]; seg[-n:] *= np.linspace(1, 0, n)[:, None]
            out[int(o * sr):int(o * sr) + len(seg)] += seg[:len(out) - int(o * sr)]
            o += b - a
    voice = out.copy()
    # no music block: the system picks; "music": null: none; a file: yours
    spec = EDIT.get("audio", {}).get("music", "auto")
    if PICK_ONLY or spec == "auto" or (isinstance(spec, dict) and spec.get("auto")):
        spec = auto_music(spec if isinstance(spec, dict) and spec.get("auto") else {}, voice, sr)
    if PICK_ONLY: sys.exit()
    if spec:
        rec = music.load(spec, BASE)
        info = music.check(rec, allow=set(spec.get("allow", [])))
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(rec["path"]), "-ac", "2", "-ar", str(sr),
                              "-f", "f32le", "-"], capture_output=True).stdout
        if not raw: raise SystemExit(f"could not read music {rec['path']}")
        mus = music.fit(np.frombuffer(raw, np.float32).reshape(-1, 2), len(out), sr,
                        start=spec.get("start", 0.0), fade_out=spec.get("fade", 1.5))
        mus *= 10 ** (spec.get("gainDb", -20) / 20)
        if np.abs(voice).max() > 1e-3:                      # only duck when there is something to duck for
            mus *= music.speech_gain(voice, sr, duck_db=spec.get("duckDb", -12))
        out += mus
        CREDITS.write_text(music.credits_text(rec, info))
        print(f"music: {rec.get('title', rec['path'].name)} ({info['name']}); credits in {CREDITS}")
        if info["credit"]: print("  this licence needs the credit published with the video: see the credits file")
        if info.get("note"): print("  note:", info["note"])
    path = BUILD / "soundtrack.wav"
    with wave.open(str(path), "w") as wv:
        wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(sr)
        wv.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())
    return path

def loudnorm_args(path, target):
    """One fixed gain to reach `target` LUFS, then a peak limiter at -1 dBFS. (ffmpeg's loudnorm
    quietly turns dynamic when it cannot stay linear, which pumps music up in the pauses.)"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "highpass=f=70,ebur128",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])
    return f"volume={target - i:.2f}dB,alimiter=limit=0.891:attack=5:release=60:level=false"

if STILLS:
    (BUILD / "stills").mkdir(parents=True, exist_ok=True)
    for t in STILLS:
        # image scenes need the window content that came before them
        for si, s in enumerate(SCENES):
            if "take" in s and s["start"] + s["dur"] <= t: scene_frame(si, s["dur"] - 0.01)
        Image.fromarray((frame(t) * 255).clip(0, 255).astype(np.uint8)).save(BUILD / "stills" / f"{t:06.2f}.png")
        readers.clear()
        print("still", t)
    sys.exit()

OUT.parent.mkdir(parents=True, exist_ok=True)
CREDITS.unlink(missing_ok=True)
try:
    audio = soundtrack()
except music.LicenseError as e:
    raise SystemExit(f"music refused: {e}")
target = EDIT.get("audio", {}).get("loudness", -16)
silent = np.abs(np.frombuffer(open(audio, "rb").read()[44:], np.int16)).max() < 30
af = "aresample=48000" if silent else f"highpass=f=70,{loudnorm_args(audio, target)},aresample=48000"
if AUDIO_ONLY:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(AUDIO_ONLY), "-i", str(audio), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", str(OUT.with_name("." + OUT.name + ".part.mp4"))], check=True)
    OUT.with_name("." + OUT.name + ".part.mp4").replace(OUT)
    print("wrote", OUT)
    sys.exit()
PART = OUT.with_name(f".{OUT.stem}.{__import__('os').getpid()}.part.mp4")   # written here, renamed when done
SRT = BASE / EDIT["baseBuild"] / "subtitles.srt"
if SRT.exists():                                    # always offer the caption file beside the video
    import shutil; shutil.copy(SRT, OUT.with_suffix(".srt")); print("subtitles:", OUT.with_suffix(".srt"))
enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio), "-af", af,
                        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(PART)],
                       stdin=subprocess.PIPE)
n = int(round(TOTAL * FPS))
rng = np.random.default_rng(0)
for i in range(n):
    f = frame(i / FPS) + (rng.random((H, W, 1), np.float32) - 0.5) / 255     # dither: no banding
    enc.stdin.write((f * 255).clip(0, 255).astype(np.uint8).tobytes())
    if i % 90 == 0: print(f"frame {i}/{n}", flush=True)
enc.stdin.close()
if enc.wait() != 0: raise SystemExit(f"encoding failed; {OUT} was left as it was")
PART.replace(OUT)                                   # only a finished render ever takes the name
print("wrote", OUT, f"{TOTAL:.2f}s")
