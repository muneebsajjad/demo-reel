---
name: demo-reel
description: Make a polished product demo video (LinkedIn, X, a launch page, a store listing) by recording the real product in a browser, then framing, captioning and rendering it — end to end, with no video editor. Use when someone wants a demo, promo, launch or feature video, a screen recording made presentable, or "a video showing what my extension / web app does". macOS for recording.
---

# demo-reel

You produce the whole video yourself: the person gives you the product and what to show, and gets
back an MP4 they can post. Everything on screen is the real product, recorded live; the polish
(window frame, camera moves, captions, title and end cards) is added afterwards from the recording.

The pipeline, and the file each step makes:

| Step | Command | Makes |
|---|---|---|
| 1. Storyboard | you, with the person | 3–5 features, one caption each |
| 2. Scenario | write `scenario.mjs` | the steps a user would take |
| 3. Take | `bin/reel take scenario.mjs takes/take1` | `take1.mov` (picture + the app's sound), `take1.json` (events, element positions) |
| 4. Edit | write `edit.json` | scenes, shots, captions, brand |
| 5. Stills | `bin/reel check edit.json`, `bin/reel layers edit.json`, then `bin/reel stills edit.json 1,4,9` | problems found early; preview frames |
| 6. Subtitles | `bin/reel subtitles edit.json`, then read and fix `build/subtitles.srt` | what is said, as captions |
| 7. Render | `bin/reel render edit.json renders/x.mp4 --format all` | the video in each format, with its `.srt` |
| 8. Check | `bin/reel sheet renders/x.mp4 1,4,9,…` | contact sheet, length, loudness |

`examples/sawt/` is a complete worked example (a Chrome extension that reads articles aloud). Open
its `scenario.mjs` and `edit.json` before writing your own. `docs/edit-format.md` is the edit file
reference; `docs/lessons.md` lists what went wrong the first time, so read it before recording.

## 0. Setup (once)

Run `bin/reel doctor` first: it checks every tool and permission and says what to fix.
`bin/reel setup` builds the recorder (Swift, ScreenCaptureKit), installs `playwright-core` and Chrome
for Testing. Also needed: `ffmpeg`, `uv`, Google Chrome (to render the overlay layers). The terminal
running you needs **Screen & System Audio Recording** permission (System Settings → Privacy &
Security); if the recorder reports it is not permitted, ask the person to grant it and restart the
terminal.

## 1. Storyboard

Agree, in a few lines, before recording anything:
- the features, in order, each as a caption: a short kicker ("Word zoom") and a headline of at most
  two short lines, with the payoff in `<b>` ("Follow along. Each word<br><b>grows as it's spoken.</b>");
- what real content to demo on: a public page, a sample account, seed data. Pick content that makes
  the feature look its best and check it does (for Sawt: an article whose hard words get cards, on
  a site where the cards have room beside the column);
- the brand: accent colour, a light variant, background tints, logo; title and end card text.

Default format: 1080×1350 (4:5), 25–35 s — it fills the most of a phone feed, and most people watch
muted, so the captions must carry the story on their own. Ask where it will be posted: 1:1, 9:16 and
16:9 come from the same edit (`--format`), so offer them. Check stills of each format you render:
a shot that frames well in 4:5 can cut a heading in 1:1; nudge it per format (`"1:1": {"dy": 20}`).

When the product speaks (or the take has narration), make subtitles: `reel subtitles`, then read
the `.srt` and fix names and jargon before rendering — the transcription is good, not perfect.
Put hard words in `subtitles.words` to steer it.

## 2. Scenario

A scenario is an ES module (see `drive/take.mjs` for the full API):

```js
export const config = { url: "https://…", width: 1700, height: 1090, extension: "./ext" };
export async function setup(api) { /* settings, login; api.rect("title", "h1") for camera targets */ }
export async function run(api)   { /* the demo; api.mark("step") at every moment you will cut on */ }
export async function after(api) { /* stills to show as image scenes, e.g. a popup at 3x */ }
```

- **Mark every moment you will cut or move the camera on** (`api.mark("sentence", {n})`). The edit
  anchors to these marks, so a take that runs faster or slower still cuts in the right place.
- **Record camera targets with `api.rect(name, selector | fn, arg)`** in viewport pixels. Elements
  in a closed shadow root cannot be measured: compute where they will be (see the Sawt cards).
- **Click-driven products need a visible pointer.** Automation moves no real cursor, so shapes
  appear and buttons press by themselves. Call `api.pointer.show()` in `setup`, then drive with
  `api.pointer.click(selector | [x, y])`, `.drag(from, to)`, `.move(x, y)`, `.type(text)` and `.key(k)`:
  an on-page arrow follows, clicks ripple, moves are eased and typing has human rhythm. Click
  controls by selector (a `title` or `aria-label` is usually stable) so their positions come from
  the page.
- **Canvas content** (drawings, charts, maps) has no element to measure: record the box you drew
  into with `api.rect(name, {x, y, width, height})` in CSS px.
- Chrome extensions: run actions through the extension's own code with `api.inWorker(fn)`. An
  extension that relies on `activeTab` needs a recording copy with host access, because automation
  cannot press the browser's shortcuts (see `examples/sawt/prepare.sh`). Change nothing a viewer sees.
- Popups and other small UI: capture them in `after()` at deviceScaleFactor 3 with CDP (see the
  example), and show them as an image scene. Capture both states of a toggle at the same moment by
  clicking the real control, not by reloading.

Run it, then **look at the take** before editing: `ffmpeg -ss 6 -i takes/take1.mov -frames:v 1 x.png`
and read the PNG. Check the page is styled, the feature fired, nothing covers it. Retake freely —
a take costs a minute.

## 3. Edit

Write `edit.json` (reference: `docs/edit-format.md`). Rules that make it look made, not recorded:

- **Cut in pauses.** `bin/reel speech take1.mov` lists where there is sound; take pieces start
  just before a step and end before the next one starts. Anchor them to marks: `"sentence#5-0.15"`.
- **Side-by-side content does not fit tall windows.** A toolbar on the left and a diagram on the
  right can need more width than a 4:5 window shows; `reel check` warns, per format, how much a
  fitted shot will lose. Fit fewer things, or nudge the shot for that format.
- **Shots from rects.** `{"fit": ["title", {"rect": "card1", "dh": 330}], "pad": 60}`. One wide
  establishing shot, then push in to what the caption talks about. Keep text at least ~20 px tall in
  the output; a wide shot may go smaller for a moment, never for long.
- **One caption per scene**, in for the whole scene; switch captions only at a camera move.
- **Let moves breathe:** 1.0–1.5 s per camera move, hold at least 1.5 s after it lands.
- Title card 2–2.5 s, end card 3–3.5 s. Image scenes (a popup, a settings panel) 3–4 s.

## Speed

A 30-second 4:5 render takes about 3 minutes on a 6-core laptop: frames render in parallel chunks
(4 by default; `--jobs N`), joined without re-encoding, and unchanged layers are reused. While the
edit is still moving, use `reel render … --draft` (15 fps, fast encoder, about half the time) and
`reel stills`; render the real thing once the stills look right.

## 4. Check, every time

1. `bin/reel layers` and `bin/reel stills` at the start, middle and end of every scene and at each
   camera move. Read every PNG. Look for: cut-off text or UI at the frame edges, a half-visible
   heading at the top, a caption over something important, a frame that is all empty page.
2. Render, then `bin/reel sheet` across the whole video and read it.
3. Length should be what you planned; loudness about −16 LUFS when the product makes sound.
4. Sync: the moment a step appears on screen and its sound starts should match the take.

Then put the MP4 in front of the person, with the thumbnail (`build/layers/title.png`), and say
plainly what is real and what was changed for recording.

## Music

By default the system picks a bed that suits the video (`docs/music.md`): it profiles the video
(length, speech, pace, caption words), ranks licensed instrumental candidates — the person's own
`music/` folder, then the bundled CC0 library (`library/`), then online only if nothing local
fits — by measured tempo, energy and steadiness, and keeps the best. Run `reel music auto edit.json --audition renders/x.mp4`
to see the ranking and get a preview of the top tracks. You cannot hear, so hand the previews to the
person before calling the video done. When the best tracks are link-only (the site blocks scripted
downloads), give the person the links; they download one and run `reel music add <file> --candidate N`.
If they bring their own track, record its licence with `reel music add` and put it in the edit.
Always give them the `.credits.txt` beside the render, and say when its licence needs a published credit.

## Limits

- Recording is macOS only (ScreenCaptureKit). Compositing and layers run anywhere.
- Browser products only so far; a desktop app needs its own driver (accessibility scripting), but
  the recorder (`--app <bundle id>`) and everything after it already work for any app.
- Generating music (`reel music generate`) needs a local model wired in; ACE-Step is suggested but
  not yet tested with demo-reel.
