# Your first video in 10 minutes

You will record Tidy, a small task board that ships with demo-reel, and render a 20-second product
video from it: captions, camera moves, music, title and end cards. No account and no product of
your own needed. You need a Mac (recording uses macOS's screen capture).

## 1. Install (once, ~3 minutes)

```bash
git clone https://github.com/muneebsajjad/demo-reel ~/.claude/skills/demo-reel
cd ~/.claude/skills/demo-reel
export PATH="$PWD/bin:$PATH"
reel setup        # builds the recorder, installs Node packages and a test browser
reel doctor       # checks everything; fix anything it marks FAIL
```

`reel doctor` will most likely ask for one thing: **Screen & System Audio Recording** permission for
your terminal (System Settings → Privacy & Security). Turn it on and restart the terminal.

## 2. Record a take (~1 minute)

```bash
cd examples/tidy
reel take scenario.mjs takes/take1
```

A browser window opens, a pointer adds a task, drags two cards and switches to dark mode, then the
window closes. Leave it alone while it runs (other windows will not be recorded, but the browser
needs to stay on screen). You get `takes/take1.mov` and `takes/take1.json`; the second lists every
moment the scenario marked and where things were on the page.

Open `scenario.mjs` to see how: `api.pointer.click(...)`, `.drag(...)`, `.type(...)`, and
`api.mark("move")` before each step the edit will cut on.

## 3. Check the edit and look at stills (~1 minute)

```bash
reel check edit.json                    # problems and warnings, before rendering
reel stills edit.json 1,4,8,12,16,19    # frames at those seconds, in build/stills/
```

Open the PNGs in `build/stills/`. `edit.json` is the whole video: scenes, camera shots fitted around
page elements, captions, brand colours. Change a caption's text and run `reel stills` again.

## 4. Render (~3 minutes)

```bash
reel render edit.json renders/tidy.mp4 --draft      # quick preview (15 fps)
reel render edit.json renders/tidy.mp4              # the real thing
reel render edit.json renders/tidy.mp4 --format all # 4:5 and 16:9
```

Tidy makes no sound, so the system picked music from the bundled CC0 library to suit the video;
`renders/tidy.credits.txt` says which track and that no credit is needed.

## 5. Make it yours

- Your web app: copy `examples/tidy`, point `config.url` at your app, rewrite the steps in
  `scenario.mjs`, and `api.rect(...)` whatever the camera should frame.
- Your Chrome extension: see `examples/sawt` (it loads an unpacked extension and talks to it).
- With Claude Code, skip all of this and ask: *"Make a 30-second demo video of my app at
  localhost:3000 showing X, Y and Z."* The skill (`SKILL.md`) does the rest.

Stuck? Open an issue with what you tried and what happened: https://github.com/muneebsajjad/demo-reel/issues
