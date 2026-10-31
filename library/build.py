"""Rebuild the bundled music library from its sources.

    python library/build.py          # downloads the originals (once), cuts and encodes the clips

Every track is CC0 (or public domain) and released by the artist themselves, so the clips can live
in this repo and be used in any video without credit. Each clip is a steady 75-second stretch of the
original, measured for the least swing in loudness, faded in and out, as 112 kbps MP3.
The sources and cut points below are the whole record of how the library was made.
"""
import hashlib, json, pathlib, subprocess, sys, urllib.parse, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CACHE = pathlib.Path.home() / ".cache" / "demo-reel" / "pool"
UA = "demo-reel/0.1 (+https://github.com/muneebsajjad/demo-reel)"
LENGTH = 75

CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
TRACKS = [
    # slug, moods, title, artist, archive.org item, file in the item, start (s)
    ("calm-no-cadillac", ["calm", "focused"], "No Cadillac", "Loyalty Freak Music",
     "MINIMALAMBIENTBOUNCE", "Loyalty Freak Music - MINIMAL AMBIENT BOUNCE - 07 No Cadillac.mp3", 80),
    ("calm-nocturne", ["calm", "warm"], "Nocturne Op. 9 No. 2 (Chopin)", "Musopen",
     "musopen-chopin", "Nocturne Op. 9 no. 2 in E flat major.mp3", 110),
    ("focused-waiting", ["focused", "calm"], "Waiting TTTT", "Loyalty Freak Music",
     "MINIMALAMBIENTBOUNCE", "Loyalty Freak Music - MINIMAL AMBIENT BOUNCE - 05 Waiting TTTT.mp3", 70),
    ("focused-after-party", ["focused", "upbeat"], "After Party", "Loyalty Freak Music",
     "ROBOTDANCE", "Loyalty Freak Music - ROBOT DANCE ! - 03 After Party.mp3", 65),
    ("warm-chill-out", ["warm", "focused"], "Chill Out Theme", "Komiku",
     "Komiku-ItsTimeForAdventureVol2", "Komiku_-_02_-_Chill_Out_Theme.mp3", 90),
    ("upbeat-one-cool-minute", ["upbeat", "energetic"], "One Cool Minute", "Loyalty Freak Music",
     "MINIMALAMBIENTBOUNCE", "Loyalty Freak Music - MINIMAL AMBIENT BOUNCE - 02 One Cool Minute.mp3", 100),
    ("cinematic-something-to-save", ["cinematic"], "Something to save", "Komiku",
     "Komiku-ItsTimeForAdventureVol2", "Komiku_-_10_-_Something_to_save.mp3", 25),
]

def fetch(item, name):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / (item + "--" + "".join(c if c.isalnum() or c in ".-" else "_" for c in name))
    if not out.exists() or out.stat().st_size < 100_000:
        url = f"https://archive.org/download/{item}/{urllib.parse.quote(name)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        out.write_bytes(urllib.request.urlopen(req, timeout=300).read())
    return out

def licence_of(item):
    req = urllib.request.Request(f"https://archive.org/metadata/{item}", headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["metadata"].get("licenseurl", "")

def main():
    manifest = []
    for slug, moods, title, artist, item, name, start in TRACKS:
        lic = licence_of(item)
        if "publicdomain" not in lic: sys.exit(f"{item}: licence is now {lic!r}, not CC0 / public domain")
        src = fetch(item, name)
        out = HERE / f"{slug}.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(LENGTH), "-i", str(src),
                        "-af", f"afade=t=in:d=1.5,afade=t=out:st={LENGTH - 3}:d=3", "-ac", "2", "-ar", "44100",
                        "-c:a", "libmp3lame", "-b:a", "112k", "-map_metadata", "-1", str(out)], check=True)
        page = f"https://archive.org/details/{item}"
        rec = dict(title=title, artist=artist, source=page, license="CC0-1.0" if "zero" in lic else "PD",
                   moods=moods, original=name, cut=dict(start=start, length=LENGTH),
                   sha256=hashlib.sha256(out.read_bytes()).hexdigest())
        (HERE / f"{slug}.mp3.license.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        manifest.append(dict(file=out.name, **{k: rec[k] for k in ["title", "artist", "moods", "license", "source"]}))
        print(f"{out.name:<34} {out.stat().st_size / 1e6:.2f} MB  {', '.join(moods)}")
    (HERE / "library.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
