#!/usr/bin/env python3
"""Render the Debug Soundtrack panel from a public YouTube playlist.

Replaces the lowlighter/metrics music plugin, which gave no control over
layout. Scrapes the playlist page for track metadata, centre-crops each
thumbnail to a square, and writes a self-contained SVG.

Exits 0 without touching the output when the scrape fails, so a YouTube
hiccup leaves the previous panel in place instead of breaking the profile.
"""

import base64
import html
import io
import json
import os
import re
import sys
import urllib.request

PLAYLIST = os.environ.get("PLAYLIST_URL", "https://music.youtube.com/playlist?list=PLWJzcQJwrVbM")
OUT = os.environ.get("OUT_PATH", "metrics/music.svg")
LIMIT = int(os.environ.get("TRACK_LIMIT", "6"))

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# tokyonight, to match the other README panels
BG = "#1a1b27"
ACCENT = "#70a5fd"
TITLE = "#c0caf5"
MUTED = "#7f88a8"
DIM = "#565f89"
ROW = "#ffffff"

W = 480
PAD = 16
ART = 34
ROW_H = 46
HEAD_H = 58
FONT = "'Segoe UI',Ubuntu,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"

# Rough per-character advance ratios for proportional sans at 1px, used to
# truncate text (SVG has no ellipsis).
NARROW = set("ijltfrI.,:;'!|()[]{}-/\\ ")
WIDE = set("mwMW@")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def text_width(s, size):
    total = 0.0
    for ch in s:
        if ch in NARROW:
            total += 0.30
        elif ch in WIDE:
            total += 0.88
        elif ch.isupper() or ch.isdigit():
            total += 0.62
        else:
            total += 0.53
    return total * size


def truncate(s, size, max_px):
    if text_width(s, size) <= max_px:
        return s
    ell = "…"
    while s and text_width(s + ell, size) > max_px:
        s = s[:-1]
    return s.rstrip() + ell


def walk(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, key)


def first(gen, default=None):
    for x in gen:
        return x
    return default


def scrape(url):
    """Return (playlist_title, [track dicts])."""
    canonical = url.replace("music.youtube.com", "www.youtube.com")
    page = fetch(canonical).decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", page)
    if not m:
        raise RuntimeError("ytInitialData not present in playlist page")
    data = json.loads(m.group(1))

    # og:title is the playlist name; ytInitialData's first "title" is a track.
    og = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    name = html.unescape(og.group(1)) if og else "Playlist"

    tracks = []
    for lockup in walk(data, "lockupViewModel"):
        meta = first(walk(lockup, "lockupMetadataViewModel"))
        if not meta:
            continue
        title = (meta.get("title") or {}).get("content")
        if not title:
            continue

        artist = ""
        rows = first(walk(meta, "metadataRows"), [])
        for row in rows:
            for part in row.get("metadataParts", []):
                candidate = (part.get("text") or {}).get("content", "")
                # Skip view counts / dates, keep the channel name
                if candidate and not re.search(r"\d+\s*(views?|ago)", candidate):
                    artist = candidate
                    break
            if artist:
                break
        artist = re.sub(r"\s*-\s*Topic$", "", artist).strip()

        duration = ""
        for badge in walk(lockup, "thumbnailBadgeViewModel"):
            if badge.get("text") and re.match(r"^\d+:\d{2}", badge["text"]):
                duration = badge["text"]
                break

        sources = first(walk(lockup, "sources"), [])
        thumb = ""
        if isinstance(sources, list):
            usable = [s for s in sources if isinstance(s, dict) and s.get("url", "").startswith("http")]
            if usable:
                thumb = max(usable, key=lambda s: s.get("width", 0))["url"]

        tracks.append({"title": title, "artist": artist, "duration": duration, "thumb": thumb})
        if len(tracks) >= LIMIT:
            break

    if not tracks:
        raise RuntimeError("no tracks parsed from playlist page")
    return name, tracks


