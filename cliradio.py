#!/usr/bin/env python3
"""cliradio — Terminal Indian Radio Streaming Client.

Fetches live Indian radio stations from the Radio Browser API and plays them
through mpv. Inspired by ani-cli.

Usage:
  cliradio                   Interactive mode (list → select → play)
  cliradio --search <query>  Filter stations by query
  cliradio --refresh         Force-refresh the station cache
  cliradio --cache           Show cache info
  cliradio --help            Show this message
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_DIR = Path.home() / ".cache" / "cliradio"
CACHE_FILE = CACHE_DIR / "stations.json"
CACHE_TTL = 86_400  # 24 hours

API_BASE = "https://de1.api.radio-browser.info"
API_STATIONS = f"{API_BASE}/json/stations"

USER_AGENT = "cliradio/1.0 (terminal radio client)"

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fmt_age(t: float) -> str:
    h = (time.time() - t) / 3600
    if h < 1:
        return f"{h*60:.0f}m ago"
    if h < 24:
        return f"{h:.1f}h ago"
    return f"{h/24:.1f}d ago"


_TIMEOUT = 45


def _api_get(path: str) -> bytes:
    req = Request(f"{API_BASE}{path}", headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Station fetching / caching
# ---------------------------------------------------------------------------


FREQ_MAP: dict[str, list[str]] = {
    "93.5":  ["red fm", "redfm"],
    "98.3":  ["mirchi"],
    "92.7":  ["big fm", "bigfm"],
    "91.1":  ["radio city", "city fm", "cityfm"],
    "104":   ["fever"],
    "107.2": ["nasha"],
    "94.3":  ["radio one", "radioone"],
    "100.7": ["air fm gold", "air gold"],
    "102.6": ["air fm rainbow", "rainbow"],
    "106.4": ["hello fm", "hellofm"],
    "90.4":  ["radio dc"],
    "91.9":  ["radio mango", "radiomango"],
    "101.4": ["radio mantra"],
    "93.1":  ["vancover red fm"],
    "106.7": ["calgary red fm"],
}

LANG_SEARCHES = [
    "kannada", "malayalam", "telugu", "tamil",
    "marathi", "gujarati", "punjabi", "bengali",
    "odia", "assamese", "urdu",
]


def _fetch_json(path: str) -> list[dict]:
    return json.loads(_api_get(path))


def _enrich_freq(stations: list[dict]) -> None:
    """Attach a `freq` tag to stations matching known frequency mappings."""
    for freq, patterns in FREQ_MAP.items():
        for pat in patterns:
            for s in stations:
                n = s["name"].lower().replace(" ", "")
                if pat.replace(" ", "") in n:
                    existing = s.get("freq", "")
                    s["freq"] = f"{existing},{freq}" if existing else freq


def fetch_stations(refresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()

    if not refresh and CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            if now - data.get("fetched_at", 0) < CACHE_TTL:
                return data["stations"]
        except (json.JSONDecodeError, KeyError):
            pass

    console.print("[bold yellow] Fetching Indian radio stations from Radio Browser API ...")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    urls = ["/json/stations/bycountry/india?limit=500"]
    for lang in LANG_SEARCHES:
        urls.append(
            f"/json/stations/search?limit=50&countryCode=IN&language={lang}"
        )

    all_raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        fut = {pool.submit(_fetch_json, u): u for u in urls}
        for f in as_completed(fut):
            try:
                all_raw.extend(f.result())
            except Exception as e:
                console.print(f"[dim]  skipped: {fut[f]} — {e}[/]")

    seen: set[str] = set()
    stations: list[dict] = []

    for s in all_raw:
        url = (s.get("url_resolved") or s.get("url") or "").strip()
        name = (s.get("name") or "").strip()
        if not url or not name or url in seen:
            continue

        # skip unverified / dead stations
        if s.get("lastcheckok") != 1:
            continue
        br = s.get("bitrate", 0) or 0
        codec = (s.get("codec") or "").strip()
        if br == 0 and codec in ("", "UNKNOWN"):
            continue

        seen.add(url)

        stations.append({
            "name": name,
            "url": url,
            "tags": (s.get("tags") or "").strip(),
            "freq": "",
            "language": (s.get("language") or "").strip(),
            "state": (s.get("state") or "").strip(),
            "codec": codec,
            "bitrate": br,
            "votes": s.get("votes", 0) or 0,
        })

    _enrich_freq(stations)
    stations.sort(key=lambda x: (x["votes"], x["bitrate"]), reverse=True)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"fetched_at": now, "stations": stations}))
    console.print(f"[green]  Loaded {len(stations)} Indian radio stations (filtered for working streams)[/]\n")
    return stations


def show_cache() -> None:
    if not CACHE_FILE.exists():
        console.print("[yellow]No cache yet. Run cliradio to build one.[/]")
        return
    data = json.loads(CACHE_FILE.read_text())
    dt = datetime.fromtimestamp(data["fetched_at"], tz=timezone.utc)
    console.print(
        f"[cyan]Cache:[/] {len(data['stations'])} stations, "
        f"fetched {dt.strftime('%Y-%m-%d %H:%M UTC')} "
        f"[dim]({fmt_age(data['fetched_at'])})[/]"
    )


# ---------------------------------------------------------------------------
# Interactive station picker
# ---------------------------------------------------------------------------

PAGE_SIZE = 40


def pick_station(stations: list[dict]) -> dict | None:
    if not stations:
        console.print("[red]No stations found. Try --refresh.[/]")
        return None

    lines = [(i + 1, s) for i, s in enumerate(stations)]
    filtered = lines
    search = ""
    page = 0

    while True:
        total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
        start = page * PAGE_SIZE
        batch = filtered[start:start + PAGE_SIZE]

        # ── build table ──
        table = Table(box=ROUNDED, border_style="cyan", header_style="bold cyan")
        table.add_column("#", style="yellow", width=4)
        table.add_column("Station", style="white")
        table.add_column("Language / State", style="dim", width=32)
        table.add_column("Codec", style="dim", width=12)

        for idx, s in batch:
            name = s["name"]
            if s.get("freq"):
                name = f"{name}  [dim]({s['freq']})[/]"
            loc = " · ".join(filter(None, [s["language"], s["state"]])) or "—"
            codec = f"{s['codec']} {s['bitrate']}k" if s["bitrate"] else (s["codec"] or "—")
            table.add_row(str(idx), name[:55], loc[:32], codec[:12])

        # ── header ──
        h = Text()
        h.append(" cliradio ", style="bold white on blue")
        h.append(f"  ·  {len(stations)} Indian stations")
        if search:
            h.append(f"  ·  [filter: {search}]", style="yellow")
        if total_pages > 1:
            h.append(f"  ·  page {page+1}/{total_pages}", style="dim")

        console.clear()
        console.print(Panel(table, title=h, border_style="cyan"))
        console.print(
            "[dim]Type number to play  |  "
            "/text to filter  |  "
            "n/p page  |  "
            "r refresh  |  "
            "q quit[/]"
        )

        try:
            inp = Prompt.ask(">").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not inp:
            continue
        if inp == "q":
            return None
        if inp == "r":
            return {"_refresh": True}
        if inp == "n" and page < total_pages - 1:
            page += 1
            continue
        if inp == "p" and page > 0:
            page -= 1
            continue

        if inp.startswith("/"):
            search = inp[1:].strip().lower()
            page = 0
            q = search
            if q:
                filtered = [(i, s) for i, s in lines
                            if q in s["name"].lower()
                            or q in s["tags"].lower()
                            or q in s["language"].lower()
                            or q in s["state"].lower()
                            or q in s.get("freq", "").lower()]
            else:
                filtered = lines
            if not filtered:
                console.print("[yellow]No matches. Press Enter.[/]")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    return None
                search = ""
                filtered = lines
                page = 0
            continue

        try:
            sel = int(inp)
        except ValueError:
            continue

        if 1 <= sel <= len(filtered):
            return filtered[sel - 1][1]

    return None

# ---------------------------------------------------------------------------
# Playback via mpv
# ---------------------------------------------------------------------------


def play_station(station: dict) -> None:
    name = station["name"]
    url = station["url"]
    lang = station.get("language", "") or ""
    state = station.get("state", "") or ""
    codec = station.get("codec", "") or ""
    bitrate = station.get("bitrate", 0) or 0

    loc = f" · {state}" if state else ""
    meta = f"{codec} {bitrate}k" if bitrate else codec or "Stream"

    console.clear()

    info = Table.grid(padding=1)
    info.add_column(style="bold", width=12)
    info.add_column(style="white")
    info.add_row("Station:", Text(name, style="bold white"))
    info.add_row("Language:", lang or "—")
    info.add_row("Quality:", meta + loc)
    info.add_row("URL:", Text(url, style="dim italic"))

    console.print(Panel(
        info,
        title=Text(" \U0001f4fb  NOW PLAYING  ", style="bold white on green"),
        border_style="green",
    ))
    console.print(
        "\n[dim]mpv will open in a moment. "
        "Use mpv's own controls (Space=pause, q=stop).\n"
        "When mpv closes you'll return to the station list.[/]"
    )
    time.sleep(1)

    cmd = [
        "mpv",
        "--no-video",
        "--cache=yes",
        "--cache-secs=30",
        "--demuxer-max-bytes=8M",
        "--demuxer-max-back-bytes=2M",
        "--volume=65",
        f"--title=cliradio — {name}",
        url,
    ]

    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        console.print("[red]mpv not found. Install mpv and try again.[/]")
        input("[dim]Press Enter to continue ...[/]")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = [a.lower() for a in sys.argv[1:]]

    if "--cache" in args:
        show_cache()
        return
    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    refresh = "--refresh" in args
    stations = fetch_stations(refresh=refresh)

    # optional --search
    if "--search" in args:
        try:
            idx = args.index("--search")
            query = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else Prompt.ask("Search")
        except IndexError:
            query = Prompt.ask("Search")
        q = query.lower()
        stations = [s for s in stations
                    if q in s["name"].lower()
                    or q in s["tags"].lower()
                    or q in s["language"].lower()
                    or q in s["state"].lower()
                    or q in s.get("freq", "").lower()]
        if not stations:
            console.print("[yellow]No matches.[/]")
            return

    while True:
        s = pick_station(stations)
        if s is None:
            break
        if s.get("_refresh"):
            stations = fetch_stations(refresh=True)
            continue
        play_station(s)

    console.print("\n[bold cyan]☕ cliradio — tuning out.[/]")


if __name__ == "__main__":
    # handle SIGINT gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    main()
