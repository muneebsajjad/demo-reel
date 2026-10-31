"""Check an edit file against its take before anything renders.

    python compose/validate.py edit.json        (also run by `reel check` and at the start of a render)

Every problem is reported with where it is ("scenes[2].camera[1]") and what to do, instead of a
traceback halfway through a render.
"""
import copy, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import music, timeline

CARDS = {"title", "end"}

def validate(edit, base, log=None, warnings=None):
    """Return a list of problems (empty when the edit is good). `log` is the take log, if loaded.
    Things that will render but probably not as meant are added to `warnings`, if a list is given."""
    errs = []
    err = errs.append
    warn = warnings.append if warnings is not None else (lambda m: None)
    base = pathlib.Path(base)

    import layout
    if edit.get("format", "4:5") not in layout.PRESETS:
        err(f"format: {edit['format']!r} is not one of {', '.join(layout.PRESETS)}")
    try:
        edit = layout.resolve(edit) if "window" not in edit or "layout" not in edit else edit
    except ValueError as e:
        return errs + [str(e)]
    for key in ["take", "window", "scenes", "brand"]:
        if key not in edit: err(f"{key}: missing")
    if errs: return errs

    if log is None:
        mov, js = base / (edit["take"] + ".mov"), base / (edit["take"] + ".json")
        if not mov.exists(): err(f"take: {mov.name} not found (record one with `reel take`)")
        if not js.exists(): return errs + [f"take: {js.name} not found"]
        log = json.loads(js.read_text())
    events = log.get("events", [])
    take_end = max([e["t"] for e in events], default=0) + 5
    rects = log.get("rects", {})

    w = edit["window"]
    for k in ["x", "y", "w", "h", "bar", "r"]:
        if not isinstance(w.get(k), (int, float)): err(f"window.{k}: missing or not a number")
    size = edit.get("size", [1080, 1350])
    if not errs and (w["x"] + w["w"] > size[0] or w["y"] + w["h"] > size[1]):
        err(f"window: {w['w']}x{w['h']} at ({w['x']},{w['y']}) does not fit the {size[0]}x{size[1]} video")

    b = edit["brand"]
    if not b.get("accent"): err("brand.accent: missing")
    if len(b.get("background", [])) != 3: err("brand.background: needs three colours (centre to edge)")
    for k in ["logo", "toolbarIcon"]:
        if b.get(k) and not (base / b[k]).exists(): err(f"brand.{k}: {b[k]} not found")

    shots = edit.get("shots", {})
    aspect = (w.get("w", 1) / max(1, w.get("h", 2) - w.get("bar", 1))) if isinstance(w.get("w"), (int, float)) else 1
    vp = log.get("viewport", {"width": 1, "height": 1})
    geo = timeline.Frame(vp["width"], vp["height"], aspect, rects, shots)
    for name, spec in shots.items():
        try:
            if "fit" not in spec and not all(k in spec for k in ["cx", "cy", "w"]):
                raise ValueError("needs either \"fit\" or \"cx\", \"cy\" and \"w\"")
            geo.shot(spec)
            over = geo.overflow(spec)
            if over:
                warn(f"shots.{name}: needs {over[0]:.0f} px of page width but a {edit.get('format', '4:5')} window "
                     f"shows at most {over[1]:.0f}; {100 * (1 - over[1] / over[0]):.0f}% will be cut off. "
                     f"Fit fewer things, or adjust it for this format (\"{edit.get('format', '4:5')}\": {{...}})")
        except (KeyError, ValueError) as e:
            have = ", ".join(sorted(rects)) or "none"
            err(f"shots.{name}: {e.args[0]}" + (f" (rects in the take: {have})" if isinstance(e, KeyError) else ""))

    if not isinstance(edit["scenes"], list) or not edit["scenes"]: return errs + ["scenes: must be a non-empty list"]
    scenes = copy.deepcopy(edit["scenes"])
    for i, s in enumerate(scenes):
        at = f"scenes[{i}]"
        kinds = [k for k in ["card", "take", "images"] if k in s]
        if len(kinds) != 1:
            err(f"{at}: needs exactly one of \"card\", \"take\" or \"images\""); continue
        if "card" in s:
            if s["card"] not in CARDS: err(f"{at}.card: {s['card']!r} is not a card template ({', '.join(sorted(CARDS))})")
        if "card" in s or "images" in s:
            if not isinstance(s.get("dur"), (int, float)) or s["dur"] <= 0: err(f"{at}.dur: a positive number of seconds")
        if "images" in s:
            for j, p in enumerate(s["images"]):
                if not (base / p).exists(): err(f"{at}.images[{j}]: {p} not found")
            rv = s.get("reveal")
            if rv and len(s["images"]) < 2: err(f"{at}.reveal: needs two images")
        if "take" in s:
            if not s["take"]: err(f"{at}.take: no pieces")
            for j, piece in enumerate(s["take"]):
                try:
                    a, c = (timeline.take_time(x, events) for x in piece)
                    if c <= a: err(f"{at}.take[{j}]: ends ({c:.2f}s) before it starts ({a:.2f}s)")
                    if c > take_end: err(f"{at}.take[{j}]: ends at {c:.2f}s, after the take")
                except (ValueError, TypeError) as e:
                    err(f"{at}.take[{j}]: {e}")
            if not s.get("camera"): err(f"{at}.camera: at least one [time, shot] key")
            for j, key in enumerate(s.get("camera", [])):
                try:
                    timeline.take_time(key[0], events)
                except (ValueError, TypeError) as e:
                    err(f"{at}.camera[{j}]: {e}")
                if isinstance(key[1], str) and key[1] not in shots:
                    err(f"{at}.camera[{j}]: no shot {key[1]!r} (shots: {', '.join(sorted(shots)) or 'none'})")
        for kind in ["captions", "toasts"]:
            for j, c in enumerate(s.get(kind, [])):
                if kind == "captions" and not c.get("text"): err(f"{at}.{kind}[{j}].text: missing")
                if kind == "toasts" and not (c.get("keys") or c.get("text")): err(f"{at}.{kind}[{j}]: needs keys or text")
                if not all(isinstance(c.get(k), (int, float)) for k in ["at", "until"]):
                    err(f"{at}.{kind}[{j}]: \"at\" and \"until\" in seconds")
    if not any(e.startswith("scenes") for e in errs):
        try:
            timeline.build(scenes, events)
            for i, s in enumerate(scenes):
                for kind in ["captions", "toasts"]:
                    for j, c in enumerate(s.get(kind, [])):
                        if c["until"] <= c["at"]: err(f"scenes[{i}].{kind}[{j}]: ends before it starts")
                        if c["at"] >= s["dur"]: err(f"scenes[{i}].{kind}[{j}]: starts after the scene ends ({s['dur']:.2f}s)")
        except (ValueError, KeyError, TypeError) as e:
            err(f"scenes: {e}")

    subs = edit.get("subtitles")
    if subs is not None:
        if not isinstance(subs, dict): err("subtitles: a block like {\"burn\": true}")
        else:
            unknown = set(subs) - {"burn", "words", "model"}
            if unknown: err(f"subtitles: unknown option{'s' * (len(unknown) > 1)} {', '.join(sorted(unknown))}")
            if "words" in subs and not isinstance(subs["words"], list): err("subtitles.words: a list of words")
    for name in edit.get("formats", []):
        if name not in layout.PRESETS: err(f"formats: {name!r} is not one of {', '.join(layout.PRESETS)}")

    spec = edit.get("audio", {}).get("music", "auto")
    if isinstance(spec, dict) and spec.get("file") and not spec.get("auto"):
        if not (base / spec["file"]).exists():
            err(f"audio.music.file: {spec['file']} not found")
        else:
            try:
                music.check(music.load(spec, base), allow=set(spec.get("allow", [])))
            except music.LicenseError as e:
                err(f"audio.music: {e}")
    elif spec not in (None, "auto") and not (isinstance(spec, dict) and spec.get("auto")):
        err('audio.music: "auto", null, or a block with "file"')
    return errs

def main():
    import layout
    path = pathlib.Path(sys.argv[1]).resolve()
    raw = json.loads(path.read_text())
    warnings, errs = [], []
    for fmt in dict.fromkeys([raw.get("format", "4:5")] + raw.get("formats", [])):   # each format it renders
        w = []
        errs += [e for e in validate(layout.resolve(raw, fmt), path.parent, warnings=w) if e not in errs]
        warnings += [x for x in w if x not in warnings]
    for x in warnings: print("  warning:", x)
    if errs:
        print(f"{path.name}: {len(errs)} problem{'s' * (len(errs) != 1)}")
        for e in errs: print("  -", e)
        sys.exit(1)
    print(f"{path.name}: ok")

if __name__ == "__main__":
    main()
