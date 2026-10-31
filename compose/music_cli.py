"""reel music: keep track of where music came from, and audition it under a video.

    reel music add <track> --license CC-BY-4.0 --title T --artist A --source URL [--credit TEXT]
    reel music list [folder]
    reel music audition <edit.json> <render.mp4> <track> [<track> ...]
    reel music generate --prompt TEXT --seconds 35 --out music/bed.wav [--seed 7]
    reel music auto <edit.json> [--count 3] [--audition renders/demo.mp4]
"""
import argparse, datetime, json, os, pathlib, shlex, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import music

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

def cmd_add(a):
    track = pathlib.Path(a.track).resolve()
    if not track.exists(): sys.exit(f"no such file: {track}")
    if a.candidate:                       # fill the record from the system's shortlist
        edit_path = pathlib.Path(a.edit).resolve()
        edit = json.loads(edit_path.read_text())
        choice = json.loads((edit_path.parent / edit.get("build", "build") / "music-choice.json").read_text())
        c = choice["shortlist"][a.candidate - 1]
        a.title, a.artist, a.source = a.title or c["title"], a.artist or c.get("artist"), a.source or c.get("source")
        a.license = a.license or c["license"]
    if not a.license: sys.exit("--license is required (or --candidate N after `reel music auto`)")
    if a.license not in music.LICENSES: sys.exit(f"unknown licence {a.license!r}. Known: {', '.join(sorted(music.LICENSES))}")
    rec = {k: v for k, v in dict(title=a.title, artist=a.artist, source=a.source, license=a.license,
                                 credit=a.credit, added=datetime.date.today().isoformat()).items() if v}
    info = music.LICENSES[a.license]
    if info["credit"] and not rec.get("credit"):
        by = f" by {a.artist}" if a.artist else ""
        src = f" ({a.source})" if a.source else ""
        rec["credit"] = f"\"{a.title or track.stem}\"{by}{src}, licensed under {info['name']}"
    music.sidecar(track).write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(f"recorded {music.sidecar(track).name}")
    try:
        music.check({**rec, "path": track}); print("  usable in a product demo" + (" (credit required)" if info["credit"] else ""))
    except music.LicenseError as e:
        print("  NOT usable in a product demo:", e)
    if not info["bundle"]: print("  keep it out of public repos:", info.get("note", "redistribution not allowed"))

def cmd_list(a):
    folder = pathlib.Path(a.folder).resolve()
    tracks = sorted(p for p in folder.rglob("*") if p.suffix.lower() in AUDIO)
    if not tracks: print("no audio files in", folder); return
    for t in tracks:
        rec = json.loads(music.sidecar(t).read_text()) if music.sidecar(t).exists() else {}
        rec["path"] = t
        try:
            info = music.check(rec)
            status = "ok, credit needed" if info["credit"] else "ok"
        except music.LicenseError as e:
            status = "REFUSED: " + str(e).split(": ", 1)[-1]
        print(f"{t.relative_to(folder)}\n    {rec.get('license', '-'):<14} {status}")

def cmd_audition(a):
    edit_path = pathlib.Path(a.edit).resolve()
    edit = json.loads(edit_path.read_text())
    video = pathlib.Path(a.video).resolve()
    outs = []
    for track in a.tracks:
        t = pathlib.Path(track).resolve()
        spec = dict(edit.get("audio", {}).get("music") or {})
        spec["file"] = os.path.relpath(t, edit_path.parent)
        for k in ["title", "artist", "source", "license", "credit", "generated"]: spec.pop(k, None)  # from sidecar
        trial = {**edit, "audio": {**edit.get("audio", {}), "music": spec}}
        trial_path = edit_path.with_name(f".audition-{t.stem}.json")
        trial_path.write_text(json.dumps(trial))
        out = video.with_name(f"{video.stem}-{t.stem}.mp4")
        r = subprocess.run([sys.executable, str(ROOT / "compose/compose.py"), str(trial_path),
                            "--audio-only", str(video), "--out", str(out)], capture_output=True, text=True)
        trial_path.unlink()
        if r.returncode:
            print(f"{t.name}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.stdout.strip()}")
        else:
            outs.append(out); print(f"{t.name}: {out}")
    if outs: print(f"\n{len(outs)} previews. Listen to each and keep one; its credits file sits beside it.")

