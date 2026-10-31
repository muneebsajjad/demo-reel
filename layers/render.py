"""Render the overlay layers an edit needs as transparent PNGs, from HTML templates and the brand.

    python layers/render.py edit.json        -> <build>/layers/*.png

Each layer is a full-canvas PNG (the video's size) so the compositor can lay it straight on top.
Text is set by Chrome, so any script shapes correctly (Arabic, CJK) and system fonts work.
"""
import html, json, pathlib, shutil, subprocess, sys

from templates import TEMPLATES

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
]

def chrome():
    for c in CHROME_CANDIDATES:
        if c and pathlib.Path(c).exists(): return c
    sys.exit("Chrome not found for rendering layers")

def page(css, body, brand, size):
    w, h = size
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root {{ --accent: {brand['accent']}; --accent-2: {brand.get('accentLight', brand['accent'])};
        --ink: {brand.get('ink', '#16181d')}; --muted: {brand.get('muted', '#3b4048')};
        --soft: {brand.get('soft', '#6b7280')};
        --bg-0: {brand['background'][0]}; --bg-1: {brand['background'][1]}; --bg-2: {brand['background'][2]}; }}
html, body {{ margin: 0; width: {w}px; height: {h}px; overflow: hidden; }}
body {{ font-family: {brand.get('font', '-apple-system, "SF Pro Display", "Helvetica Neue", sans-serif')};
       color: var(--ink); -webkit-font-smoothing: antialiased; background: transparent; }}
.mono {{ font-family: {brand.get('mono', '"SF Mono", Menlo, monospace')}; }}
b {{ color: var(--accent); }}
{css}
</style></head><body>{body}</body></html>"""

def render(edit_path):
    edit_path = pathlib.Path(edit_path).resolve()
    edit = json.loads(edit_path.read_text())
    base = edit_path.parent
    out = base / edit.get("build", "build") / "layers"
    out.mkdir(parents=True, exist_ok=True)
    brand = edit["brand"]
    size = edit.get("size", [1080, 1350])
    if brand.get("logo"):
        shutil.copy(base / brand["logo"], out / pathlib.Path(brand["logo"]).name)
        brand = {**brand, "logo": pathlib.Path(brand["logo"]).name}

    jobs = {"bg": TEMPLATES["window"](edit, brand, size)}
    for s in edit["scenes"]:
        if s.get("card"):
            jobs[s["card"]] = TEMPLATES[s["card"]](s, brand, size) if s["card"] in TEMPLATES else None
        for i, c in enumerate(s.get("captions", [])):
            jobs[c.setdefault("id", f"cap-{edit['scenes'].index(s)}-{i}")] = TEMPLATES["caption"](c, brand, size)
        for i, k in enumerate(s.get("toasts", [])):
            jobs[k.setdefault("id", f"toast-{edit['scenes'].index(s)}-{i}")] = TEMPLATES["toast"](k, brand, size)
    exe = chrome()
    for name, job in jobs.items():
        if job is None: continue
        css, body = job
        f = out / f"{name}.html"
        f.write_text(page(css, body, brand, size))
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--default-background-color=00000000", f"--window-size={size[0]},{size[1]}",
                        f"--screenshot={out / (name + '.png')}", f.as_uri()], capture_output=True)
        print("layer", name, "ok" if (out / f"{name}.png").exists() else "FAILED")
    # the compositor reads ids back from here
    (out / "index.json").write_text(json.dumps(edit["scenes"], indent=1))

if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    render(sys.argv[1])
