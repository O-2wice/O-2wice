#!/usr/bin/env python3
"""Render the Daily Drivers table as one clickable SVG row per fork.

This was a markdown table. On the web it reflowed fine, because GitHub's
stylesheet gives tables `width: max-content; max-width: 100%`. The mobile
app renders the markdown itself and lays a two-column table out its own
way, which squeezed it on a tablet. A README cannot fix that: the borders
and the column widths both come from the renderer, and GitHub strips the
`style` attribute that would override them (verified against its markdown
API - `style="border:none"` comes back deleted).

Drawing the rows is the only way to get a table that looks the same
everywhere. Each row is its own file so it can sit in its own anchor: a
link inside an SVG does nothing when the SVG is loaded through an <img>.
Rows are fluid, like every other panel here, and stack the description
under the name below the breakpoint.

Exits 0 without touching the outputs when the API call fails, so a hiccup
leaves yesterday's rows in place.
"""

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

from svg_common import (ACCENT, FONT, MUTED, NARROW_MAX, NARROW_REF, ROW,
                        esc, light_css, truncate, write)

LOGIN = os.environ.get("GH_LOGIN", "O-2wice")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_DIR = os.environ.get("OUT_DIR", "metrics/drivers")
README = os.environ.get("README_PATH", "README.md")
LIMIT = int(os.environ.get("DRIVER_LIMIT", "6"))
# A saved API response, for rendering without network access.
SAMPLE = os.environ.get("DRIVERS_JSON", "")

# Text is truncated at build time against a fixed budget, so one wide
# variant would have to be cut for the narrowest column in its band and
# would then look needlessly clipped on everything wider. Four bands keep
# the cut close to the width it is actually rendered at. Each band is
# wrapped for its own lower bound, which is the only width in it that is
# guaranteed to fit.
#   (class, min width, max width or None)
BANDS = [("n", None, NARROW_MAX),
         ("w", NARROW_MAX + 1, 699),
         ("x", 700, 839),
         ("xl", 840, None)]
# Text budget per two-column band: the band's lower bound, less the name
# column and the right padding.
BUDGETS = {"w": NARROW_MAX + 1, "x": 700, "xl": 840}

ROW_H = 46
HEAD_H = 26
PAD, NARROW_PAD = 20, 14
# Where the description starts on a wide row. The longest fork name here is
# 17 characters, which is about 120px at this weight.
NAME_COL = 200


def repos():
    if SAMPLE:
        return json.loads(pathlib.Path(SAMPLE).read_text())
    url = (f"https://api.github.com/users/{LOGIN}/repos"
           "?type=owner&sort=pushed&per_page=100")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": f"{LOGIN}-profile-panels"}
    if TOKEN:
        headers["Authorization"] = f"bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def band_css():
    """Every band is off by default and exactly one query switches it on, so
    the result never depends on rule order."""
    rules = [",".join(f".{cls}" for cls, _, _ in BANDS) + "{display:none}"]
    for cls, lo, hi in BANDS:
        query = " and ".join(
            part for part in (f"(min-width:{lo}px)" if lo else "",
                              f"(max-width:{hi}px)" if hi else "") if part)
        rules.append(f"@media {query}{{.{cls}{{display:inline}}}}")
    return "".join(rules)


def open_svg(height, label):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
            f'role="img" aria-label="{esc(label)}">',
            f"<style>{band_css()}{light_css()}</style>"]


def header_row():
    """Column labels and a hairline. No labels below the breakpoint, where
    the description sits under the name and the columns no longer exist."""
    out = open_svg(HEAD_H, "Tool, what it does")
    out.append(f'<g font-family="{FONT}" font-size="11.5" fill="{MUTED}" '
               f'letter-spacing="0.4">')
    for cls in BUDGETS:
        out.append(f'<g class="{cls}"><text x="{PAD}" y="14">TOOL</text>'
                   f'<text x="{NAME_COL}" y="14">WHAT IT DOES</text></g>')
    # Nothing below the breakpoint: the rows stack there, so a column label
    # would be labelling a column that is no longer there.
    out.append("</g>")
    out.append(f'<rect x="0" y="{HEAD_H - 1}" width="100%" height="1" '
               f'fill="{ROW}" fill-opacity="0.10"/>')
    out.append("</svg>")
    return "\n".join(out)