def cmd_generate(a):
    """Run the configured music model. REEL_MUSIC_CMD is a command template with {prompt},
    {seconds}, {seed} and {out}; REEL_MUSIC_MODEL, REEL_MUSIC_VERSION and REEL_MUSIC_LICENSE
    describe the model (REEL_MUSIC_LICENSE is a licence id such as Generated-MIT)."""
    tmpl = os.environ.get("REEL_MUSIC_CMD")
    lic = os.environ.get("REEL_MUSIC_LICENSE")
    if not tmpl or not lic:
        sys.exit("no music model configured. Set REEL_MUSIC_CMD (a command template using {prompt} {seconds} "
                 "{seed} {out}) and REEL_MUSIC_LICENSE (for example Generated-MIT). See docs/music.md.")
    if lic not in music.LICENSES: sys.exit(f"unknown REEL_MUSIC_LICENSE {lic!r}")
    out = pathlib.Path(a.out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    cmd = tmpl.format(prompt=shlex.quote(a.prompt), seconds=a.seconds, seed=a.seed, out=shlex.quote(str(out)))
    print("running:", cmd)
    if subprocess.run(cmd, shell=True).returncode or not out.exists(): sys.exit("the model did not produce " + str(out))
    rec = dict(title=out.stem, license=lic, generated=dict(
        model=os.environ.get("REEL_MUSIC_MODEL", "unknown"), version=os.environ.get("REEL_MUSIC_VERSION", ""),
        prompt=a.prompt, seed=a.seed, seconds=a.seconds, date=datetime.datetime.now().isoformat(timespec="seconds")))
    music.sidecar(out).write_text(json.dumps(rec, indent=2) + "\n")
    print("wrote", out, "and", music.sidecar(out).name)

def cmd_auto(a):
    """Let the system choose: profile the video, rank licensed candidates, keep the best."""
    edit_path = pathlib.Path(a.edit).resolve()
    edit = json.loads(edit_path.read_text())
    spec = edit.get("audio", {}).get("music")
    if isinstance(spec, dict) and spec.get("file") and not spec.get("auto"):
        print(f"this edit already uses your own track ({spec['file']}); showing what the system would pick instead.")
    r = subprocess.run([sys.executable, str(ROOT / "compose/compose.py"), str(edit_path), "--pick-music", str(a.count)])
    if r.returncode: sys.exit(r.returncode)
    choice = json.loads((edit_path.parent / edit.get("build", "build") / "music-choice.json").read_text())
    if spec is None or (isinstance(spec, dict) and spec.get("auto")) or spec == "auto":
        print("renders of this edit will use this choice (delete build/music-choice.json to choose again)")
    else:
        print('this edit names its own music; set "music": "auto" (or remove it) to use the choice')
    print(f"\nchosen: {choice['title']}")
    if a.audition:
        a.edit, a.video, a.tracks = str(edit_path), a.audition, [c["file"] for c in choice["shortlist"]]
        cmd_audition(a)
    print("To use your own track instead: reel music add <file> --license … then set music.file in the edit.")

p = argparse.ArgumentParser(prog="reel music")
sub = p.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("add"); x.add_argument("track"); x.add_argument("--license")
x.add_argument("--candidate", type=int, help="take title, artist, source and licence from `reel music auto`'s list")
x.add_argument("--edit", default="edit.json")
for f in ["title", "artist", "source", "credit"]: x.add_argument(f"--{f}")
x = sub.add_parser("list"); x.add_argument("folder", nargs="?", default="music")
x = sub.add_parser("audition"); x.add_argument("edit"); x.add_argument("video"); x.add_argument("tracks", nargs="+")
x = sub.add_parser("generate"); x.add_argument("--prompt", required=True); x.add_argument("--seconds", type=float, default=35)
x.add_argument("--out", required=True); x.add_argument("--seed", type=int, default=0)
x = sub.add_parser("auto"); x.add_argument("edit"); x.add_argument("--count", type=int, default=3)
x.add_argument("--audition", metavar="RENDER")
a = p.parse_args()
{"add": cmd_add, "list": cmd_list, "audition": cmd_audition, "generate": cmd_generate, "auto": cmd_auto}[a.cmd](a)
