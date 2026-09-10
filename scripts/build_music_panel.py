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

from svg_common import (DIM, MONO, MUTED, NARROW_MAX, NARROW_REF, ROW, TITLE,
                        WIDE_REF, card_close, esc, fluid_open, right, truncate)

PLAYLIST = os.environ.get("PLAYLIST_URL", "https://music.youtube.com/playlist?list=PLWJzcQJwrVbM")
OUT = os.environ.get("OUT_PATH", "metrics/music.svg")
LIMIT = int(os.environ.get("TRACK_LIMIT", "8"))

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# The panel is full width whatever the column is, so the two layouts are
# defined by how many tracks fit rather than by pixels: two columns of four
# on anything above the breakpoint, one column of five below it. Tracks run
# down one column then the next, so they are numbered to keep the reading
# order unambiguous.
PAD = 20
NARROW_PAD = 14
HEAD_H = 46
WIDE_ROWS, WIDE_ROW_H, WIDE_ART = 4, 65, 44
NARROW_ROWS, NARROW_ROW_H, NARROW_ART = 5, 52, 36
HEIGHT = HEAD_H + max(WIDE_ROWS * WIDE_ROW_H, NARROW_ROWS * NARROW_ROW_H) + 4


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return urllib.request.urlopen(req, timeout=timeout).read()


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


def rows(tracks, cols, per_col, row_h, art, pad, budget, clip):
    """One layout's worth of track rows, laid out inside `cols` columns."""
    out = []
    col_w = 100 / cols
    num_w, dur_w = 18, 40
    text_x = pad + num_w + art + 12
    title_max = budget / cols - text_x - dur_w - 8

    for i, t in enumerate(tracks):
        col, row = divmod(i, per_col)
        y = HEAD_H + row * row_h
        out.append(f'<svg x="{col * col_w}%" y="0" width="{col_w}%" height="100%">')
        if row % 2 == 0:
            out.append(f'<rect x="{pad - 8}" y="{y}" height="{row_h - 6}" rx="7" '
                       f'fill="{ROW}" fill-opacity="0.03" '
                       f'style="width:calc(100% - {(pad - 8) * 2}px)"/>')
        out.append(f'<text x="{pad + 6}" y="{y + row_h / 2 - 1}" fill="{DIM}" font-size="11" '
                   f'text-anchor="middle" font-family="{MONO}">{i + 1}</text>')

        art_x, art_y = pad + num_w, y + (row_h - 6 - art) / 2
        if t.get("data"):
            out.append(f'<g transform="translate({art_x},{art_y})">'
                       f'<image href="{t["data"]}" width="{art}" height="{art}" '
                       f'clip-path="url(#{clip})"/>'
                       f'<rect width="{art}" height="{art}" rx="6" fill="none" '
                       f'stroke="{ROW}" stroke-opacity="0.1"/></g>')
        else:
            out.append(f'<rect x="{art_x}" y="{art_y}" width="{art}" height="{art}" rx="6" '
                       f'fill="{ROW}" fill-opacity="0.06"/>')

        mid = y + row_h / 2
        out.append(f'<text x="{text_x}" y="{mid - 3}" fill="{TITLE}" font-size="14.5" '
                   f'font-weight="500">{esc(truncate(t["title"], 14.5, title_max))}</text>')
        if t["artist"]:
            out.append(f'<text x="{text_x}" y="{mid + 13}" fill="{MUTED}" font-size="12.5">'
                       f'{esc(truncate(t["artist"], 12.5, title_max))}</text>')
        if t["duration"]:
            out.append(right(pad, f'<text x="100%" y="{mid + 4}" fill="{DIM}" font-size="11" '
                                  f'text-anchor="end" font-family="{MONO}">'
                                  f'{esc(t["duration"])}</text>'))
        out.append("</svg>")
    return out


def build(name, tracks):
    """The soundtrack panel, carrying both layouts in one fixed-height box.

    A phone column cannot hold two columns of tracks, and the box cannot get
    taller on a phone to make up for it (an SVG's height is fixed by its
    attribute, whatever a media query says), so the narrow layout shows five
    tracks in one column where the wide one shows eight in two.
    """
    wide = tracks[:WIDE_ROWS * 2]
    narrow = tracks[:NARROW_ROWS]

    out = fluid_open(HEIGHT, "Debug Soundtrack")
    out.insert(4, f'<clipPath id="artw"><rect width="{WIDE_ART}" height="{WIDE_ART}" rx="6"/></clipPath>'
                  f'<clipPath id="artn"><rect width="{NARROW_ART}" height="{NARROW_ART}" rx="6"/></clipPath>')

    for cls, label, pad in (("w", f"{len(wide)} tracks", PAD),
                            ("n", f"{len(narrow)} of {len(tracks)}", NARROW_PAD)):
        head = f"{truncate(name, 13, 200)} \u00b7 {label} \u00b7 refreshed daily"
        out.append(f'<g class="{cls}">')
        out.append(f'<text x="{pad}" y="30" fill="{MUTED}" font-size="13">{esc(head)}</text>')
        out.append(right(pad, f'<text x="100%" y="30" fill="{DIM}" font-size="12.5" '
                              f'text-anchor="end">YouTube Music</text>'))
        out.append("</g>")

    out.append('<g class="w">')
    out += rows(wide, 2, WIDE_ROWS, WIDE_ROW_H, WIDE_ART, PAD, WIDE_REF * 2, "artw")
    out.append("</g>")
    out.append('<g class="n">')
    out += rows(narrow, 1, NARROW_ROWS, NARROW_ROW_H, NARROW_ART, NARROW_PAD, NARROW_REF, "artn")
    out.append("</g>")

    out += card_close()
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
