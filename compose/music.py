"""Music beds: licence records and checks, fitting a track to the video, and ducking under speech.

A track is described by its fields in the edit's "music" block, by a sidecar file next to it
(<track>.license.json, written by `reel music add`), or both (the edit wins). Fields:

    file, title, artist, source (URL), license (an id from LICENSES), credit (text to publish),
    generated (for model output: {"model", "version", "license", "prompt", "seed", "date"})
"""
import json, pathlib

# What each licence lets a product demo do. "ok": usable in a commercial promo; "credit": the
# credit line must be published with the video; "bundle": may be committed to a public repo;
# "note": shown when it is used.
LICENSES = {
    "CC0-1.0":      dict(ok=True,  credit=False, bundle=True,  name="CC0 1.0 (public domain)"),
    "PD":           dict(ok=True,  credit=False, bundle=True,  name="Public domain"),
    "CC-BY-2.5":    dict(ok=True,  credit=True,  bundle=True,  name="CC BY 2.5"),
    "CC-BY-3.0":    dict(ok=True,  credit=True,  bundle=True,  name="CC BY 3.0"),
    "CC-BY-4.0":    dict(ok=True,  credit=True,  bundle=True,  name="CC BY 4.0"),
    "CC-BY-SA-3.0": dict(ok=True,  credit=True,  bundle=True,  name="CC BY-SA 3.0",
                         note="share-alike: the video itself may have to be released under CC BY-SA"),
    "CC-BY-SA-4.0": dict(ok=True,  credit=True,  bundle=True,  name="CC BY-SA 4.0",
                         note="share-alike: the video itself may have to be released under CC BY-SA"),
    "Pixabay":      dict(ok=True,  credit=False, bundle=False, name="Pixabay Content License",
                         note="do not redistribute the track on its own (keep it out of public repos)"),
    "Generated-MIT":        dict(ok=True, credit=False, bundle=True, name="Generated with an MIT-licensed model"),
    "Generated-Apache-2.0": dict(ok=True, credit=False, bundle=True, name="Generated with an Apache-2.0 model"),
    "Purchased":    dict(ok=True,  credit=False, bundle=False, name="Purchased licence",
                         note="keep the licence certificate; check its terms for the platform you post on"),
}
for nc in ["CC-BY-NC-3.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-4.0"]:
    LICENSES[nc] = dict(ok=False, credit=True, bundle=True, name="CC " + "-".join(nc.split("-")[1:-1]) + " " + nc.split("-")[-1],
                        why="non-commercial: a product demo is commercial use")
for nd in ["CC-BY-ND-3.0", "CC-BY-ND-4.0", "CC-BY-NC-ND-3.0", "CC-BY-NC-ND-4.0"]:
    LICENSES[nd] = dict(ok=False, credit=True, bundle=True, name="CC " + "-".join(nd.split("-")[1:-1]) + " " + nd.split("-")[-1],
                        why="no derivatives: cutting and mixing the track under a video is an adaptation")

class LicenseError(Exception):
    pass

def sidecar(path):
    return pathlib.Path(str(path) + ".license.json")

def load(spec, base):
    """The full record for a music block: sidecar fields, overridden by the edit's own."""
    path = (base / spec["file"]).resolve()
    rec = json.loads(sidecar(path).read_text()) if sidecar(path).exists() else {}
    rec.update({k: v for k, v in spec.items() if k not in ("gainDb", "duckDb", "fade", "start", "loop")})
    rec["path"] = path
    return rec

def check(rec, allow=()):
    """Refuse a track whose licence is missing, unknown or unfit for a product demo.
    `allow` holds licence ids the person has explicitly accepted (e.g. a personal, non-commercial video)."""
    lic = rec.get("license")
    if not lic:
        raise LicenseError(f"{rec['path'].name}: no licence recorded. Add one with `reel music add`, "
                           "or put \"license\" in the edit's music block.")
    info = LICENSES.get(lic)
    if info is None:
        raise LicenseError(f"{rec['path'].name}: unknown licence {lic!r}. Known: {', '.join(sorted(LICENSES))}")
    if not info["ok"] and lic not in allow:
        raise LicenseError(f"{rec['path'].name}: {info['name']} — {info['why']}. "
                           f"Only if this video is not commercial, add {lic!r} to music.allow.")
    if info["credit"] and not rec.get("credit"):
        raise LicenseError(f"{rec['path'].name}: {info['name']} needs a published credit; add \"credit\".")
    return info

def credits_text(rec, info):
    lines = [f"Music: {rec.get('title', rec['path'].name)}" + (f" — {rec['artist']}" if rec.get("artist") else ""),
             f"Licence: {info['name']}"]
    if rec.get("source"): lines.append(f"Source: {rec['source']}")
    if rec.get("generated"):
        g = rec["generated"]
        lines.append("Generated: " + ", ".join(f"{k} {g[k]}" for k in ["model", "version", "seed", "date"] if g.get(k)))
        if g.get("prompt"): lines.append(f"Prompt: {g['prompt']}")
    if info["credit"]:
        lines += ["", "Publish this credit with the video (for example in the post text):", rec["credit"]]
    else:
        lines += ["", "No credit is required."]
    if info.get("note"): lines += ["", "Note: " + info["note"]]
    return "\n".join(lines) + "\n"

# ---- signal ------------------------------------------------------------------------------------
import numpy as np

def fit(track, n, sr, start=0.0, fade_in=0.4, fade_out=1.5, xfade=2.0):
    """`track` (frames x 2) made exactly `n` frames long: from `start`, looped with a crossfade when
    it is too short, faded in briefly and out at the end."""
    track = track[int(start * sr):]
    if len(track) == 0: raise ValueError("music start is past the end of the track")
    x = int(xfade * sr)
    out = track.copy()
    while len(out) < n:
        k = min(x, len(out) // 2, len(track) // 2)
        ramp = np.linspace(0, 1, k, dtype=np.float32)[:, None]
        joint = out[-k:] * (1 - ramp) + track[:k] * ramp      # equal-gain is fine for ambient beds
        out = np.concatenate([out[:-k], joint, track[k:]])
    out = out[:n].copy()
    a, b = int(fade_in * sr), int(fade_out * sr)
    if a: out[:a] *= np.linspace(0, 1, a, dtype=np.float32)[:, None]
    if b: out[-b:] *= np.linspace(1, 0, b, dtype=np.float32)[:, None]
    return out

def speech_gain(voice, sr, duck_db=-12.0, threshold_db=-42.0, attack=0.08, release=0.45):
    """Per-frame gain for the music: `duck_db` down while `voice` has sound, back up in pauses.
    Attack and release are smoothed so the bed breathes rather than pumps."""
    hop = int(0.02 * sr)
    mono = np.abs(voice).mean(1)
    frames = len(mono) // hop + 1
    pad = np.zeros(frames * hop, np.float32); pad[:len(mono)] = mono
    rms = np.sqrt((pad.reshape(frames, hop) ** 2).mean(1) + 1e-12)
    on = (20 * np.log10(rms + 1e-9) > threshold_db).astype(np.float32)
    # hold through gaps between words shorter than the release
    env = np.zeros_like(on); level = 0.0
    up, down = 1 - np.exp(-0.02 / attack), 1 - np.exp(-0.02 / release)
    for i, v in enumerate(on):
        level += (v - level) * (up if v > level else down)
        env[i] = level
    low = 10 ** (duck_db / 20)
    g = 1 - (1 - low) * env
    return np.interp(np.arange(len(mono)), np.arange(frames) * hop, g).astype(np.float32)[:, None]
