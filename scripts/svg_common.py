#!/usr/bin/env python3
"""Shared drawing helpers for the README panels.

Every panel in this repo is rendered here and committed as a static file, so
the profile never depends on a third-party card service being up.

Panels are *fluid*: `width="100%"` with a fixed pixel height, and no
viewBox. An SVG referenced through <img> keeps its own viewport, so the
width attribute resolves against the README column and the height stays
put, which means the type inside renders at its true pixel size on every
device instead of being scaled down with the box. Media queries inside the
file test that rendered width, so each panel can lay itself out differently
on a phone, a tablet and a desktop. GitHub ignores width media queries on
<picture><source>, so this is the only responsive lever a README has.

The one thing this cannot do is change a panel's height per breakpoint: the
height attribute fixes the intrinsic size (verified - a media query that
sets svg{height} is ignored by the image sizing). So every layout variant
of a panel has to fit the same box, and the height is chosen for the
tallest variant, which is normally the stacked phone one.
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


def mono_width(s, size):
    """Monospace advance is a flat 0.6em, so the estimate is exact.

    text_width models proportional sans and runs ~24% narrow on a mono
    string, which is enough to clip a reveal animation.
    """
    return len(s) * 0.6 * size


def truncate(s, size, max_px):
    if text_width(s, size) <= max_px:
        return s
    ell = "…"
    while s and text_width(s + ell, size) > max_px:
        s = s[:-1]
    return s.rstrip() + ell


def esc(s):
    return html.escape(str(s))


def card_close():
    return ["</g></svg>"]


# Rendered width, in CSS pixels, below which panels switch to their stacked
# layout. GitHub's README column is about 860px at desktop, roughly 700px on
# a tablet once the profile sidebar appears, and the viewport width minus
# padding on a phone.
NARROW_MAX = 560

# The light palette, keyed by the dark colour it replaces. GitHub's own
# light canvas is white, so panels sit on #f6f8fa with the same hairlines
# rather than disappearing into the page.
#
# Applied as attribute selectors rather than by changing how the panels are
# drawn: a presentation attribute loses to any author rule, so one block of
# CSS repaints a whole panel without touching a single drawing call. This
# follows the viewer's browser or system colour scheme, which is not the
# same thing as GitHub's own theme toggle - someone reading light GitHub on
# a dark desktop still gets the dark panels.
LIGHT = {
    BG: "#f6f8fa",
    TITLE: "#1f2328",
    MUTED: "#59636e",
    DIM: "#6e7781",
    ACCENT: "#0969da",
    ACCENT_ALT: "#8250df",
    # Only ever drawn at a low opacity, as a tint or a hairline, so it
    # inverts with the background.
    ROW: "#1f2328",
}


def light_css():
    rules = "".join(
        f'[fill="{dark}"]{{fill:{light}}}'
        f'[stroke="{dark}"]{{stroke:{light}}}'
        f'[stop-color="{dark}"]{{stop-color:{light}}}'
        for dark, light in LIGHT.items())
    return f"@media(prefers-color-scheme:light){{{rules}}}"

# Text is wrapped at build time, so a fluid panel has to be wrapped once per
# layout variant. These are the narrowest column each variant has to survive:
# a 360px phone and a panel just above the breakpoint.
NARROW_REF = 320
WIDE_REF = 520


def fluid_open(height, label, radius=12, css=""):
    """Panel chrome for a fluid card: 100% wide, fixed height, no viewBox.

    `.w` elements show only above NARROW_MAX and `.n` only below it, so a
    panel carries both layouts and the renderer picks one.
    """
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
        f'role="img" aria-label="{esc(label)}">',
        "<style>"
        ".n{display:none}"
        f"@media(max-width:{NARROW_MAX}px){{.w{{display:none}}.n{{display:inline}}}}"
        f"{light_css()}"
        f"{css}"
        "</style>",
        "<defs>",
        '<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT_ALT}"/>'
        "</linearGradient>",
        "</defs>",
        f'<rect width="100%" height="{height}" rx="{radius}" fill="{BG}"/>',
        f'<rect width="100%" height="3" rx="1.5" fill="url(#accent)" opacity="0.85"/>',
        f'<g font-family="{FONT}">',
    ]


def right(offset, body):
    """Anchor `body` (which uses x="100%") `offset` px in from the right edge.

    A percentage resolves against the viewport and SVG has no calc(), so the
    offset has to come from a transform on the way out.
    """
    return f'<g transform="translate({-offset},0)">{body}</g>'


def column(x_pct, w_pct, height, body, y=0):
    """A nested viewport, so percentages inside are percentages of the column."""
    return ([f'<svg x="{x_pct}%" y="{y}" width="{w_pct}%" height="{height}">'] +
            list(body) + ["</svg>"])


def wrap(text, size, max_px, max_lines):
    """Greedy wrap to a pixel budget, with a trailing ellipsis when cut."""
    words, line, lines = text.split(), "", []
    clipped = False
    for word in words:
        trial = f"{line} {word}".strip()
        if text_width(trial, size) > max_px:
            if line:
                lines.append(line)
            line = word
            if len(lines) == max_lines:
                clipped = True
                break
        else:
            line = trial
    if line and len(lines) < max_lines:
        lines.append(line)
    elif line:
        clipped = True
    if clipped and lines:
        lines[-1] = truncate(lines[-1] + " \u2026", size, max_px)
    return lines


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


def bytes_human(n):
    """3047025 -> 3.05 MB. Source bytes, as GitHub's language API counts them.

    Decimal units rather than binary: the figure sits beside counts a reader
    scans in passing, and 3.05 MB is the number they would expect from
    3,047,025 bytes. KB is the smallest unit shown, because a profile with
    less than a kilobyte of code has nothing to report.
    """
    n = int(n)
    for unit, step in (("GB", 1_000_000_000), ("MB", 1_000_000), ("KB", 1000)):
        if n >= step:
            return f"{n / step:.2f}".rstrip("0").rstrip(".") + f" {unit}"
    return f"{n} B"
