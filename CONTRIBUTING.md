# Contributing

Thanks for helping. demo-reel grows from real videos: the most useful contribution is trying it on
your product and telling us what got in the way.

## Ways to help

- **Try it on your product** and open an issue with the product type, what you wanted to show, and
  where it went wrong (the "My product" issue template asks for exactly this).
- **Card and caption templates**: `layers/templates.py`. New looks for title and end cards, caption
  styles, other key-toast designs.
- **Transitions and scene types**: `compose/compose.py` (wipes, split before/after, zoom on a click).
- **Bundled music**: a CC0 track that covers a mood the library lacks (`library/README.md` has the rules).
- **Drivers for more kinds of product**: desktop apps (accessibility scripting), terminals.

Issues labelled **good first issue** are small and self-contained.

## Working on the code

```bash
reel setup && reel doctor
uv run --group dev pytest -q        # unit tests and an end-to-end render; needs ffmpeg and Chrome
```

- Keep the pure logic (times, shots, layouts, music rules) in plain modules with tests;
  `tests/test_render.py` renders a synthetic take end to end, so changes to the compositor are
  checked for framing, sound placement and length.
- When something surprised you, add it to `docs/lessons.md`: what happened and what the tools now
  do about it. It is the most useful document in the repo.
- Any music added to `library/` must be CC0 or public domain, released by the artist, and go
  through `library/build.py` so its source and cut are recorded.

## Pull requests

Small and focused, with a sentence on why. If it changes what a video looks like, include a still
(`reel stills`). CI runs the tests on Linux and builds the recorder on macOS.

## Conduct

Be kind and assume good intent. Harassment of any kind is not tolerated.
