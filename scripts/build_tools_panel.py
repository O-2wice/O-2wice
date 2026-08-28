#!/usr/bin/env python3
"""Render the tech stack as one small icon tile per tool.

Replaces four rows of labelled img.shields.io badges, which were the last
part of the README fetched from someone else's server at page-load time.
Icon paths come from simple-icons at build time and are inlined, so each
tile is self-contained.

One file per tool rather than a single grid, because a link inside an SVG
does nothing when the SVG is loaded through an <img>, and GitHub strips
inline SVG from markdown. Separate tiles let each one sit in its own
anchor, so the stack is clickable.

Exits 0 without touching the output when the icons cannot be fetched, so a
CDN hiccup leaves the previous panel in place.
"""

import os
import re
import sys
import urllib.error

from svg_common import BG, DIM, FONT, MONO, MUTED, ROW, TITLE, card_close, card_open, esc, fetch, write

OUT_DIR = os.environ.get("OUT_DIR", "metrics/tools")
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

# Languages GitHub can filter his repositories by are worth far more than a
# vendor home page: the click shows what he actually built with the thing.
LANGUAGES = {"Python": "Python", "R": "R", "Jupyter": "Jupyter Notebook"}

HOMES = {
    "PostgreSQL": "https://www.postgresql.org/", "DuckDB": "https://duckdb.org/",
    "Oracle": "https://www.oracle.com/database/", "MongoDB": "https://www.mongodb.com/",
    "Elasticsearch": "https://www.elastic.co/elasticsearch",
    "pandas": "https://pandas.pydata.org/", "NumPy": "https://numpy.org/",
    "scikit-learn": "https://scikit-learn.org/", "PyTorch": "https://pytorch.org/",
    "TensorFlow": "https://www.tensorflow.org/",
    "Apache Kafka": "https://kafka.apache.org/", "Apache Flink": "https://flink.apache.org/",
    "Apache Spark": "https://spark.apache.org/",
    "SAP S/4HANA": "https://www.sap.com/products/erp/s4hana.html",
    "Power BI": "https://www.microsoft.com/power-platform/products/power-bi",
    "Tableau": "https://www.tableau.com/", "XGBoost": "https://xgboost.readthedocs.io/",
    "LangChain": "https://www.langchain.com/", "Docker": "https://www.docker.com/",
    "Git": "https://git-scm.com/", "Linux": "https://www.kernel.org/",
}


def slugify(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def link_for(label):
    if label in LANGUAGES:
        return ("https://github.com/O-2wice?tab=repositories&language="
                + LANGUAGES[label].lower().replace(" ", "+"))
    return HOMES.get(label, "https://github.com/O-2wice")


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


def build_tile(label, slug, colour, paths):
    tint = readable(colour)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{TILE}" height="{TILE}" '
           f'viewBox="0 0 {TILE} {TILE}" role="img" aria-label="{esc(label)}">',
           f'<title>{esc(label)}</title>',
           f'<rect width="{TILE}" height="{TILE}" rx="12" fill="{BG}"/>',
           f'<rect width="{TILE}" height="{TILE}" rx="12" fill="{ROW}" fill-opacity="0.05" '
           f'stroke="{ROW}" stroke-opacity="0.07"/>']
    path = paths.get(slug)
    if path:
        offset = (TILE - ICON) / 2
        out.append(f'<g transform="translate({offset:.1f},{offset:.1f}) '
                   f'scale({ICON / 24:.4f})" fill="{tint}"><path d="{path}"/></g>')
    else:
        out.append(f'<text x="{TILE / 2}" y="{TILE / 2 + 5}" fill="{tint}" font-size="14" '
                   f'font-weight="700" text-anchor="middle" font-family="{MONO}">'
                   f'{esc(MONOGRAM.get(label, label[:3]))}</text>')
    out.append("</svg>")
    return "\n".join(out)


def markdown(per_row=COLS):
    """The anchor rows to paste into the README, printed for reference.

    Broken into explicit rows: left to wrap on its own the run reflows to a
    ragged 13 and 11 against GitHub's column.
    """
    tags = [f'<a href="{link_for(label)}" title="{label}">'
            f'<img src="metrics/tools/{slugify(label)}.svg" width="46" alt="{label}"/></a>'
            for label, _, _ in TOOLS]
    rows = [" ".join(tags[i:i + per_row]) for i in range(0, len(tags), per_row)]
    return "\n<br/>\n".join(rows)


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
        print("::warning::no icons could be fetched; keeping existing tiles")
        return 0
    for label, slug, colour in TOOLS:
        write(f"{OUT_DIR}/{slugify(label)}.svg", build_tile(label, slug, colour, paths))
    if os.environ.get("PRINT_MARKDOWN"):
        print(markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
