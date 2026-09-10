#!/usr/bin/env python3
"""Render the WakaTime week as a panel, from the API.

Replaces anmol098/waka-readme-stats, which wrote a fenced code block into
the README. That block was the last fixed-width thing on the page: its
rows are about 76 characters wide, so anything narrower than ~610px
scrolled sideways. It also carried an img.shields.io badge, which was a
page-load call to another server for a number that never changes between
builds.

Only time by language is drawn. The editor split is deliberately not:
it is almost entirely AI tooling, which is not what the panel is for.

Exits 0 without touching the output when the API call fails, so a hiccup
leaves yesterday's panel in place.
"""

import base64
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

from svg_common import (ACCENT, MONO, MUTED, NARROW_REF, ROW, TITLE, card_close,
                        column, esc, fluid_open, right, truncate, write)

KEY = os.environ.get("WAKATIME_API_KEY", "")
OUTDIR = os.environ.get("OUT_DIR", "metrics")
README = os.environ.get("README_PATH", "README.md")
API = "https://wakatime.com/api/v1/users/current"
# A saved response, for rendering without network access.
SAMPLE = os.environ.get("WAKA_JSON", "")

HEIGHT = 254            # the stats panel's height, so the pair reads as a pair
PAD, NARROW_PAD = 20, 14
WIDE_LANGS, NARROW_LANGS = 5, 3


def fetch(path):
    token = base64.b64encode(KEY.encode()).decode()
    req = urllib.request.Request(f"{API}/{path}", headers={
        "Authorization": f"Basic {token}",
        "User-Agent": "O-2wice-profile-panels",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["data"]


def short(text):
    """'9 hrs 42 mins' -> '9h 42m'. The long form does not fit a quarter of
    a narrow column at a size worth reading."""
    hours = re.search(r"(\d+)\s*hr", text or "")
    mins = re.search(r"(\d+)\s*min", text or "")
    parts = []
    if hours:
        parts.append(f"{hours.group(1)}h")
    if mins and not (hours and int(hours.group(1)) >= 100):
        parts.append(f"{mins.group(1)}m")
    return " ".join(parts) or "0m"


def figures(cells, pad, label_size, value_size, rows):
    out = [f'<g transform="translate({pad},0)">']
    for i, (label, value) in enumerate(cells):
        col, row = i % 2, i // 2
        label_y, value_y = rows[row]
        out.append(f'<text x="{col * 50}%" y="{label_y}" fill="{MUTED}" '
                   f'font-size="{label_size}">{esc(label)}</text>')
        out.append(f'<text x="{col * 50}%" y="{value_y}" fill="{TITLE}" '
                   f'font-size="{value_size}" font-weight="600" '
                   f'font-family="{MONO}">{esc(value)}</text>')
    out.append("</g>")
    return out


def languages(langs, pad, label_y, first_y, step, count, uid):
    """A row per language: name, time, and a bar of its share of the week."""
    out = [f'<text x="{pad}" y="{label_y}" fill="{MUTED}" font-size="13.5">'
           f'Time by language</text>']
    top = langs[:count]
    widest = max((l["percent"] for l in top), default=1) or 1
    for i, lang in enumerate(top):
        y = first_y + i * step
        out.append(f'<text x="{pad}" y="{y}" fill="{TITLE}" font-size="13">'
                   f'{esc(truncate(lang["name"], 13, 130))}</text>')
        out.append(right(pad, f'<text x="100%" y="{y}" fill="{MUTED}" font-size="12" '
                              f'text-anchor="end" font-family="{MONO}">'
                              f'{esc(short(lang["text"]))}</text>'))
        # The bar is scaled against the largest share rather than 100%, so a
        # week split five ways still shows a readable difference.
        out.append(f'<svg x="{pad}" y="{y + 6}" height="5" '
                   f'style="width:calc(100% - {pad * 2}px)">'
                   f'<rect x="0" y="0" width="100%" height="5" rx="2.5" '
                   f'fill="{ROW}" fill-opacity="0.07"/>'
                   f'<rect x="0" y="0" width="{lang["percent"] / widest * 100:.2f}%" '
                   f'height="5" rx="2.5" fill="{ACCENT}" fill-opacity="0.85"/>'
                   f"</svg>")
    return out


def build(week, all_time):
    cells = [("This week", short(week.get("human_readable_total"))),
             ("Daily average", short(week.get("human_readable_daily_average"))),
             ("Best day", short((week.get("best_day") or {}).get("text", ""))),
             ("Tracked in total", short(all_time))]
    langs = [l for l in week.get("languages", []) if l.get("percent")]

    out = fluid_open(HEIGHT, "Coding time this week, by language")

    out.append('<g class="w">')
    out += column(0, 50, HEIGHT, figures(cells, PAD, 14, 26, [(76, 112), (162, 198)]))
    out.append(f'<line x1="50%" y1="30" x2="50%" y2="{HEIGHT - 30}" '
               f'stroke="{ROW}" stroke-opacity="0.08"/>')
    out += column(50, 50, HEIGHT,
                  languages(langs, PAD, 68, 100, 30, WIDE_LANGS, "w"))
    out.append("</g>")

    out.append('<g class="n">')
    out += figures(cells, NARROW_PAD, 12.5, 22, [(40, 70), (104, 134)])
    # 190 + two 25px steps puts the last bar at 251 of the 254 available.
    out += languages(langs, NARROW_PAD, 166, 190, 25, NARROW_LANGS, "n")
    out.append("</g>")

    out += card_close()
    return "\n".join(out)


def main():
    if not KEY and not SAMPLE:
        print("::error::WAKATIME_API_KEY is empty; cannot query WakaTime")
        return 1
    try:
        if SAMPLE:
            saved = json.loads(pathlib.Path(SAMPLE).read_text())
            week, all_time = saved["week"], saved["all_time"]
        else:
            week = fetch("stats/last_7_days")
            all_time = fetch("all_time_since_today").get("text", "")
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
            ValueError) as exc:
        print(f"::warning::WakaTime call failed ({exc}); keeping the existing panel")
        return 0

    write(f"{OUTDIR}/waka.svg", build(week, all_time))

    readme = pathlib.Path(README)
    if readme.exists():
        text = readme.read_text()
        block = ("<!--START_SECTION:waka-->\n"
                 f'<img src="{OUTDIR}/waka.svg" width="100%" '
                 'alt="Coding time this week, by language"/>\n'
                 "<!--END_SECTION:waka-->")
        updated = re.sub(r"<!--START_SECTION:waka-->.*?<!--END_SECTION:waka-->",
                         lambda _m: block, text, flags=re.S)
        if updated != text:
            readme.write_text(updated)
            print("updated the waka block in README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
