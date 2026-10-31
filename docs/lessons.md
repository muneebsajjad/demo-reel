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
