"""reel doctor: is this machine ready to make a demo video? Checks everything the pipeline needs and
says what to do about anything missing. Standard library only, so it runs before anything is set up."""
import json, os, pathlib, platform, re, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAC = platform.system() == "Darwin"
results = []          # (level, what, detail, fix)

def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)

def ok(what, detail=""): results.append(("ok", what, detail, ""))
def warn(what, detail, fix): results.append(("warn", what, detail, fix))
def bad(what, detail, fix): results.append(("bad", what, detail, fix))

def version(text):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)

# ---- tools ---------------------------------------------------------------------------------------
if sys.version_info < (3, 9): bad("python", platform.python_version(), "Python 3.9 or newer")
else: ok("python", platform.python_version())

if shutil.which("ffmpeg"):
    code, out = run(["ffmpeg", "-hide_banner", "-encoders"])
    missing = [e for e in ["libx264", "aac", "libmp3lame"] if e not in out]
    ver = run(["ffmpeg", "-version"])[1].split("\n")[0]
    if missing: bad("ffmpeg", f"{ver}; missing encoders: {', '.join(missing)}", "install a full build: brew install ffmpeg")
    else: ok("ffmpeg", ver.split()[2] if len(ver.split()) > 2 else ver)
else:
    bad("ffmpeg", "not found", "brew install ffmpeg (or your package manager)")

if shutil.which("uv"): ok("uv", run(["uv", "--version"])[1])
else: bad("uv", "not found", "brew install uv  (https://docs.astral.sh/uv/)")

if shutil.which("node"):
    v = run(["node", "--version"])[1]
    if version(v) < (18, 0, 0): bad("node", v, "Node 18 or newer")
    else: ok("node", v)
else:
    bad("node", "not found", "install Node 18+ (https://nodejs.org)")

if (ROOT / "node_modules" / "playwright-core").exists(): ok("playwright-core", "installed")
else: bad("playwright-core", "not installed", "reel setup  (or: npm install)")

# ---- browsers ------------------------------------------------------------------------------------
chrome = next((c for c in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           "/Applications/Chromium.app/Contents/MacOS/Chromium",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
               if c and pathlib.Path(c).exists()), None)
if chrome: ok("chrome (layers)", pathlib.Path(chrome).name)
else: bad("chrome (layers)", "not found", "install Google Chrome; it renders captions and cards")

cft = os.environ.get("CHROME_PATH")
if not cft:
    for root in [pathlib.Path.home() / "Library/Caches/ms-playwright", pathlib.Path.home() / ".cache/ms-playwright"]:
        hits = sorted(root.glob("chromium-*/chrome-*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")) \
            + sorted(root.glob("chromium-*/chrome-linux/chrome"))
        if hits: cft = str(hits[-1]); break
if cft and pathlib.Path(cft).exists(): ok("chrome for testing (takes)", "found")
else: bad("chrome for testing (takes)", "not found", "npx playwright@1.49.1 install chromium  (or reel setup)")

# ---- recording (macOS) ---------------------------------------------------------------------------
if not MAC:
    warn("recording", f"{platform.system()}: the recorder is macOS only", "record on a Mac; layers and rendering work here")
else:
    mac = version(platform.mac_ver()[0])
    if mac < (15, 0, 0): bad("macos", platform.mac_ver()[0], "macOS 15 or newer is needed to record")
    else: ok("macos", platform.mac_ver()[0])
    rec, src = ROOT / "recorder/record", ROOT / "recorder/record.swift"
    if not rec.exists():
        bad("recorder", "not built", "recorder/build.sh  (needs Xcode command line tools: xcode-select --install)")
    elif rec.stat().st_mtime < src.stat().st_mtime:
        warn("recorder", "older than its source", "recorder/build.sh")
    else:
        ok("recorder", "built")
        code, out = run([str(rec), "--check-permission"])
        if code == 0: ok("screen recording permission", "granted")
        elif code == 2:
            bad("screen recording permission", "not granted to this terminal",
                "System Settings > Privacy & Security > Screen & System Audio Recording: turn on your terminal, then restart it")
        else:
            warn("screen recording permission", "could not check", "rebuild the recorder: recorder/build.sh")

# ---- report --------------------------------------------------------------------------------------
mark = {"ok": "ok  ", "warn": "warn", "bad": "FAIL"}
for level, what, detail, fix in results:
    print(f"  {mark[level]}  {what:<30} {detail}")
    if fix: print(f"        {'':<30} -> {fix}")
fails = sum(r[0] == "bad" for r in results)
print("\nready to make videos" if not fails else f"\n{fails} thing{'s' * (fails != 1)} to fix before making videos")
sys.exit(1 if fails else 0)
