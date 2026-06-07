# cliradio

**Terminal Indian Radio Streaming Client** — browse and play live Indian radio stations from your terminal.

```
$ cliradio

  ╭──────────────────────  cliradio   ·  461 Indian stations ──────────────────────╮
  │ ┌──────┬──────────────────┬──────────────────────────────────┬──────────────┐ │
  │ │  #   │ Station          │ Language / State                 │ Codec        │ │
  │ ├──────┼──────────────────┼──────────────────────────────────┼──────────────┤ │
  │ │  1   │ Radio Mirchi ... │ hindi · Mumbai                   │ MP3 128k     │ │
  │ │  2   │ Red FM 93.5      │ hindi · Delhi                    │ MP3 128k     │ │
  │ │  3   │ AIR FM Rainbow   │ hindi · Mumbai                   │ AAC 32k      │ │
  │ │ ...  │                                                        ...         │ │
  │ └──────┴──────────────────┴──────────────────────────────────┴──────────────┘ │
  │ Type number to play  |  /text to filter  |  n/p page  |  q quit              │
  │ > _                                                                          │
  ╰──────────────────────────────────────────────────────────────────────────────╯
```

## Features

-   Fetches **460+ live Indian radio stations** from the [Radio Browser API](https://api.radio-browser.info/)
-   Supports **all major Indian languages** — Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese, Urdu, and more
-   **Search by station name, language, city, or FM frequency** (e.g., `/93.5`)
-   Paginated station list with **ani-cli** style interaction
-   Plays via **mpv** — handles HTTP/ICY streaming, buffering, and all audio codecs
-   **Caches** station list locally (24h TTL) for instant startup
-   Works on **Arch Linux**, **Debian/Ubuntu**, **Fedora**, and any distro with mpv

## Dependencies

| Dependency | Notes |
|-----------|-------|
| **mpv** | Audio player — handles all streaming/decoding |
| **Python 3.10+** | Runtime |
| **rich** | Terminal UI (installed via pip) |

## Installation

### 1. Install mpv

**Arch Linux (including Arch-based like EndeavourOS, Manjaro):**
```bash
sudo pacman -S mpv
```

**Debian / Ubuntu / Linux Mint / Pop!_OS:**
```bash
sudo apt install mpv
```

**Fedora:**
```bash
sudo dnf install mpv
```

**openSUSE:**
```bash
sudo zypper install mpv
```

**Void Linux:**
```bash
sudo xbps-install mpv
```

**macOS (Homebrew):**
```bash
brew install mpv
```

**Termux (Android):**
```bash
pkg install mpv
```

### 2. Install cliradio

```bash
# Clone the repo
git clone https://github.com/Maneesh081/cliradio.git
cd cliradio

# Install the Python dependency
pip install rich

# Make it executable and add to PATH
chmod +x cliradio
# Optional: symlink to ~/.local/bin so you can run it from anywhere
ln -s "$(pwd)/cliradio" ~/.local/bin/
```

### 3. Run it

```bash
./cliradio
```

## Usage

### Interactive mode

```bash
cliradio
```

Starts the station browser. Controls inside:

| Input | Action |
|-------|--------|
| **`<number>`** | Play that station |
| **`/text`** | Filter stations by name, language, state, or frequency |
| **`n`** / **`p`** | Next / previous page |
| **`r`** | Refresh station list from API |
| **`q`** | Quit |

### Command-line options

```bash
cliradio --search tamil       # Pre-filter stations by query
cliradio --refresh            # Force re-fetch stations from API
cliradio --cache              # Show cache info
cliradio --help               # Show help
```

### During playback (mpv controls)

mpv takes over the terminal during playback:

| Key | Action |
|-----|--------|
| **Space** | Play / Pause |
| **q** | Stop and return to station list |
| **m** | Mute / Unmute |
| **0-9** | Set volume |
| **f** | Toggle fullscreen (if video, but disabled here) |

When mpv exits, you return to the station browser.

### Examples

```bash
# Browse all stations
cliradio

# Jump straight to Kannada stations
cliradio --search kannada

# Find a specific station by frequency
cliradio --search 98.3

# Refresh the station database
cliradio --refresh
```

## How it works

1.  cliradio fetches Indian radio stations from the Radio Browser API using parallel requests for better language coverage
2.  Stations are cached locally (`~/.cache/cliradio/stations.json`) so subsequent launches are instant
3.  You pick a station from the interactive list; cliradio launches **mpv** with the stream URL
4.  mpv handles all the hard parts — HTTP/ICY protocol, buffering, codec decoding, and audio output
5.  When you quit mpv, you're back in the station browser


## License

MIT
