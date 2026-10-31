# Lessons

What went wrong making the first video (Sawt 0.2), and what the tools now do about it. Read this
before recording a new product.

## Recording

- **Branded Google Chrome ignores `--load-extension`.** Use Chrome for Testing (`reel setup` installs
  it); `drive/browser.mjs` finds it.
- **`activeTab` extensions do nothing under automation.** The permission comes from a real keypress
  or click on the browser's own UI, which automation cannot make. Record with a copy that adds host
  access, and change nothing else (`examples/sawt/prepare.sh`). Say so when you hand the video over.
- **Chrome's sound comes from helper processes** that ScreenCaptureKit does not list as
  applications. Capturing "only Chrome" gave a silent track. The recorder excludes every *other*
  app instead, which keeps the helpers' sound and still keeps everything else out.
- **Playwright mutes audio and adds warning bars by default** (`--mute-audio`, `--enable-automation`,
  `--no-sandbox`). `browser.mjs` removes them. Chrome for Testing still shows its own "only for
  automated testing" bar; it sits above the page viewport, which is all the compositor uses.
- **The recorder's stdout must be line-buffered**, or the driver only learns recording started
  when it ends. It is, and it speaks JSON lines.
- **The window can open on another display** when the main display changes. The recorder records
  whichever display holds the app's largest window and reports where it is.
- **Pages can arrive unstyled.** A take of bare HTML is useless; the driver waits for every
  stylesheet before recording and stops with an error if they do not load.
- **Timings drift between takes** (a cold cache took 25 s to start reading). Anchor every edit time
  to an event the scenario marks.

## Content

- **Choose the page for the feature.** Wikipedia had no room beside the column for Sawt's cards;
  paulgraham.com exposed a placement bug (no `<p>` elements); a Substack essay worked. Look at the
  feature on a candidate page before committing to it.
- **Measure, do not eyeball.** Positions now come from `api.rect` in the scenario, in the same
  pixels as the recording. Select elements by text where structure is unreliable (the first `<p>`
  on that Substack page was a heading).
- **Capture small UI at 3x through CDP** (`Emulation.setDeviceMetricsOverride` and
  `Page.captureScreenshot`); Playwright's own screenshot of a persistent context came out at 1x.
- **Two states of a toggle should be the same moment**: click the real control between the two
  captures rather than reloading, or the rest of the UI moves on (a progress counter did).

## Editing

- **Dissolving between two shots of a text page overlaps two layouts** and looks broken. Between
  take scenes the compositor dips through the page colour instead.
- **Downscaling text needs a real resampler.** The compositor crops and resizes with Lanczos from the
  2x recording, so text stays crisp at any zoom without shimmer.
- **Clamp crop boxes to the page**; a box edge of −1e−13 fails the resize.
- **Loudness: one fixed gain, then a limiter.** A single `loudnorm` pass over a track with long
  silences under-shot badly (−19.8 LUFS for −16). Two-pass `loudnorm` with `linear=true` silently
  falls back to dynamic mode when it cannot stay linear, and then swelled a music bed by 7 dB in the
  pauses. The compositor now measures the integrated loudness, applies one gain and limits peaks.
- **Measure what you cannot hear.** To check ducking, the test bed was a 7 kHz tone, where speech
  has little energy, and its level was read per half second. (Resampling that check to 8 kHz first
  removes the tone and makes it look missing.)
- **Most viewers are muted.** Captions carry the story; the voice is a bonus.

## Music

- **Pick by measurement, then by ear.** The system scores tracks on tempo, energy, steadiness and
  busy-ness against the video's profile, but an agent cannot hear: the person gets previews of the
  top few before a video is called done.
- **Respect sites that refuse scripts.** ccMixter answers 403 to scripted downloads. Its tracks are
  ranked from catalogue data and handed over as links; nothing pretends to be a browser.

## A second product (Excalidraw, a drawing app)

What a click-and-drag product with no sound changed:

- **No pointer, no story.** Shapes appeared and colours changed with nothing doing it. The driver
  now draws an on-page pointer that follows the automated mouse, with a ripple on click, eased
  moves along a slight curve, and typing at a human rhythm.
- **Canvas drawings have no element**, so `api.rect` takes a literal box: the one you drew into.
- **Portrait windows are narrow.** A shot fitting a side panel and a diagram needed 2488 px of page
  width; a 4:5 window shows 1943, so 22% was silently cut. `reel check` now warns about it for each
  format the edit renders.
- **Silence is handled by music.** With no voice, the auto-picker read the captions (warm), the pace
  and the length, chose a bundled bed offline and set it louder than it would sit under speech.
- **Wait for the page, then act through its controls.** Clicking by `title` / `aria-label`
  survived the panel appearing in a different place than in the probe.

## Speed

- **Measure before optimising.** A profile showed the time in full-frame overlay blends (a caption
  covers a strip, but every pixel was blended), Lanczos resizes and fresh dither noise every frame.
  Blending only each overlay's box and reusing a few noise frames cut a quarter of the frame time.
- **Chunks in parallel, joined without re-encoding.** Workers render frame ranges with the same
  encoder settings; the concat demuxer joins them and the sound is added once. Workers must not
  depend on earlier frames: readers start near their chunk, and an image scene finds its backdrop
  itself. Four chunks were as fast as six on 6 cores: the work is CPU-bound by then.
- **Check alignment where things move.** A frame-matching test said two chunk starts were shifted;
  they fell in still moments where every neighbour matches. Where there is motion, the match is exact.
- **One browser for all the layers.** Seventeen Chrome launches took 77 s; one session takes 6 s.
  Branded Chrome's headless mode stopped painting 88 px short of a 1350 px page on this Mac, so
  layer shots use Playwright's headless shell. Unchanged layers are not rendered again at all.
- **macOS ships bash 3.2**, where an empty array under `set -u` is an error: `reel render` without
  `--format` failed. Expand optional arrays as `${a[@]+"${a[@]}"}`.
