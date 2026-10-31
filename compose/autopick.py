"""Pick music for a video automatically: read what the video is like, find licensed candidates, measure
each one, and score them against the video. Used by `reel music auto` and by renders whose edit says
"music": "auto". An agent cannot listen, so everything here is measured; the person can always
override with their own track.

The profile of a video:
    length       seconds of music needed
    voice        share of the video with speech (a voiced video wants a sparser, quieter bed)
    pace         scene changes and camera moves per minute
    energy       0..1 target, from pace, voice and the mood
    bpm          target tempo range
    mood         a word: calm, focused, warm, upbeat, energetic, cinematic (from the edit, or guessed)
"""
import json, math, pathlib, re, subprocess, urllib.error, urllib.parse, urllib.request
import numpy as np

import music

CACHE = pathlib.Path.home() / ".cache" / "demo-reel" / "music"
UA = "demo-reel/0.1 (+https://github.com/muneebsajjad/demo-reel)"

MOODS = {   # target energy, tempo range, search words
    "calm":      (0.25, (60, 90),   ["ambient", "calm", "chill"]),
    "focused":   (0.35, (75, 105),  ["ambient", "electronic", "chill"]),
    "warm":      (0.40, (80, 110),  ["acoustic", "piano", "chill"]),
    "upbeat":    (0.60, (100, 125), ["upbeat", "electronic", "pop"]),
    "energetic": (0.80, (118, 140), ["energetic", "electronic", "dance"]),
    "cinematic": (0.50, (70, 100),  ["cinematic", "orchestral", "ambient"]),
}
WORDS = {   # caption words that hint at a mood
    "calm": ["calm", "quiet", "focus", "read", "listen", "private", "simple", "peace", "relax"],
    "upbeat": ["fast", "launch", "new", "boost", "save time", "instantly", "in seconds", "ship"],
    "energetic": ["game", "race", "power", "speed", "turbo", "hype"],
    "cinematic": ["story", "journey", "world", "epic", "discover"],
    "warm": ["friend", "family", "together", "home", "personal", "love"],
}

# ---- what the video is like -----------------------------------------------------------------
def profile(edit, scenes, voice, sr, total):
    speech = 0.0
    if voice is not None and np.abs(voice).max() > 1e-3:
        hop = int(0.05 * sr); mono = np.abs(voice).mean(1)
        n = len(mono) // hop
        rms = np.sqrt((mono[:n * hop].reshape(n, hop) ** 2).mean(1))
        speech = float((20 * np.log10(rms + 1e-9) > -42).mean())
    moves = sum(max(0, len(s.get("camera", [])) - 1) for s in scenes)
    pace = (len(scenes) + 0.3 * moves) / max(total, 1) * 60      # a camera move is gentler than a cut
    spec = edit.get("audio", {}).get("music")
    mood = spec.get("mood") if isinstance(spec, dict) else None
    if not mood:
        text = " ".join(c.get("text", "") + " " + c.get("kicker", "")
                        for s in scenes for c in s.get("captions", [])).lower()
        text = re.sub(r"<[^>]+>", " ", text)
        votes = {m: sum(text.count(w) for w in ws) for m, ws in WORDS.items()}
        mood = max(votes, key=votes.get) if max(votes.values()) else "focused"
        if mood == "calm" and pace > 14: mood = "focused"        # calm words, busy cutting
    energy, bpm, words = MOODS[mood]
    energy = min(1, max(0, energy + (pace - 10) * 0.015 - speech * 0.15))
    return dict(length=total, voice=round(speech, 2), pace=round(pace, 1), mood=mood,
                energy=round(energy, 2), bpm=bpm, words=words)

