"""Render the overlay layers an edit needs as transparent PNGs, from HTML templates and the brand.

    python layers/render.py edit.json [--format 16:9]     -> <build>/layers/*.png

Each layer is a full-canvas PNG (the video's size) so the compositor can lay it straight on top.
Text is set by Chrome, so any script shapes correctly (Arabic, CJK) and system fonts work.
"""
import html, json, pathlib, shutil, subprocess, sys

from templates import TEMPLATES
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "compose"))
import layout

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

ROOT = pathlib.Path(__file__).resolve().parent.parent

def playwright_browser():
    """Playwright's headless shell (or Chrome for Testing). Branded Chrome's headless mode stops
    painting partway down a tall page on some Macs, so it is the last resort for one-session shots."""
    import os, glob
    for root in [os.path.expanduser("~/Library/Caches/ms-playwright"), os.path.expanduser("~/.cache/ms-playwright")]:
        for pattern in ["chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
                        "chromium_headless_shell-*/chrome-*/headless_shell",
                        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                        "chromium-*/chrome-linux/chrome"]:
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits: return hits[-1]
    return None

def shoot(exe, todo):
    """Screenshot the layers: all in one browser session when playwright-core is installed, else one
    headless Chrome per layer (slower: each launch costs a few seconds)."""
    if not todo: return
    for j in todo: pathlib.Path(j["png"]).unlink(missing_ok=True)
    pw = playwright_browser()
    if pw and (ROOT / "node_modules" / "playwright-core").exists() and shutil.which("node"):
        jobs = pathlib.Path(todo[0]["png"]).parent / "shoot.json"
        jobs.write_text(json.dumps(todo))
        r = subprocess.run(["node", str(ROOT / "layers/shoot.mjs"), str(jobs)], capture_output=True, text=True,
                           env={**__import__("os").environ, "CHROME": pw})
        if r.returncode == 0:
            print(r.stdout.strip()); return
        print("one-session screenshots failed, falling back:", (r.stderr or r.stdout).strip().splitlines()[-1:])
    for j in todo:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--default-background-color=00000000", f"--window-size={j['width']},{j['height']}",
                        f"--screenshot={j['png']}", pathlib.Path(j["html"]).as_uri()], capture_output=True)
        print("layer", j["name"], "ok" if pathlib.Path(j["png"]).exists() else "FAILED")

def render(edit_path, fmt=None):
    edit_path = pathlib.Path(edit_path).resolve()
    edit = layout.resolve(json.loads(edit_path.read_text()), fmt)
    lay = edit["layout"]
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
            jobs[c.setdefault("id", f"cap-{edit['scenes'].index(s)}-{i}")] = TEMPLATES["caption"](c, brand, size, lay)
        for i, k in enumerate(s.get("toasts", [])):
            jobs[k.setdefault("id", f"toast-{edit['scenes'].index(s)}-{i}")] = TEMPLATES["toast"](k, brand, size, lay)
    subs = (edit.get("subtitles") or {})
    srt = base / edit["baseBuild"] / "subtitles.srt"
    cues = []
    if subs.get("burn") and srt.exists():
        import subtitles as _subs
        cues = _subs.read_srt(srt)
        for i, c in enumerate(cues):
            c["id"] = f"sub-{i}"
            jobs[c["id"]] = TEMPLATES["subtitle"](c, brand, size, edit["window"])
    elif subs.get("burn"):
        print(f"subtitles: burn is on but {srt} does not exist; run `reel subtitles` first")
    (out / "subtitles.json").write_text(json.dumps(cues, indent=1))
    exe = chrome()
    skipped, todo = 0, []
    for name, job in jobs.items():
        if job is None: continue
        css, body = job
        f = out / f"{name}.html"
        html_text = page(css, body, brand, size)
        png = out / f"{name}.png"
        if f.exists() and png.exists() and f.read_text() == html_text and png.stat().st_mtime >= f.stat().st_mtime:
            skipped += 1; continue                  # unchanged since the last render
        f.write_text(html_text)
        todo.append(dict(name=name, html=str(f), png=str(png), width=size[0], height=size[1]))
    shoot(exe, todo)
    if skipped: print(f"{skipped} layer{'s' * (skipped != 1)} unchanged")
    # the compositor reads ids back from here
    (out / "index.json").write_text(json.dumps(edit["scenes"], indent=1))

if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    a = sys.argv[1:]
    render(a[0], a[a.index("--format") + 1] if "--format" in a else None)
