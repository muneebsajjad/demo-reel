# The edit file

`edit.json` describes the whole video. Paths are relative to the edit file.
`examples/sawt/edit.json` is a complete one.

```jsonc
{
  "format": "4:5",                 // 4:5, 1:1, 9:16 or 16:9 (see "formats" below)
  "formats": ["4:5", "1:1", "16:9"],   // what `reel render --format all` makes
  "fps": 30,
  "take": "takes/take1",           // reads take1.mov and take1.json
  "build": "build",                // layers and stills go here
  "transition": 0.4,               // seconds for dissolves between scenes
  "dip": [205, 219, 234],          // between two take scenes, dip through this colour (the page's)
  "brand": { ... },
  "window": { ... },
  "shots": { ... },
  "scenes": [ ... ],
  "audio": { "loudness": -16, "music": { "file": "music.m4a", "gainDb": -22, "fade": 1.5 } }
}
```

## formats

One edit renders to any of four layouts; the camera's fitted shots adapt to each window's shape.

| Format | Size | Layout | For |
|---|---|---|---|
| `4:5` | 1080×1350 | caption above the window | LinkedIn, Instagram feeds |
| `1:1` | 1080×1080 | caption above, smaller | square feeds |
| `9:16` | 1080×1920 | caption above, tall window | stories, reels, shorts |
| `16:9` | 1920×1080 | caption on the left, window on the right | YouTube, websites, X |

```bash
reel render edit.json renders/demo.mp4 --format 16:9
reel render edit.json renders/demo.mp4 --format all     # demo-4x5.mp4, demo-1x1.mp4, …
```

`size`, `window` and `layout` (`{"caption": {...}, "toast": {...}}`) in the edit adjust its own
format only; other formats use their presets. A shot can be nudged for one format:

```json
"para": { "fit": ["para1", "para2"], "dy": -100, "1:1": { "dy": 20 } }
```

## brand

| Field | Meaning |
|---|---|
| `name` | product name, used on the cards |
| `accent`, `accentLight` | main colour (kickers, `<b>` text, pills) and a lighter one (rules, icon tile) |
| `background` | three colours for the radial background, centre to edge |
| `ink`, `muted`, `soft` | text colours (optional) |
| `font`, `mono` | CSS font stacks (optional; system fonts by default) |
| `logo`, `toolbarIcon` | image files; `pixelated: true` for pixel art |

## window

Optional: each format has its own. The browser window the take sits in: `x`, `y`, `w`, `h` (including the title bar), `bar` (title
bar height), `r` (corner radius), `url` (shown in the address pill).

## shots

Named camera framings, in page viewport pixels of the take (the same pixels as `rects` in the take
log). Either explicit:

```json
"close": { "cx": 2700, "cy": 400, "w": 1100 }
```

or fitted around recorded rects, which keeps working when a page moves between takes:

```json
"card": { "fit": ["title", { "rect": "card1", "dh": 330 }], "pad": 90, "minWidth": 1250, "dx": -190 }
```

A rect reference is a name from the take log, or `{ "rect": name, "dx", "dy", "dw", "dh" }` to
adjust it (useful for things that are not measurable, like a card whose height you know), or a
literal `{ "x", "y", "width", "height" }`. `pad` is added all round; the frame keeps the window's
aspect ratio and is clamped to the page. `dx`, `dy` nudge the result.

## times

Take times are seconds from the first recorded frame, or anchored to an event in the take log:
`"sentence#5-0.15"` is 0.15 s before the sixth `sentence` event; `"read+1"` is a second after the
first `read` event. Anchored times survive a retake that runs faster or slower.

Caption and toast times are seconds from the start of their scene; a negative `until` counts back
from the scene's end (`-0.1` = until 0.1 s before it ends).

## scenes

Played in order, with a dissolve between them (a dip through `dip` between two take scenes).

**A card** (a full-frame still from a template):

```json
{ "card": "title", "dur": 2.4,
  "title": { "name": "Sawt", "alt": "صوت", "altFont": "\"Geeza Pro\"", "badge": "Version 0.2",
             "tagline": "Now it explains<br><b>the words you don’t know.</b>" } }
{ "card": "end", "dur": 3.4,
  "end": { "points": ["…", "…"], "pill": "github.com/you/thing", "sub": "Open source" } }
```

**Part of the take**, framed by the camera:

```json
{ "take": [["sentence#0-1.8", "sentence#2-0.18"]],           // one or more [from, to] pieces
  "camera": [["sentence#0-1.8", "wide"], ["sentence#0+0.7", "wide"], ["sentence#0+1.9", "card"]],
  "captions": [{ "at": 0.2, "until": -0.1, "kicker": "Meanings", "text": "Hard words get a card,<br><b>right as you hear them.</b>" }],
  "toasts": [{ "at": 0.6, "until": 2.3, "keys": ["Alt", "R"], "text": "starts reading" }] }
```

Camera keys are `[take time, shot]`; between keys the camera eases, zooming evenly in log scale.
Several pieces play back to back (a hard cut, for removing a wait in the middle of a scene).

**Images** over the dimmed, blurred window (a popup, a settings panel), optionally revealing the
second image from a point, as a theme switch would:

```json
{ "images": ["takes/take1-popup-light.png", "takes/take1-popup-dark.png"], "dur": 3.6, "width": 480,
  "reveal": { "at": 1.35, "dur": 0.75, "from": [278, 424], "srcWidth": 352 } }
```

`from` is in the image's CSS pixels; `srcWidth` is the image's CSS width.

## audio

The take's own sound, cut with the picture, brought to `loudness` LUFS with one fixed gain and a
peak limiter. `music` adds a bed under it, fitted to the video's length and ducked under speech.
Leave it out and the system picks one for the video; `"auto"` or `{"auto": true, "mood": "calm"}`
says so explicitly; `null` means no music; a block with `file` uses your own track, which must
carry a licence (see `docs/music.md`):

```json
"audio": { "loudness": -16,
           "music": { "file": "music/bed.mp3", "gainDb": -20, "duckDb": -12, "start": 0, "fade": 1.5 } }
```

Licence fields (`license`, `title`, `artist`, `source`, `credit`) can sit in the music block or in
the track's `.license.json` sidecar.

## subtitles

```json
"subtitles": { "burn": true, "words": ["Heuristics", "Sawt"], "model": "base.en" }
```

`reel subtitles edit.json` transcribes what is said, locally, into `<build>/subtitles.srt`, in output
times. Read it and fix any word: renders use the file as it is (`--again` re-transcribes). `words`
steers the transcription toward names and jargon. With `burn`, cues are drawn near the bottom of
the window; either way the `.srt` is written beside every render, for platforms that take caption
files (LinkedIn, YouTube).
