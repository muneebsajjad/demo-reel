# Bundled music

Seven short beds that cover the moods most product demos need, so the automatic choice works out
of the box, offline, with no licence to worry about. Each is a steady 75-second cut of a track its
artist released as **CC0** (public domain): use it in anything, commercial included, no credit
required. A credit is still a kind thing to give.

| File | Moods | Track | Artist | Source |
|---|---|---|---|---|
| `calm-no-cadillac.mp3` | calm, focused | No Cadillac | Loyalty Freak Music | [MINIMAL AMBIENT BOUNCE](https://archive.org/details/MINIMALAMBIENTBOUNCE) |
| `calm-nocturne.mp3` | calm, warm | Nocturne Op. 9 No. 2 (Chopin) | Musopen | [The Complete Chopin Collection](https://archive.org/details/musopen-chopin) |
| `focused-waiting.mp3` | focused, calm | Waiting TTTT | Loyalty Freak Music | [MINIMAL AMBIENT BOUNCE](https://archive.org/details/MINIMALAMBIENTBOUNCE) |
| `focused-after-party.mp3` | focused, upbeat | After Party | Loyalty Freak Music | [ROBOT DANCE !](https://archive.org/details/ROBOTDANCE) |
| `warm-chill-out.mp3` | warm, focused | Chill Out Theme | Komiku | [It's Time For Adventure! Vol 2](https://archive.org/details/Komiku-ItsTimeForAdventureVol2) |
| `upbeat-one-cool-minute.mp3` | upbeat, energetic | One Cool Minute | Loyalty Freak Music | [MINIMAL AMBIENT BOUNCE](https://archive.org/details/MINIMALAMBIENTBOUNCE) |
| `cinematic-something-to-save.mp3` | cinematic | Something to save | Komiku | [It's Time For Adventure! Vol 2](https://archive.org/details/Komiku-ItsTimeForAdventureVol2) |

Each file has a `.license.json` beside it with its source, licence, moods, the cut taken from the
original and a checksum. `library.json` lists them all.

## How they were chosen

Only artists who publish their own music as CC0 (uploader-set licences elsewhere can be wrong).
From about two dozen candidates, each was measured — tempo, energy, brightness, how much the volume
swings, how busy it is — and the steadiest fits per mood were kept, cut at their steadiest
75 seconds, faded at both ends and encoded at 112 kbps: about 1 MB each.

`python library/build.py` rebuilds every clip from its source and refuses if a source's licence
is no longer CC0 or public domain.

## Adding to it

Keep it small: a track earns a place by covering a mood the others do not. It must be CC0 or public
domain, released by the artist, under 1.5 MB. Add it to `TRACKS` in `build.py` and rebuild.
For anything else, use your own `music/` folder (see `docs/music.md`) — it is searched first.
