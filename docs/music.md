# Music

A bed under the video: essential when the product makes no sound, optional under a voice. Every
track carries a licence record, and a render refuses music whose licence is missing, unknown or
unfit for a product demo.

## Record where a track came from

```bash
reel music add music/calm.mp3 --license CC-BY-4.0 --title "Calm" --artist "Name" --source https://…
```

This writes `music/calm.mp3.license.json` beside the track. For licences that need credit, a
credit line is composed for you (or pass `--credit`). `reel music list music` shows every track in
a folder and whether it may be used.

| Licence id | Product demo | Credit | In a public repo |
|---|---|---|---|
| `CC0-1.0`, `PD` | yes | no | yes |
| `CC-BY-3.0`, `CC-BY-4.0` | yes | **yes** | yes |
| `CC-BY-SA-3.0`, `CC-BY-SA-4.0` | yes, but the video may have to be CC BY-SA too | **yes** | yes |
| `Pixabay` | yes | no | **no** (no redistribution on its own) |
| `Purchased` | per your licence | per your licence | no |
| `Generated-MIT`, `Generated-Apache-2.0` | yes | no | yes |
| `CC-BY-NC-*` | **refused** (non-commercial) | | |
| `CC-BY-ND-*`, `CC-BY-NC-ND-*` | **refused** (mixing under a video is an adaptation) | | |

A refused licence can be accepted for a video that is genuinely not commercial with
`"allow": ["CC-BY-NC-4.0"]` in the music block.

Every render with music writes `<video>.credits.txt` beside it: the track, its licence and source,
and the exact line to publish with the video when the licence asks for one.

## Where to find music

- **[Pixabay Music](https://pixabay.com/music/)** — free for commercial use, no credit needed. Do not
  commit the tracks to a public repo.
- **[Incompetech](https://incompetech.com/)** (Kevin MacLeod) — a large catalogue under CC BY; put
  the credit in the post text.
- **[Free Music Archive](https://freemusicarchive.org/), [ccMixter](https://ccmixter.org/),
  [Openverse](https://openverse.org/)** — mixed Creative Commons: check each track, avoid NC and ND.
- **[Musopen](https://musopen.org/)** — public-domain classical recordings.

For a 30-second demo, calm and steady works best: no vocals, a soft start, nothing that fights the
captions. Pick two or three candidates and audition them.

## Audition candidates

```bash
reel render edit.json renders/demo.mp4                     # once, without music (or with any)
reel music audition edit.json renders/demo.mp4 music/a.mp3 music/b.mp3 music/c.mp3
```

Each candidate is mixed onto the finished picture in seconds (`renders/demo-a.mp4`, …), with its
credits file beside it. An agent cannot hear: it should hand the previews to the person to choose.
Then put the chosen track in the edit:

```json
"audio": { "loudness": -16,
           "music": { "file": "music/b.mp3", "gainDb": -20, "duckDb": -12, "start": 0, "fade": 1.5 } }
```

| Field | Meaning |
|---|---|
| `gainDb` | the bed's level before loudness matching; -20 sits under a voice, -12 alone |
| `duckDb` | how far the bed drops while there is speech (smooth attack and release) |
| `start` | seconds into the track to begin, to skip an intro |
| `fade` | fade-out at the end of the video, in seconds |

The track is fitted to the video: trimmed, or looped with a two-second crossfade when it is too
short, faded in briefly and out at the end. The final mix gets one fixed gain to the target loudness
and a peak limiter, so the bed does not swell in the pauses.

## Generate a track

Any local music model can be plugged in. `reel music generate` runs your command and records the
model, version, prompt, seed and date in the licence file, so a generated track can be traced and
made again:

```bash
export REEL_MUSIC_CMD='your-generator --prompt {prompt} --duration {seconds} --seed {seed} --out {out}'
export REEL_MUSIC_MODEL="ACE-Step" REEL_MUSIC_VERSION="1.5" REEL_MUSIC_LICENSE="Generated-MIT"
reel music generate --prompt "calm ambient electronic, soft pads, no vocals, 80 bpm" --seconds 35 --out music/bed.wav
```

Suggested model: **[ACE-Step 1.5](https://huggingface.co/ACE-Step/acestep-v15-base)**, whose model
card lists the MIT licence and allows commercial use of its output. It needs an NVIDIA GPU or Apple
Silicon; it has not been tested with demo-reel yet, so check its current licence and wire its CLI
into `REEL_MUSIC_CMD` yourself. Avoid MusicGen for product videos (its weights are non-commercial,
CC BY-NC 4.0); Stable Audio Open is free commercially only below $1M annual revenue.
