#!/usr/bin/env python3
"""Render the tech stack as one grid of icon tiles.

Replaces four rows of labelled img.shields.io badges, which were the last
part of the README fetched from someone else's server at page-load time.
Icon paths come from simple-icons at build time and are inlined, so the
finished panel is a single self-contained file.

Exits 0 without touching the output when the icons cannot be fetched, so a
CDN hiccup leaves the previous panel in place.
"""

import os
import re
import sys
import urllib.error

from svg_common import BG, DIM, FONT, MONO, MUTED, ROW, TITLE, card_close, card_open, esc, fetch, write

OUT = os.environ.get("OUT_PATH", "metrics/tools.svg")
CDN = "https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{}.svg"

W, PAD = 860, 20
COLS, TILE, GAP = 12, 52, 17.8
ICON = 24

# (label, simple-icons slug or None, brand colour). Order groups the stack:
# languages and stores, then modelling, then streaming and platform.
TOOLS = [
    ("Python", "python", "#3776AB"),
    ("R", "r", "#276DC3"),
    ("PostgreSQL", "postgresql", "#4479A1"),
    ("DuckDB", "duckdb", "#FFF000"),
    ("Oracle", "oracle", "#F80000"),
    ("MongoDB", "mongodb", "#47A248"),
    ("Elasticsearch", "elasticsearch", "#005571"),
    ("pandas", "pandas", "#150458"),
    ("NumPy", "numpy", "#013243"),
    ("scikit-learn", "scikitlearn", "#F7931E"),
    ("PyTorch", "pytorch", "#EE4C2C"),
    ("TensorFlow", "tensorflow", "#FF6F00"),
    ("Apache Kafka", "apachekafka", "#231F20"),
    ("Apache Flink", "apacheflink", "#E6526F"),
    ("Apache Spark", "apachespark", "#E25A1C"),
    ("SAP S/4HANA", "sap", "#0FAAFF"),
    # simple-icons carries no Power BI or XGBoost mark, so these fall back to
    # a monogram tile rather than being dropped from the stack.
    ("Power BI", None, "#F2C811"),
    ("Tableau", "tableau", "#E97627"),
    ("XGBoost", None, "#FF6600"),
    ("LangChain", "langchain", "#1C3C3C"),
    ("Docker", "docker", "#2496ED"),
    ("Jupyter", "jupyter", "#F37626"),
    ("Git", "git", "#F05032"),
    ("Linux", "linux", "#FCC624"),
]

MONOGRAM = {"Power BI": "BI", "XGBoost": "XGB"}


def luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable(hex_colour, floor=0.33):
    """Lift a mark that would disappear against the dark card.

    Several brand colours are near-black (pandas #150458, Kafka #231F20),
    which is invisible here. Blend toward white until it clears the floor
    rather than dropping the brand colour entirely.
    """
    lum = luminance(hex_colour)
    if lum >= floor:
        return hex_colour
    mix = min(1.0, (floor - lum) / max(1 - lum, 1e-6) + 0.15)
    parts = []
    for i in (1, 3, 5):
        channel = int(hex_colour[i:i + 2], 16)
        parts.append(round(channel + (255 - channel) * mix))
    return "#%02x%02x%02x" % tuple(parts)


def icon_path(slug):
    raw = fetch(CDN.format(slug), timeout=20).decode("utf-8", "replace")
    match = re.search(r'<path\s+d="([^"]+)"', raw)
    if not match:
        raise RuntimeError(f"no path in {slug}.svg")
    return match.group(1)


def build(paths):
    rows = -(-len(TOOLS) // COLS)
    height = PAD + rows * TILE + (rows - 1) * 14 + PAD + 8
    span = COLS * TILE + (COLS - 1) * GAP
    left = (W - span) / 2

    out = card_open(W, height, "Tech stack: " + ", ".join(t[0] for t in TOOLS))
    for i, (label, slug, colour) in enumerate(TOOLS):
        col, row = i % COLS, i // COLS
        x = left + col * (TILE + GAP)
        y = PAD + row * (TILE + 14)
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{TILE}" height="{TILE}" rx="12" '
                   f'fill="{ROW}" fill-opacity="0.05" stroke="{ROW}" stroke-opacity="0.07"/>')
        out.append(f"<title>{esc(label)}</title>")
        tint = readable(colour)
        path = paths.get(slug)
        if path:
            scale = ICON / 24
            ox = x + (TILE - ICON) / 2
            oy = y + (TILE - ICON) / 2
            out.append(f'<g transform="translate({ox:.1f},{oy:.1f}) scale({scale:.4f})" '
                       f'fill="{tint}"><path d="{path}"/></g>')
        else:
            out.append(f'<text x="{x + TILE / 2:.1f}" y="{y + TILE / 2 + 5:.1f}" fill="{tint}" '
                       f'font-size="14" font-weight="700" text-anchor="middle" '
                       f'font-family="{MONO}">{esc(MONOGRAM.get(label, label[:3]))}</text>')
    out += card_close()
    return "\n".join(out)


def main():
    paths = {}
    for label, slug, _ in TOOLS:
        if not slug:
            continue
        try:
            paths[slug] = icon_path(slug)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
            print(f"::warning::icon {slug} unavailable ({exc})")
    if not paths:
        print("::warning::no icons could be fetched; keeping existing panel")
        return 0
    write(OUT, build(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
