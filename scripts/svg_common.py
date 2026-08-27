#!/usr/bin/env python3
"""Shared drawing helpers for the README panels.

Every panel in this repo is rendered here and committed as a static file, so
the profile never depends on a third-party card service being up.
"""

import html
import os
import urllib.error
import urllib.request

# tokyonight, to match the other README panels
BG = "#1a1b27"
ACCENT = "#70a5fd"
ACCENT_ALT = "#bb9af7"
TITLE = "#c0caf5"
MUTED = "#7f88a8"
DIM = "#565f89"
ROW = "#ffffff"

FONT = "'Segoe UI',Ubuntu,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Consolas,monospace"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Rough per-character advance ratios for proportional sans at 1px, used to
# truncate text (SVG has no ellipsis).
NARROW = set("ijltfrI.,:;'!|()[]{}-/\\ ")
WIDE = set("mwMW@")


def fetch(url, timeout=30, headers=None):
    hdrs = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, headers=hdrs)
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


def esc(s):
    return html.escape(str(s))


def card_open(width, height, label, radius=12):
    """Panel chrome shared by every card: rounded body and gradient top rule."""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">',
        "<defs>",
        '<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT_ALT}"/>'
        "</linearGradient>",
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="{radius}" fill="{BG}"/>',
        f'<rect width="{width}" height="3" rx="1.5" fill="url(#accent)" opacity="0.85"/>',
        f'<g font-family="{FONT}">',
    ]


def card_close():
    return ["</g></svg>"]


def heading(x, y, text, size=15.5):
    return (f'<text x="{x}" y="{y}" fill="{ACCENT}" font-size="{size}" '
            f'font-weight="600">{esc(text)}</text>')


def write(path, svg):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {path} ({len(svg)} bytes)")


def human(n):
    """1234 -> 1.2k, matching the compact counts on GitHub's own UI."""
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
