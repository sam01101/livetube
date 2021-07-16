# Livetube

Livetube is a library aims to YouTube's internal API (innertube)

## Documentation

No documentation, welcome to Pull Request.

## Features

- Video `Metadata Extraction`, with `Livestream`, `Premiere` and `Members Only` support
  - Livestream metadata, heartbeat, fetch player
  - Get animated thumbnail (Video only)
  - Show video type tag (`Members only`, `Unlisted`, `Private`)
- `Community Post fetching` with `Attachment`
     - - [x] Video
     - - [x] Image (With listed image)
     - - [x] Poll
     - - [x] Playlist
     - - [x] Shared Post
     - - [x] Members only post
- `Purchases and memberships` list fetch
  - `YouTube Music` `YouTube Premium` basic extraction
  - Channel ID
  - Expire status
  - Expire date
- Basic Studio functionality
  - Upload video
  - Create playlist

Extra:
- [aiohttp] Connection reuse to reduce memory usage
- Request `html <-> json API` use/fallback

_P.S. Please figure out how to get a `bgResponse` yourself, I don't want Google blame me._

## Installation

```bash
$ python -m pip install livetube
```

## Others

This package supports `3.7` and `3.8`, but no CLI support, I'm sorry if I let you down because of this.

This code quality is bad, I'll find a time to do this.
