# cliradio — How It Works

## Overview

cliradio is a terminal-based Indian radio streaming client. It:

1. Fetches live Indian radio station metadata from the **Radio Browser API**
2. Displays an interactive, searchable station list in the terminal (ani-cli style)
3. Streams the selected station via **mpv** (which handles HTTP/ICY, buffering, and audio decoding)
4. Returns to the station picker when playback ends

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     cliradio.py                      │
│                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────┐  │
│  │ fetch_stations│──>│ pick_station │──>│play_stn │  │
│  │ (API + cache) │   │ (rich Table) │   │(subproc)│  │
│  └──────┬───────┘   └──────────────┘   └────┬────┘  │
│         │                                   │       │
│         ▼                                   ▼       │
│  ┌──────────────┐                   ┌──────────────┐ │
│  │~/.cache/     │                   │  mpv process │ │
│  │cliradio/     │                   │  (STDOUT=null)│ │
│  │stations.json │                   │  STDIN=term  │ │
│  └──────────────┘                   └──────────────┘ │
└─────────────────────────────────────────────────────┘
```

Three layers:

| Layer | Technology | Role |
|-------|-----------|------|
| **Data** | Radio Browser API + local JSON cache | Discover & store station metadata |
| **UI** | Rich (Python) | Terminal table, search, selection |
| **Playback** | mpv subprocess | Network I/O, decode, audio output |

---

## 1. Radio Browser API

The [Radio Browser](https://api.radio-browser.info/) project maintains a public, crowd-sourced directory of thousands of internet radio stations worldwide.

### Endpoint used

```
GET /json/stations/bycountry/india?limit=200
```

Returns a JSON array of station objects sorted by click popularity.

### Station object (relevant fields)

```json
{
  "name": "Radio Mirchi 98.3",
  "url": "http://example.com/listen.pls",
  "url_resolved": "http://example.com/stream.mp3",
  "country": "India",
  "countrycode": "IN",
  "language": "hindi",
  "state": "Mumbai",
  "tags": "bollywood, hindi",
  "codec": "MP3",
  "bitrate": 128,
  "votes": 8413,
  "clickcount": 2350,
  "lastcheckok": 1
}
```

### How cliradio processes it

- Only stations where `lastcheckok == 1` (verified working) are included
- `url_resolved` is preferred over `url` (some stations give a .pls redirect URL that resolves to the actual stream)
- Duplicates are removed by comparing resolved URLs
- Results are sorted by `votes` (community trust signal)

### Caching

The API is slow (~5-8 seconds for 200 stations). To avoid waiting on every launch:

- JSON response is cached to `~/.cache/cliradio/stations.json`
- Cache TTL is 24 hours
- `--refresh` flag overrides and re-fetches

---

## 2. How Internet Radio Streaming Works

### The HTTP/ICY Protocol

Most internet radio stations use **ICY** (I Can Yell) protocol — a variant of HTTP designed for audio streaming. It works like this:

1. **Client sends an HTTP GET** request to the stream URL
2. **Server responds** with `ICY 200 OK` instead of `HTTP/1.1 200 OK` (ICY is a non-standard but widely supported extension)
3. **Headers include:**
   - `icy-metaint: 8192` — interval (in bytes) at which metadata appears in the stream
   - `icy-name: My Radio` — station name
   - `icy-genre: Pop`
   - `icy-br: 128` — bitrate
4. **Body is a continuous flow** of audio data frames, interleaved with metadata chunks at the `icy-metaint` interval

### Data flow

```
[Radio Station Server]
       │
       │ HTTP GET /stream.mp3
       ▼
[ICY 200 OK]
[icy-metaint: 8192]
[icy-name: ...]
       │
       ▼
