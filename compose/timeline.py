"""The pure parts of an edit: times, shots, the camera and the scene timeline. No I/O, so the
compositor, the validator and the tests share one implementation."""
import math, re

def ease(x):
    """Smooth step (zero velocity and acceleration at both ends), clamped to 0..1."""
    x = min(1, max(0, x))
    return x * x * x * (x * (6 * x - 15) + 10)

# ---- times -------------------------------------------------------------------------------------
TIME = re.compile(r"\s*(.+?)(?:#(\d+))?\s*([+-]\s*\d+(?:\.\d+)?)?\s*")

def take_time(v, events):
    """A take time: seconds (12.5), or an event anchor: "sentence#5-0.15" is 0.15 s before the 6th
    'sentence' event; "read+1" is a second after the first 'read'; "zoom on" is that event."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError(f"time must be seconds or an event anchor, not {v!r}")
    if isinstance(v, (int, float)): return float(v)
    m = TIME.fullmatch(v)
    if not m: raise ValueError(f"bad time {v!r}")
    hits = [e for e in events if e["name"] == m.group(1)]
    k = int(m.group(2) or 0)
    if k >= len(hits):
        raise ValueError(f"{v!r}: the take has {len(hits)} '{m.group(1)}' event{'s' * (len(hits) != 1)}")
    return hits[k]["t"] + float((m.group(3) or "0").replace(" ", ""))

def build(scenes, events):
    """Resolve take times, give every scene its start and duration, and make negative caption
    `until`s count back from the scene's end. Returns the total length. Mutates `scenes`."""
    t = 0.0
    for s in scenes:
        if "take" in s:
            s["take"] = [[take_time(a, events), take_time(b, events)] for a, b in s["take"]]
            s["camera"] = [[take_time(k, events), sh] for k, sh in s["camera"]]
            s["dur"] = sum(b - a for a, b in s["take"])
        s["start"], t = t, t + s["dur"]
        for c in s.get("captions", []) + s.get("toasts", []):
            if c["until"] < 0: c["until"] += s["dur"]
    return t

def src_time(scene, local):
    """Scene-local output seconds -> take seconds, across the scene's pieces."""
    for a, b in scene["take"]:
        if local <= b - a: return a + local
        local -= b - a
    return scene["take"][-1][1] + local

# ---- shots and camera --------------------------------------------------------------------------
class Frame:
    """The page viewport of a take (width, height in px) seen through a window of `aspect`."""
    def __init__(self, page_w, page_h, aspect, rects, shots):
        self.pw, self.ph, self.aspect, self.rects, self.shots = page_w, page_h, aspect, rects, shots

    def rect(self, ref):
        if isinstance(ref, str): ref = {"rect": ref}
        if "rect" in ref:
            if ref["rect"] not in self.rects: raise KeyError(f"no rect {ref['rect']!r} in the take")
            r = self.rects[ref["rect"]]
            x, y, w, h = r["x"], r["y"], r["width"], r["height"]
        else:
            x, y, w, h = ref["x"], ref["y"], ref["width"], ref["height"]
        return (x + ref.get("dx", 0), y + ref.get("dy", 0), w + ref.get("dw", 0), h + ref.get("dh", 0))

    def clamp(self, cx, cy, w):
        """Keep a framing inside the page: no wider than it fits, centre pulled in from the edges."""
        w = min(w, self.pw, self.ph * self.aspect)
        h = w / self.aspect
        return (min(self.pw - w / 2, max(w / 2, cx)), min(self.ph - h / 2, max(h / 2, cy)), w)

    def shot(self, spec):
        if isinstance(spec, str):
            if spec not in self.shots: raise KeyError(f"no shot {spec!r} in the edit")
            spec = self.shots[spec]
        if "fit" in spec:
            boxes = [self.rect(r) for r in spec["fit"]]
            p = spec.get("pad", 60)
            x0 = min(b[0] for b in boxes) - p; y0 = min(b[1] for b in boxes) - p
            x1 = max(b[0] + b[2] for b in boxes) + p; y1 = max(b[1] + b[3] for b in boxes) + p
            w = max(x1 - x0, (y1 - y0) * self.aspect, spec.get("minWidth", 0))
            return self.clamp((x0 + x1) / 2 + spec.get("dx", 0), (y0 + y1) / 2 + spec.get("dy", 0), w)
        return self.clamp(spec["cx"], spec["cy"], spec["w"])

    def camera(self, keys, t):
        """Where the camera looks at take time t: eased between keys, zooming evenly in log width."""
        keys = [(k[0], self.shot(k[1])) for k in keys]
        if t <= keys[0][0]: return keys[0][1]
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t <= t1:
                u = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1
                w = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * u)
                return self.clamp(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, w)
        return keys[-1][1]

    def box(self, cx, cy, w):
        """The crop box for a framing, clamped to the page (float error must not go negative)."""
        h = w / self.aspect
        return (max(0.0, cx - w / 2), max(0.0, cy - h / 2), min(self.pw, cx + w / 2), min(self.ph, cy + h / 2))