def artwork(url, px=68):
    """Centre-crop a 16:9 thumbnail to a square data URI."""
    from PIL import Image
    raw = fetch(url, timeout=20)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build(name, tracks):
    height = HEAD_H + len(tracks) * ROW_H + 12
    dur_w = 44
    title_max = W - PAD * 2 - ART - 12 - dur_w - 8

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" role="img" aria-label="Debug Soundtrack">',
        "<defs>",
        '<clipPath id="art"><rect width="%d" height="%d" rx="5"/></clipPath>' % (ART, ART),
        "</defs>",
        f'<rect width="{W}" height="{height}" rx="10" fill="{BG}"/>',
        f'<g font-family="{FONT}">',
        # header
        f'<circle cx="{PAD + 7}" cy="24" r="7.5" fill="none" stroke="{ACCENT}" stroke-width="1.5"/>',
        f'<path d="M{PAD + 5} 20.5 L{PAD + 10.5} 24 L{PAD + 5} 27.5 Z" fill="{ACCENT}"/>',
        f'<text x="{PAD + 22}" y="28" fill="{ACCENT}" font-size="14" font-weight="600">Debug Soundtrack</text>',
        f'<text x="{W - PAD}" y="28" fill="{DIM}" font-size="10" text-anchor="end">YouTube Music</text>',
        f'<text x="{PAD}" y="45" fill="{MUTED}" font-size="10.5">'
        f'{html.escape(truncate(name, 10.5, W - PAD * 2 - 90))} · refreshed daily</text>',
    ]

    y = HEAD_H
    for i, t in enumerate(tracks):
        if i % 2 == 0:
            out.append(f'<rect x="{PAD - 6}" y="{y}" width="{W - (PAD - 6) * 2}" height="{ROW_H - 4}" '
                       f'rx="6" fill="{ROW}" fill-opacity="0.025"/>')
        art_y = y + (ROW_H - 4 - ART) / 2
        if t.get("data"):
            out.append(f'<g transform="translate({PAD},{art_y})">'
                       f'<image href="{t["data"]}" width="{ART}" height="{ART}" clip-path="url(#art)"/>'
                       f'<rect width="{ART}" height="{ART}" rx="5" fill="none" '
                       f'stroke="{ROW}" stroke-opacity="0.08"/></g>')
        else:
            out.append(f'<rect x="{PAD}" y="{art_y}" width="{ART}" height="{ART}" rx="5" '
                       f'fill="{ROW}" fill-opacity="0.06"/>')

        tx = PAD + ART + 12
        out.append(f'<text x="{tx}" y="{y + 18}" fill="{TITLE}" font-size="12.5" font-weight="500">'
                   f'{html.escape(truncate(t["title"], 12.5, title_max))}</text>')
        if t["artist"]:
            out.append(f'<text x="{tx}" y="{y + 32}" fill="{MUTED}" font-size="10.5">'
                       f'{html.escape(truncate(t["artist"], 10.5, title_max))}</text>')
        if t["duration"]:
            out.append(f'<text x="{W - PAD}" y="{y + 25}" fill="{DIM}" font-size="10.5" '
                       f'text-anchor="end" font-family="ui-monospace,SFMono-Regular,Consolas,monospace">'
                       f'{html.escape(t["duration"])}</text>')
        y += ROW_H

    out.append("</g></svg>")
    return "\n".join(out)


def main():
    try:
        name, tracks = scrape(PLAYLIST)
    except Exception as exc:
        print(f"::warning::could not read playlist ({exc}); keeping existing panel")
        return 0

    for t in tracks:
        try:
            t["data"] = artwork(t["thumb"]) if t["thumb"] else ""
        except Exception as exc:
            print(f"::warning::artwork failed for {t['title']}: {exc}")
            t["data"] = ""

    svg = build(name, tracks)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {OUT} ({len(svg)} bytes, {len(tracks)} tracks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