┌─────────────────────────────────┐
│   Audio Data (MP3/AAC/OGG)     │  ◄── 8192 bytes
├─────────────────────────────────┤
│   Metadata block (title, etc.) │  ◄── variable length
├─────────────────────────────────┤
│   Audio Data (MP3/AAC/OGG)     │
├─────────────────────────────────┤
│   Metadata block               │
├─────────────────────────────────┤
│            ...                  │
└─────────────────────────────────┘
```

### Codec negotiation

- The server tells client the codec via the `Content-Type` header (`audio/mpeg`, `audio/aac`, `audio/ogg`) or via the ICY headers
- cliradio delegates all of this to **mpv**, which auto-detects the codec and handles decoding

### Why mpv instead of python-vlc

| Factor | mpv (subprocess) | python-vlc |
|--------|-----------------|------------|
| Simplicity | `subprocess.run(["mpv", url])` | Requires VLC libs, complex instance mgmt |
| Reliability | Battle-tested on every platform | Platform-specific quirks |
| Codec support | FFmpeg backend — everything | Depends on VLC build |
| Terminal UX | Takes over terminal (ani-cli style) | Embedding is complex |
| Dependencies | Just `mpv` binary | VLC + python-vlc bindings |

Using mpv as a subprocess also gives us "free" features:
- Cache/buffering management
- Codec auto-detection
- Network error recovery
- Volume control (mpv's own `0`-`9`, `m` for mute)
- Pause/resume (Space)
- Seeking in streams

---

## 3. CLI Interaction Model (ani-cli style)

The UX is modelled after [ani-cli](https://github.com/pystardust/ani-cli) — a terminal anime streaming tool:

```
┌─────────────────────────────────────────────────────────┐
│  █ cliradio  ·  163 Indian stations  ·  page 1/5        │
├──────────┬──────────────────────────────────────────────┤
│  #│ Station              │ Language / State │ Codec     │
│──┼───────────────────────┼─────────────────┼───────────│
│ 1 │ Radio Mirchi 98.3   │ hindi · Mumbai   │ MP3 128k  │
│ 2 │ Red FM 93.5         │ hindi · Delhi    │ MP3 128k  │
│ 3 │ AIR FM Rainbow      │ hindi · Mumbai   │ AAC 32k   │
│ 4 │ Hello FM 106.4      │ tamil · Chennai  │ MP3 64k   │
│ ...                                                      │
├──────────┴──────────────────────────────────────────────┤
│ Type number to play  │  /text to filter  │  q quit       │
│ > _                                                     │
└─────────────────────────────────────────────────────────┘
```

### User commands

| Input | Action |
|-------|--------|
| `<number>` | Play selected station |
| `/text` | Search/filter by name, language, state, or tags |
| `n` / `p` | Next / previous page |
| `r` | Refresh station list from API |
| `q` | Quit |

### During playback

mpv takes over the terminal entirely (just like ani-cli). The user gets mpv's native OSD and controls. When mpv exits (user presses `q` in mpv), control returns to the station picker.

---

## 4. Code Walkthrough

### `cliradio.py` structure

```
fetch_stations(refresh=False)
  ├── Check cache (JSON) → return if fresh
  ├── GET Radio Browser API → parse JSON
  ├── Deduplicate & sort stations
  ├── Write cache file
  └── Return list[dict]

pick_station(stations)
  ├── Build rich.Table from station list
  ├── Loop: display table → read input
  ├── Input handlers: number, /search, n/p, r, q
  └── Return selected station dict

play_station(station)
  ├── Clear terminal
  ├── Print "Now Playing" Panel (rich)
  ├── subprocess.run(["mpv", ...url...])
  └── Return when mpv exits

main()
  ├── Parse CLI args (--search, --refresh, --cache)
  ├── Load stations
  ├── Loop: pick → play → pick → ...
  └── Clean exit
```

### Key design decisions

**Why subprocess instead of Python bindings?**
- Simpler, more portable, matches ani-cli philosophy
- mpv's native controls work out of the box
- No complex IPC or event loop needed

**Why Rich instead of curses/fzf?**
- Simpler to implement
- Pagination and search are straightforward
- Fzf adds a dependency; Rich is pure Python

**Why cache the station list?**
- Radio Browser API can be slow (5-10 seconds)
- Station data changes infrequently
- Cache avoids the wait on every launch

---

## 5. Dependencies

| Dependency | Purpose |
|-----------|---------|
| **mpv** | Audio streaming, decoding, playback |
| **Python 3.10+** | Runtime |
| **requests** | HTTP calls to Radio Browser API (stdlib `urllib` used instead to keep it zero-dep) |
| **rich** | Terminal UI (tables, panels, styling) |

Actually, cliradio uses only `rich` from PyPI + stdlib. `urllib.request` replaces `requests` to minimize dependencies.

---

## 6. Future Extensions

The architecture makes it easy to add:

- **Global stations**: Change API path from `bycountry/india` to `bycountry/<any>` or add a country selector
- **Genre filtering**: Add `/genre/<genre>` endpoint or tag-based filtering
- **Favorites**: Save favorite stations locally
- **Recording**: mpv supports `--record-file=out.mp3` for stream recording
- **TUI mode**: Replace the Prompt-based picker with a full curses/fzf interface
- **Now playing metadata**: Parse ICY metadata from the stream to show current song title

---

## 7. Comparison with the Old Web GUI

| Aspect | Old (retro-music-player) | New (cliradio) |
|--------|------------------------|----------------|
| Type | Web app (HTML/CSS/JS) | Terminal CLI (Python) |
| Source | YouTube + static radio list | Radio Browser API (live) |
| Radio stations | 77 hardcoded URLs | 150+ live from API |
| Streaming | YouTube iframe + audio element | mpv (native) |
| Search | Manual by city/genre | Full-text + filters |
| Dependencies | Browser, YouTube API key | mpv + Python + rich |
| Platform | Desktop + mobile web | Linux/macOS terminal |

The old app had a hardcoded list of 77 Indian radio stations, all pointing to placeholder radiojar URLs. The new app fetches 150+ real, verified stations directly from the Radio Browser API, sorted by community votes — so the best stations appear first.