def driver_row(name, description, index):
    out = open_svg(ROW_H, f"{name}: {description}")
    if index % 2 == 0:
        out.append(f'<rect x="0" y="0" width="100%" height="{ROW_H}" rx="6" '
                   f'fill="{ROW}" fill-opacity="0.03"/>')
    out.append(f'<g font-family="{FONT}">')

    # Wide: two columns, the way the table read.
    for cls, budget in BUDGETS.items():
        out.append(f'<g class="{cls}">')
        out.append(f'<text x="{PAD}" y="{ROW_H / 2 + 4.5}" fill="{ACCENT}" font-size="13.5" '
                   f'font-weight="600">'
                   f'{esc(truncate(name, 13.5, NAME_COL - PAD - 14))}</text>')
        out.append(f'<text x="{NAME_COL}" y="{ROW_H / 2 + 4.5}" fill="{MUTED}" '
                   f'font-size="12.5">'
                   f'{esc(truncate(description, 12.5, budget - NAME_COL - PAD))}</text>')
        out.append("</g>")

    # Narrow: the description drops under the name.
    out.append('<g class="n">')
    out.append(f'<text x="{NARROW_PAD}" y="19" fill="{ACCENT}" font-size="13" '
               f'font-weight="600">{esc(name)}</text>')
    out.append(f'<text x="{NARROW_PAD}" y="36" fill="{MUTED}" font-size="11.5">'
               f'{esc(truncate(description, 11.5, NARROW_REF - NARROW_PAD * 2))}</text>')
    out.append("</g>")

    out.append("</g></svg>")
    return "\n".join(out)


def markup(rows):
    # The header gets an anchor of its own because GitHub wraps a bare image
    # in a link to the file itself, and a click there would land on a raw
    # SVG sitting directly above rows that link to repositories.
    forks = f"https://github.com/{LOGIN}?tab=repositories&type=fork"
    lines = [f'<a href="{forks}" title="All forks">'
             f'<img src="{OUT_DIR}/_head.svg" width="100%" alt="Tool, what it does"/></a>']
    lines += [f'<a href="{url}" title="{esc(name)}">'
              f'<img src="{OUT_DIR}/{name}.svg" width="100%" '
              f'alt="{esc(name)}: {esc(desc)}"/></a>'
              for name, desc, url in rows]
    return "\n".join(lines)


def main():
    try:
        data = repos()
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        print(f"::warning::could not list repositories ({exc}); keeping existing rows")
        return 0

    rows = [(r["name"], r.get("description") or "no description", r["html_url"])
            for r in data if r.get("fork") and not r.get("archived")][:LIMIT]
    if not rows:
        print("::warning::no forks came back; keeping existing rows")
        return 0

    for stale in pathlib.Path(OUT_DIR).glob("*.svg") if pathlib.Path(OUT_DIR).exists() else []:
        stale.unlink()
    write(f"{OUT_DIR}/_head.svg", header_row())
    for i, (name, desc, _) in enumerate(rows):
        write(f"{OUT_DIR}/{name}.svg", driver_row(name, desc, i))

    readme = pathlib.Path(README)
    if readme.exists():
        text = readme.read_text()
        block = (f"<!--START_SECTION:drivers-->\n{markup(rows)}\n"
                 f"<!--END_SECTION:drivers-->")
        updated = re.sub(r"<!--START_SECTION:drivers-->.*?<!--END_SECTION:drivers-->",
                         lambda _m: block, text, flags=re.S)
        if updated != text:
            readme.write_text(updated)
            print("updated the drivers block in README.md")
    print(f"{len(rows)} driver row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
