"""Where things go in each output format. One edit renders to any of these; the camera's shots are
fitted around page elements, so they adapt to each window's shape on their own.

    4:5   1080x1350  feeds (LinkedIn, Instagram)    caption above the window
    1:1   1080x1080  square feeds                    caption above, smaller
    9:16  1080x1920  stories, reels, shorts          caption above, tall window
    16:9  1920x1080  YouTube, websites, X            caption beside the window, on the left
"""
import copy

PRESETS = {
    "4:5": dict(size=[1080, 1350],
                window=dict(x=40, y=356, w=1000, h=934, bar=52, r=22),
                caption=dict(left=64, top=76, width=952, height=250, size=58, align="left"),
                toast=dict(bottom=112)),
    "1:1": dict(size=[1080, 1080],
                window=dict(x=40, y=262, w=1000, h=778, bar=48, r=20),
                caption=dict(left=64, top=40, width=952, height=200, size=48, align="left"),
                toast=dict(bottom=84)),
    "9:16": dict(size=[1080, 1920],
                 window=dict(x=40, y=520, w=1000, h=1240, bar=52, r=22),
                 caption=dict(left=64, top=150, width=952, height=320, size=66, align="left"),
                 toast=dict(bottom=230)),
    "16:9": dict(size=[1920, 1080],
                 window=dict(x=760, y=70, w=1110, h=940, bar=52, r=22),
                 caption=dict(left=84, top=0, width=640, height=1080, size=52, align="left"),
                 toast=dict(bottom=150, cx=1315)),
}
DEFAULT = "4:5"

def slug(fmt):
    return fmt.replace(":", "x")

def resolve(edit, fmt=None):
    """The edit laid out for `fmt`. With no format, the edit's own: its "format" (default 4:5), with
    any "size", "window" or "layout" it sets on top. A requested format other than the edit's own
    uses the preset as it is (the edit's custom window was drawn for its own format)."""
    own = edit.get("format", DEFAULT)
    fmt = fmt or own
    if fmt not in PRESETS: raise ValueError(f"unknown format {fmt!r}; formats: {', '.join(PRESETS)}")
    e = copy.deepcopy(edit)
    p = copy.deepcopy(PRESETS[fmt])
    if fmt == own:
        if "size" in edit and edit["size"] != p["size"]:          # a custom canvas: scale the preset to it
            k = edit["size"][0] / p["size"][0]
            p["size"] = edit["size"]
            p["caption"] = {a: (round(v * k) if isinstance(v, (int, float)) else v) for a, v in p["caption"].items()}
            p["toast"] = {a: round(v * k) for a, v in p["toast"].items()}
        if "window" in edit: p["window"].update({k: v for k, v in edit["window"].items() if k != "url"})
        for k, v in edit.get("layout", {}).items(): p[k].update(v)
    url = edit.get("window", {}).get("url", "")
    e["format"] = fmt
    e["size"] = p["size"]
    e["window"] = {**p["window"], "url": url}
    e["layout"] = {"caption": p["caption"], "toast": p["toast"]}
    # a shot may carry per-format adjustments: "para": {"fit": [...], "1:1": {"dy": 20}}
    for name, shot in e.get("shots", {}).items():
        own_adjust = shot.get(fmt, {})
        e["shots"][name] = {**{k: v for k, v in shot.items() if k not in PRESETS}, **own_adjust}
    e["baseBuild"] = edit.get("build", "build")          # format-independent things live here
    if fmt != own:
        e["build"] = f"{edit.get('build', 'build')}/{slug(fmt)}"
    return e
