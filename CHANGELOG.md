# Changelog

## 0.2.0

- **Formats**: one edit renders 4:5, 1:1, 9:16 and 16:9 (`--format all`); shots adapt to each window,
  and can be nudged per format.
- **Subtitles**: what is said is transcribed locally into an editable `.srt`, exported with every
  render and optionally burned in.
- **Music**: picked automatically to suit the video from a bundled CC0 library (or yours); every
  track's licence is recorded and checked, and credits are written for you.
- **Click-and-drag products**: a visible on-page pointer with human pacing (`api.pointer`), and
  literal camera targets for canvas content.
- **Speed**: about 3x faster: parallel chunks joined without re-encoding, cheaper frames, all
  layers in one browser session; `--draft` for previews.
- **Safety nets**: `reel check` validates an edit (and warns when a shot cannot fit a format),
  `reel doctor` checks a machine, 89 tests and CI.
- **Tidy**, a demo app to make your first video with (`docs/first-video.md`).

## 0.1.0

- First release: record a browser product on macOS, frame, caption and render a 4:5 MP4.
