"""Subtitles of what is said in the video.

    reel subtitles edit.json            transcribe the take, write <build>/subtitles.srt (output times)

The take's sound, cut exactly as the edit cuts it, is transcribed locally (faster-whisper; nothing
leaves the machine), so a word clipped at a cut is not there and every time is already an output
time. Words are grouped into short cues that never cross a scene change. Read the .srt and fix any word before rendering: renders use the file as it is and never
re-transcribe over your edits. Edit options:

    "subtitles": { "burn": true,                       draw them on the video (default: only export)
                   "words": ["Heuristics", "Sawt"],    names and jargon to steer the transcription
                   "model": "base.en" }                larger is slower and more accurate: small.en
"""
import json, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import timeline

MAX_CHARS, MAX_SECONDS, GAP = 38, 4.5, 0.6

# ---- the .srt format -----------------------------------------------------------------------------
def stamp(t):
    ms = int(round(max(0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

def write_srt(cues, path):
    path.write_text("\n".join(f"{i + 1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}\n"
                              for i, c in enumerate(cues)))

def read_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", pathlib.Path(path).read_text().strip()):
        lines = block.strip().splitlines()
        m = next((re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l) for l in lines
                  if "-->" in l), None)
        if not m: continue
        g = [int(x) for x in m.groups()]
        t0 = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        t1 = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(l for l in lines[lines.index(next(l for l in lines if "-->" in l)) + 1:]).strip()
        if text: cues.append(dict(start=t0, end=t1, text=text))
    return cues

# ---- the edited voice track ----------------------------------------------------------------------
def voice_track(take, scenes, sr=16000):
    """The take's sound cut exactly as the edit cuts it, in output time: transcribing this means a
    word clipped at a cut is simply not there, and timestamps are already output times."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(take), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    src = np.frombuffer(raw, np.float32)
    total = scenes[-1]["start"] + scenes[-1]["dur"]
    out = np.zeros(int((total + 0.5) * sr), np.float32)
    for s in scenes:
        if "take" not in s: continue
        o = s["start"]
        for a, b in s["take"]:
            seg = src[max(0, int(a * sr)):max(0, int(b * sr))]
            i = int((o + max(0, -a)) * sr)
            out[i:i + len(seg)] = seg[:len(out) - i]
            o += b - a
    return out

def scene_bounds(scenes):
    return [s["start"] for s in scenes[1:]]

def group(words, max_chars=MAX_CHARS, max_seconds=MAX_SECONDS, gap=GAP, bounds=()):
    """Short, readable cues: break at sentence ends, pauses, scene changes and length. A sentence that
    would leave a word or two behind is allowed to run a little long instead."""
    cues, cur = [], []
    def flush():
        if cur:
            cues.append(dict(start=cur[0]["start"], end=cur[-1]["end"], text=" ".join(w["text"] for w in cur)))
            cur.clear()
    for w in words:
        if cur:
            text = " ".join(x["text"] for x in cur + [w])
            # whisper stamps words a few tenths early, so a scene's first word can sit just before its cut
            crosses = any(cur[-1]["start"] < b - 0.45 <= w["start"] for b in bounds)
            tail = words[words.index(w):words.index(w) + 3]
            ends_soon = next((i for i, x in enumerate(tail) if re.search(r"[.!?]$", x["text"])), None)
            short_tail = ends_soon is not None and ends_soon <= 1 and \
                len(text + " " + " ".join(x["text"] for x in tail[1:ends_soon + 1])) <= max_chars + 14
            if (crosses or (len(text) > max_chars and not short_tail) or w["start"] - cur[-1]["end"] > gap
                    or w["end"] - cur[0]["start"] > max_seconds or re.search(r"[.!?]$", cur[-1]["text"])):
                flush()
        cur.append(w)
    flush()
    for a, b in zip(cues, cues[1:]):                 # hold each cue until the next, unless there is a pause
        if b["start"] - a["end"] < gap: a["end"] = b["start"] - 0.02
    for c in cues: c["end"] = max(c["end"], c["start"] + 0.8)
    return cues

# ---- transcription ---------------------------------------------------------------------------------
def transcribe(audio, model="base.en", words=()):
    from faster_whisper import WhisperModel
    prompt = (", ".join(words) + ".") if words else None
    segs, _ = WhisperModel(model, device="cpu", compute_type="int8").transcribe(
        audio, word_timestamps=True, vad_filter=True, initial_prompt=prompt)
    return [dict(text=w.word.strip(), start=float(w.start), end=float(w.end)) for s in segs for w in s.words]

def main():
    edit_path = pathlib.Path(sys.argv[1]).resolve()
    edit = json.loads(edit_path.read_text())
    base = edit_path.parent
    build = base / edit.get("build", "build")
    build.mkdir(parents=True, exist_ok=True)
    opts = edit.get("subtitles", {}) or {}
    take = base / (edit["take"] + ".mov")
    log = json.loads((base / (edit["take"] + ".json")).read_text())
    scenes = json.loads(json.dumps(edit["scenes"]))
    timeline.build(scenes, log.get("events", []))
    cache = build / "transcript.json"
    pieces = [s.get("take") for s in scenes]
    key = dict(take=str(take), mtime=take.stat().st_mtime, pieces=pieces, model=opts.get("model", "base.en"),
               words=opts.get("words", []))
    if cache.exists() and json.loads(cache.read_text()).get("key") == key and "--again" not in sys.argv:
        words = json.loads(cache.read_text())["words"]
    else:
        print(f"transcribing the edited voice with {key['model']} (local)...")
        words = transcribe(voice_track(take, scenes), key["model"], key["words"])
        cache.write_text(json.dumps(dict(key=key, words=words), indent=1))
    cues = group(words, bounds=scene_bounds(scenes))
    srt = build / "subtitles.srt"
    if srt.exists() and "--again" not in sys.argv:
        print(f"{srt} already exists and may have your fixes; pass --again to replace it")
        write_srt(cues, build / "subtitles.new.srt"); print("wrote", build / "subtitles.new.srt")
    else:
        write_srt(cues, srt); print("wrote", srt)
    for c in cues: print(f"  {stamp(c['start'])}  {c['text']}")

if __name__ == "__main__":
    main()