# ---- measuring a track ------------------------------------------------------------------------
def decode(path, sr=22050, seconds=None):
    cmd = ["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(sr)]
    if seconds: cmd += ["-t", str(seconds)]
    raw = subprocess.run(cmd + ["-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)

def features(path):
    """Tempo, energy, brightness, steadiness and intro length, measured from the audio."""
    sr = 22050
    y = decode(path, sr)
    if len(y) < sr * 5: return None
    dur = len(y) / sr
    hop, win = 512, 2048
    n = 1 + (len(y) - win) // hop
    frames = np.lib.stride_tricks.as_strided(y, (n, win), (y.strides[0] * hop, y.strides[0]))
    mag = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    rms = np.sqrt((frames ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(rms)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    centroid = float((mag * freqs).sum(1).mean() / (mag.sum(1).mean() + 1e-9))
    flux = np.maximum(0, np.diff(np.log1p(mag), axis=0)).sum(1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, "same")
    flux = np.maximum(flux, 0)
    fps = sr / hop
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    lags = np.arange(len(ac))
    bpm_of = lambda lag: 60 * fps / lag
    lo, hi = int(60 * fps / 180), int(60 * fps / 55)
    weight = np.exp(-0.5 * (np.log2(bpm_of(lags[lo:hi]) / 105) / 0.9) ** 2)   # mild prior near 105
    lag = lo + int(np.argmax(ac[lo:hi] * weight))
    beat_strength = float(ac[lag] / (ac[0] + 1e-9))
    loud = db[db > db.max() - 40]
    steady = float(np.std(np.convolve(db, np.ones(43) / 43, "valid")))     # 1-second loudness swings
    onset = float((flux > flux.mean() + 2 * flux.std()).mean() * fps)      # busy-ness, events per second
    intro = float(np.argmax(db > db.max() - 20) * hop / sr)
    energy = float(np.clip((np.mean(loud) + 30) / 22 * 0.5 + min(onset / 4, 1) * 0.3 + min(centroid / 3500, 1) * 0.2, 0, 1))
    return dict(duration=round(dur, 1), bpm=round(bpm_of(lag), 1), beat=round(beat_strength, 2),
                energy=round(energy, 2), brightness=round(centroid), swing_db=round(steady, 1),
                busy=round(onset, 2), intro=round(intro, 1))

def score(f, p):
    """Lower is better. Each term is roughly 0..1 when the track is a reasonable fit."""
    lo, hi = p["bpm"]
    b = f["bpm"]
    tempo = min(abs(math.log2(x / ((lo + hi) / 2))) for x in (b, b * 2, b / 2))   # half/double time ok
    tempo = max(0, tempo - math.log2(hi / lo) / 2) * 3
    energy = abs(f["energy"] - p["energy"]) * 2
    swing = max(0, f["swing_db"] - 2.5) / 3                    # big swells fight the captions
    length = 0 if f["duration"] >= p["length"] - f["intro"] else 0.4    # will loop otherwise
    voice = p["voice"] * (max(0, f["busy"] - 1.5) / 2 + max(0, f["brightness"] - 2600) / 2000)
    intro = max(0, f["intro"] - 3) / 6
    terms = dict(tempo=tempo, energy=energy, swing=swing, length=length, voice=voice, intro=intro)
    return sum(terms.values()), terms

# ---- where candidates come from ---------------------------------------------------------------
def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()

CCM_LICENSES = {"by/2.5": "CC-BY-2.5", "by/3.0": "CC-BY-3.0", "by/4.0": "CC-BY-4.0",
                "zero/1.0": "CC0-1.0", "publicdomain": "PD"}

def from_ccmixter(p, limit=10):
    """Instrumental tracks under CC BY or CC0, most popular first, matching the mood words."""
    out = []
    for word in p["words"][:2]:
        q = urllib.parse.urlencode(dict(f="json", tags=f"instrumental,{word}", lic="by", limit=limit, sort="rank"))
        try:
            rows = json.loads(_get(f"http://ccmixter.org/api/query?{q}"))
        except Exception as e:
            print(f"  ccmixter: {e}"); continue
        for r in rows:
            lic = next((v for k, v in CCM_LICENSES.items() if k in (r.get("license_url") or "")), None)
            f = next((f for f in r.get("files", []) if f.get("download_url", "").endswith(".mp3")), None)
            if not lic or not f: continue
            tags = r.get("upload_tags", "")
            m = re.search(r"bpm_(\d+)_(\d+)", tags)
            out.append(dict(id=f"ccmixter-{r['upload_id']}", url=f["download_url"], title=r["upload_name"],
                            artist=r["user_name"], source=r.get("file_page_url") or f["download_url"],
                            license=lic, popular=("in_video" in tags) + ("editorial_pick" in tags),
                            bpm=(int(m.group(1)) + int(m.group(2))) / 2 if m else None,
                            words=sum(w in tags for w in p["words"])))
    return out

def from_openverse(p, limit=10):
    q = urllib.parse.urlencode(dict(q=" ".join(p["words"][:2]), license_type="commercial,modification",
                                    category="music", page_size=limit))
    try:
        rows = json.loads(_get(f"https://api.openverse.org/v1/audio/?{q}", timeout=12)).get("results", [])
    except Exception as e:
        print(f"  openverse: unavailable ({e.__class__.__name__})"); return []
    out = []
    for r in rows:
        lic = {"cc0": "CC0-1.0", "pdm": "PD", "by": f"CC-BY-{r.get('license_version', '4.0')}"}.get(r["license"])
        if not lic or lic not in music.LICENSES or not r.get("url"): continue
        out.append(dict(id=f"openverse-{r['id']}", url=r["url"], title=r["title"], artist=r.get("creator") or "",
                        source=r.get("foreign_landing_url") or r["url"], license=lic, popular=0))
    return out

LIBRARY = pathlib.Path(__file__).resolve().parent.parent / "library"

def from_folder(folder, origin="yours"):
    """Tracks in a folder that have a licence record. `origin` is "yours" or "bundled"."""
    out = []
    for t in sorted(pathlib.Path(folder).glob("*")):
        if t.suffix.lower() not in {".mp3", ".wav", ".m4a", ".flac", ".ogg"} or not music.sidecar(t).exists(): continue
        rec = json.loads(music.sidecar(t).read_text())
        out.append(dict(id=f"{origin}-{t.name}", path=t, title=rec.get("title", t.stem), artist=rec.get("artist", ""),
                        source=rec.get("source", ""), license=rec.get("license"), moods=rec.get("moods", []),
                        popular=0, origin=origin))
    return out

def fetch(c):
    """Download a candidate into the cache, with its licence sidecar."""
    if c.get("path"): return c["path"]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (re.sub(r"[^\w.-]", "_", c["id"]) + pathlib.Path(urllib.parse.urlparse(c["url"]).path).suffix)
    if not path.exists():
        path.write_bytes(_get(c["url"], timeout=60))
    if not music.sidecar(path).exists():
        info = music.LICENSES[c["license"]]
        rec = dict(title=c["title"], artist=c["artist"], source=c["source"], license=c["license"])
        if info["credit"]:
            rec["credit"] = f"\"{c['title']}\" by {c['artist']} ({c['source']}), licensed under {info['name']}"
        music.sidecar(path).write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    return path

def meta_score(c, p):
    """Score from catalogue data alone (tempo tag, mood tags, popularity), for tracks not downloaded."""
    terms = dict(tempo=0.5, energy=0.5, swing=0, length=0, voice=0, intro=0)    # unknown: middling
    if c.get("bpm"):
        lo, hi = p["bpm"]
        t = min(abs(math.log2(x / ((lo + hi) / 2))) for x in (c["bpm"], c["bpm"] * 2, c["bpm"] / 2))
        terms["tempo"] = max(0, t - math.log2(hi / lo) / 2) * 3
    terms["energy"] = max(0.1, 0.5 - 0.15 * c.get("words", 0))
    return sum(terms.values()), terms

GOOD_ENOUGH = 0.6     # a local track scoring this well (lower is better) means no need to search online

def pick(p, folders=(), online="auto", count=3, log=print):
    """Rank candidates for profile `p`. Returns entries (score, terms, features|None, path|None, candidate),
    best first. Your own folders come first, then the bundled library; the internet is searched only
    when nothing local fits well (online="auto"), always (True) or never (False). Tracks a site will
    not hand to a script are scored from catalogue data and kept as links for the person."""
    ranked, seen = [], set()

    def consider(c):
        if c["id"] in seen: return
        seen.add(c["id"])
        info = music.LICENSES.get(c.get("license"))
        if not info or not info["ok"]: return
        try:
            path = fetch(c)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):                      # the site does not allow scripted downloads
                s, terms = meta_score(c, p)
                ranked.append((round(s - 0.15 * c.get("popular", 0) + 0.2, 3), terms, None, None, c))
                return "blocked"
            log(f"  skip {c['title'][:40]}: {e}"); return
        except Exception as e:
            log(f"  skip {c['title'][:40]}: {e}"); return
        f = features(path)
        if not f: return
        s, terms = score(f, p)
        s -= 0.15 * c.get("popular", 0)
        s -= {"yours": 0.3, "bundled": 0.1}.get(c.get("origin"), 0)       # your own music first
        if p["mood"] in c.get("moods", []): s -= 0.35                        # tagged for this mood
        ranked.append((round(s, 3), terms, f, path, c))

    for f in folders: [consider(c) for c in from_folder(f, "yours")]
    if LIBRARY.exists(): [consider(c) for c in from_folder(LIBRARY, "bundled")]
    best_local = min((r[0] for r in ranked), default=9)
    if online is True or (online == "auto" and best_local > GOOD_ENOUGH):
        log("  searching online: nothing local fits well enough" if online == "auto" else "  searching online")
        blocked = sum(consider(c) == "blocked" for c in from_ccmixter(p) + from_openverse(p))
        if blocked: log(f"  {blocked} tracks could not be downloaded by script; they are ranked from their catalogue data")
    ranked.sort(key=lambda r: r[0])
    return ranked                                     # everything, best first; callers show the top few

def describe(entry, p):
    s, terms, f, path, c = entry
    where = {"yours": "your music", "bundled": "bundled"}.get(c.get("origin"), "online")
    if f is None:
        bpm = f"{c['bpm']:>5.0f} bpm" if c.get("bpm") else "  ? bpm"
        return (f"{c['title'][:44]:<44} {c['license']:<10} {bpm}  score {s:.2f}  "
                f"[download it yourself: {c['source']}]")
    worst = max(terms, key=terms.get)
    why = {"tempo": "tempo off", "energy": "energy off", "swing": "swells in volume", "length": "shorter than the video",
           "voice": "busy under a voice", "intro": "long intro"}[worst] if terms[worst] > 0.25 else "close fit"
    return (f"{c['title'][:40]:<40} {where:<10} {c['license']:<10} {f['bpm']:>5.0f} bpm  energy {f['energy']:.2f} "
            f"(want {p['energy']:.2f})  score {s:.2f}  [{why}]")
