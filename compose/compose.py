"""Compose the final video from an edit file: the recorded take framed in a window on a brand
background, a camera that moves between shots, captions, key toasts, still cards, image scenes,
and the take's own sound cut to match.

    python compose/compose.py edit.json [--out renders/demo.mp4] [--stills 1.2,6.5,...]

--stills writes PNGs of those output times to <build>/stills/ instead of rendering the video:
use it to check framing before the full render. See docs/edit-format.md for the edit file.
"""
import json, math, pathlib, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

args = sys.argv[1:]
EDIT_PATH = pathlib.Path(args[0]).resolve()
BASE = EDIT_PATH.parent
EDIT = json.loads(EDIT_PATH.read_text())
BUILD = BASE / EDIT.get("build", "build")
LAYERS = BUILD / "layers"
OUT = pathlib.Path(args[args.index("--out") + 1]).resolve() if "--out" in args else BASE / "renders" / "demo.mp4"
STILLS = [float(x) for x in args[args.index("--stills") + 1].split(",")] if "--stills" in args else None

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

def ease(x):
    x = min(1, max(0, x))
    return x * x * x * (x * (6 * x - 15) + 10)

# ---- shots: where the camera looks, in page viewport pixels -----------------------------------
def rect_of(ref):
    if isinstance(ref, str): ref = {"rect": ref}
    if "rect" in ref:
        r = RECTS[ref["rect"]]
        x, y, w, h = r["x"], r["y"], r["width"], r["height"]
    else:
        x, y, w, h = ref["x"], ref["y"], ref["width"], ref["height"]
    return (x + ref.get("dx", 0), y + ref.get("dy", 0), w + ref.get("dw", 0), h + ref.get("dh", 0))

def clamp_shot(cx, cy, w):
    w = min(w, PAGE[2], PAGE[3] * ASPECT)
    h = w / ASPECT
    return (min(PAGE[2] - w / 2, max(w / 2, cx)), min(PAGE[3] - h / 2, max(h / 2, cy)), w)

def shot(spec):
    if isinstance(spec, str): spec = EDIT["shots"][spec]
    if "fit" in spec:
        boxes = [rect_of(r) for r in spec["fit"]]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
        p = spec.get("pad", 60)
        x0 -= p; y0 -= p; x1 += p; y1 += p
        w = max(x1 - x0, (y1 - y0) * ASPECT, spec.get("minWidth", 0))
        cy = (y0 + y1) / 2 + spec.get("dy", 0)
        return clamp_shot((x0 + x1) / 2 + spec.get("dx", 0), cy, w)
    return clamp_shot(spec["cx"], spec["cy"], spec["w"])

def camera(keys, t):
    keys = [(k[0], shot(k[1])) for k in keys]
    if t <= keys[0][0]: return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            u = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1
            w = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * u)   # even-feeling zoom
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, w)
    return keys[-1][1]

# ---- take times: seconds, or anchored to logged events ---------------------------------------
import re
EVENTS = LOG.get("events", [])
def T(v):
    """12.5 | "sentence#5-0.15" (6th 'sentence' event, minus 0.15s) | "read+1" | "zoom on"."""
    if isinstance(v, (int, float)): return float(v)
    m = re.fullmatch(r"\s*(.+?)(?:#(\d+))?\s*([+-]\s*\d+(?:\.\d+)?)?\s*", v)
    if not m: raise ValueError(f"bad time {v!r}")
    hits = [e for e in EVENTS if e["name"] == m.group(1)]
    k = int(m.group(2) or 0)
    if k >= len(hits): raise ValueError(f"{v!r}: only {len(hits)} '{m.group(1)}' events in the take")
    return hits[k]["t"] + float((m.group(3) or "0").replace(" ", ""))

for s in SCENES:
    if "take" in s:
        s["take"] = [[T(a), T(b)] for a, b in s["take"]]
        s["camera"] = [[T(t), sh] for t, sh in s["camera"]]

# ---- timeline --------------------------------------------------------------------------------
t = 0
for s in SCENES:
    if "take" in s: s["dur"] = sum(b - a for a, b in s["take"])
    s["start"], t = t, t + s["dur"]
    for c in s.get("captions", []) + s.get("toasts", []):     # negative: seconds before the scene ends
        if c["until"] < 0: c["until"] += s["dur"]
TOTAL = t

def src_time(s, local):
    for a, b in s["take"]:
        if local <= b - a: return a + local
        local -= b - a
    return s["take"][-1][1] + local

class Reader:
    """Frames of the take's page viewport from `start`, in order, at FPS."""
    def __init__(self, start, dur):
        self.start, (x, y, w, h) = start, PAGE
        self.size = (w, h)
        self.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{max(0, start):.3f}", "-i", str(TAKE),
                                   "-t", f"{dur:.3f}", "-vf", f"fps={FPS},crop={w}:{h}:{x}:{y}",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
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
    cx, cy, w = clamp_shot(*camera(s["camera"], st))
    h = w / ASPECT
    box = (max(0.0, cx - w / 2), max(0.0, cy - h / 2), min(PAGE[2], cx + w / 2), min(PAGE[3], cy + h / 2))
    view = img.resize((VW, VH), Image.LANCZOS, box=box)
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
        self.x, self.y = (W - width) // 2, VY + (VH - self.h) // 2
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
overlays = {}
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
    music = EDIT.get("audio", {}).get("music")
    if music:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(BASE / music["file"]), "-ac", "2", "-ar", str(sr),
                              "-f", "f32le", "-"], capture_output=True).stdout
        mus = np.frombuffer(raw, np.float32).reshape(-1, 2)[:len(out)].copy()
        mus *= 10 ** (music.get("gainDb", -22) / 20)
        f = int(music.get("fade", 1.5) * sr)
        mus[-f:] *= np.linspace(1, 0, f)[:, None]
        out[:len(mus)] += mus
    path = BUILD / "soundtrack.wav"
    with wave.open(str(path), "w") as wv:
        wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(sr)
        wv.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())
    return path

def loudnorm_args(path, target):
    """Two-pass loudness: measure, then apply linearly, so speech is not pumped."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                        f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    return (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")

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
audio = soundtrack()
target = EDIT.get("audio", {}).get("loudness", -16)
silent = np.abs(np.frombuffer(open(audio, "rb").read()[44:], np.int16)).max() < 30
af = "aresample=48000" if silent else f"highpass=f=70,{loudnorm_args(audio, target)},aresample=48000"
enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio), "-af", af,
                        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(OUT)],
                       stdin=subprocess.PIPE)
n = int(round(TOTAL * FPS))
rng = np.random.default_rng(0)
for i in range(n):
    f = frame(i / FPS) + (rng.random((H, W, 1), np.float32) - 0.5) / 255     # dither: no banding
    enc.stdin.write((f * 255).clip(0, 255).astype(np.uint8).tobytes())
    if i % 90 == 0: print(f"frame {i}/{n}", flush=True)
enc.stdin.close(); enc.wait()
print("wrote", OUT, f"{TOTAL:.2f}s")
