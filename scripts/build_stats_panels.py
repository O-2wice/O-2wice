#!/usr/bin/env python3
"""Render the GitHub stats panels from the API into committed SVGs.

Replaces four card services the README used to call at page-load time
(github-readme-stats, streak-stats.demolab.com,
github-readme-activity-graph, and the pinned-repo cards). Those are
third-party servers: when one is rate limited or shut down the profile shows
broken images, which is what happened to the activity graph.

Everything here is drawn from the GitHub API and written to metrics/, so the
panels are served by GitHub's own CDN and cannot break at page-load time.

Exits 0 without touching the outputs when the API call fails, so an API
hiccup leaves yesterday's panels in place instead of breaking the profile.
"""

import collections
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

from svg_common import (ACCENT, ACCENT_ALT, DIM, MONO, MUTED, NARROW_REF, ROW, TITLE,
                        WIDE_REF, card_close, column, esc, fluid_open, human, right,
                        truncate, wrap, write)

LOGIN = os.environ.get("GH_LOGIN", "O-2wice")
TOKEN = os.environ.get("GH_TOKEN", "")
OUTDIR = os.environ.get("OUT_DIR", "metrics")
PINS = [r.strip() for r in os.environ.get("PIN_REPOS", "").split(",") if r.strip()]
README = os.environ.get("README_PATH", "README.md")
# Notebook files carry their rendered outputs inline, so byte counts make
# Jupyter dwarf everything else and say nothing about what he actually writes.
EXCLUDE_LANGS = {s.strip().lower() for s in
                 os.environ.get("EXCLUDE_LANGS", "Jupyter Notebook").split(",") if s.strip()}

API = "https://api.github.com/graphql"


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": f"{LOGIN}-profile-panels",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"][0].get("message", "GraphQL error"))
    return payload["data"]


def pages_url(repo):
    """The published GitHub Pages URL for a repo, or None.

    Detected rather than configured so a write-up added later is picked up
    without editing the workflow.
    """
    try:
        return rest(f"repos/{LOGIN}/{repo}/pages").get("html_url")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def rest(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={
        "Authorization": f"bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{LOGIN}-profile-panels",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


PROFILE_Q = """
query($login: String!) {
  user(login: $login) {
    name login createdAt
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
    publicRepos: repositories(first: 1, ownerAffiliations: OWNER,
                              isFork: false, privacy: PUBLIC) {
      totalCount
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        name stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

CALENDAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

PUBLIC_Q = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { name }
    }
  }
}
"""

REPO_Q = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    name description stargazerCount forkCount
    primaryLanguage { name color }
  }
}
"""


def calendar_days(created):
    """Every contribution day since signup. The API caps a query at one year."""
    days = {}
    year = created.year
    today = dt.datetime.now(dt.timezone.utc)
    while year <= today.year:
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(today, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        data = graphql(CALENDAR_Q, login=LOGIN,
                       **{"from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
        cal = data["user"]["contributionsCollection"]["contributionCalendar"]
        for week in cal["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
        year += 1
    return dict(sorted(days.items()))


# Panels are fluid now: full width, fixed height, laid out by media queries
# inside the file (see svg_common). Nothing is measured against GitHub's
# column any more, because the column is no longer assumed.
PAD = 20
NARROW_PAD = 14


def figure_cells(user, all_commits, total_contribs, active_days, stars):
    """The figures that say something about the work.

    No card title and no @handle: the README section heading already says
    "GitHub Stats", and the handle is on every other part of the page. No
    follower count either: it measures the audience, not the work.
    """
    year = dt.datetime.now(dt.timezone.utc).year
    cells = [("Total commits", human(all_commits)),
             (f"Contributions in {year}", human(total_contribs)),
             (f"Active days in {year}", human(active_days)),
             ("Public repositories", human(user["publicRepos"]["totalCount"]))]
    # Stars displace the repository count rather than adding a fifth
    # figure: GitHub already prints the repository count on the profile
    # itself, and a row of zeros reads worse than no row at all.
    if stars:
        cells[3] = ("Stars earned", human(stars))
    return cells


def figures(cells, pad, label_size, value_size, rows, cols=2):
    """Figures on a grid filling whatever viewport encloses them.

    Three of them stack down one column rather than leaving a hole in a
    2x2; a fourth, when there are stars to show, pairs them up again.
    """
    out = [f'<g transform="translate({pad},0)">']
    for i, (label, value) in enumerate(cells):
        col, row = (i % cols, i // cols) if cols > 1 else (0, i)
        label_y, value_y = rows[row]
        out.append(f'<text x="{col * (100 // cols)}%" y="{label_y}" fill="{MUTED}" '
                   f'font-size="{label_size}">{esc(label)}</text>')
        out.append(f'<text x="{col * (100 // cols)}%" y="{value_y}" fill="{TITLE}" '
                   f'font-size="{value_size}" font-weight="600" '
                   f'font-family="{MONO}">{esc(value)}</text>')
    out.append("</g>")
    return out


def language_bar(top, total, colours, pad, label_y, bar_y, uid):
    """The stacked share bar.

    Drawn inside a nested viewport inset by the padding, so each segment can
    be placed as a plain percentage of the bar. `width` is the one geometry
    property that has to come through CSS: SVG has no calc() in attributes.
    """
    out = [f'<text x="{pad}" y="{label_y}" fill="{MUTED}" font-size="13.5">'
           f'Most used languages</text>',
           f'<svg x="{pad}" y="{bar_y}" height="10" '
           f'style="width:calc(100% - {pad * 2}px)">',
           f'<clipPath id="{uid}"><rect x="0" y="0" width="100%" height="10" rx="5"/></clipPath>',
           f'<g clip-path="url(#{uid})">',
           f'<rect x="0" y="0" width="100%" height="10" fill="{ROW}" fill-opacity="0.08"/>']
    at = 0.0
    for name, size in top:
        share = size / total
        out.append(f'<rect x="{at * 100:.3f}%" y="0" width="{share * 100 + 0.3:.3f}%" '
                   f'height="10" fill="{colours.get(name) or ACCENT}"/>')
        at += share
    out.append("</g></svg>")
    return out


def legend(top, total, colours, pad, rows_y, cols, size=13.5):
    """Language names down `cols` columns, each with its share right-aligned."""
    out = []
    per_col = -(-len(top) // cols)
    col_w = 100 / cols
    for i, (name, count) in enumerate(top):
        col, row = divmod(i, per_col)
        if row >= len(rows_y):
            continue
        y = rows_y[row]
        out.append(f'<svg x="{col * col_w}%" y="0" width="{col_w}%" height="100%">')
        out.append(f'<circle cx="{pad + 5}" cy="{y - 4}" r="5" '
                   f'fill="{colours.get(name) or ACCENT}"/>')
        out.append(f'<text x="{pad + 17}" y="{y}" fill="{TITLE}" font-size="{size}">'
                   f'{esc(truncate(name, size, 110))}</text>')
        out.append(right(pad, f'<text x="100%" y="{y}" fill="{MUTED}" font-size="{size - 0.5}" '
                              f'text-anchor="end" font-family="{MONO}">'
                              f'{100 * count / total:.1f}%</text>'))
        out.append("</svg>")
    return out


def build_overview(user, all_commits, total_contribs, active_days, stars, agg, colours):
    """Figures and languages side by side on a wide column, stacked below it.

    Both layouts live in the same file and the same box; the height is the
    one the stacked variant needs, which leaves the side-by-side one room to
    breathe rather than crowding the top.
    """
    h = 254
    cells = figure_cells(user, all_commits, total_contribs, active_days, stars)
    total = sum(agg.values()) or 1
    top = agg.most_common(6)

    out = fluid_open(h, "GitHub statistics and most used languages")

    # Wide: two halves, divided down the middle.
    out.append('<g class="w">')
    wide_rows = ([(58, 92), (120, 154), (182, 216)] if len(cells) == 3
                 else [(76, 112), (162, 198)])
    out += column(0, 50, h, figures(cells, PAD, 14, 30, wide_rows,
                                    cols=1 if len(cells) == 3 else 2))
    out.append(f'<line x1="50%" y1="30" x2="50%" y2="{h - 30}" '
               f'stroke="{ROW}" stroke-opacity="0.08"/>')
    out += column(50, 50, h,
                  language_bar(top, total, colours, PAD, 68, 80, "barw")
                  + legend(top, total, colours, PAD, [124, 154, 184], 2))
    out.append("</g>")

    # Narrow: the same four figures across the full width, languages under them.
    out.append('<g class="n">')
    out += figures(cells, NARROW_PAD, 12.5, 26, [(40, 70), (104, 134)])
    out += language_bar(top[:4], total, colours, NARROW_PAD, 168, 180, "barn")
    out += legend(top[:4], total, colours, NARROW_PAD, [214, 240], 2, 12.5)
    out.append("</g>")

    out += card_close()
    return "\n".join(out)


def build_pin(repo):
    """One project card, full width, two wrappings of the same description."""
    h = 124
    chip_w = 78
    out = fluid_open(h, f"{repo['name']} repository")
    lang = repo.get("primaryLanguage") or {}
    has_chip = bool(repo.get("pages"))

    for cls, pad, title_size, desc_size, rows, lang_y, budget in (
            ("w", PAD, 15, 12.5, [64, 82], 108, WIDE_REF),
            ("n", NARROW_PAD, 14, 12, [56, 73, 90], 112, NARROW_REF)):
        title_y = rows[0] - 28
        out.append(f'<g class="{cls}">')
        out.append(f'<path d="M{pad} {title_y - 14} h11 a2 2 0 0 1 2 2 v12 a2 2 0 0 1 -2 2 '
                   f'h-11 z" fill="none" stroke="{ACCENT}" stroke-width="1.4"/>')
        name_max = budget - pad * 2 - 26 - (chip_w + 10 if has_chip else 0)
        out.append(f'<text x="{pad + 22}" y="{title_y}" fill="{ACCENT}" '
                   f'font-size="{title_size}" font-weight="600">'
                   f'{esc(truncate(repo["name"], title_size, name_max))}</text>')
        if has_chip:
            out.append(right(pad + chip_w,
                             f'<rect x="100%" y="{title_y - 16}" width="{chip_w}" '
                             f'height="19" rx="9.5" fill="{ACCENT_ALT}" fill-opacity="0.16"/>'))
            out.append(right(pad + chip_w / 2,
                             f'<text x="100%" y="{title_y - 2.5}" fill="{ACCENT_ALT}" '
                             f'font-size="10.5" text-anchor="middle">Write-up \u2192</text>'))

        for i, line in enumerate(wrap(repo.get("description") or "", desc_size,
                                      budget - pad * 2, len(rows))):
            out.append(f'<text x="{pad}" y="{rows[i]}" fill="{MUTED}" '
                       f'font-size="{desc_size}">{esc(line)}</text>')

        if lang.get("name"):
            out.append(f'<circle cx="{pad + 5}" cy="{lang_y - 4}" r="5" '
                       f'fill="{lang.get("color") or ACCENT}"/>')
            out.append(f'<text x="{pad + 17}" y="{lang_y}" fill="{TITLE}" font-size="12">'
                       f'{esc(lang["name"])}</text>')
        stats = []
        if repo.get("stargazerCount"):
            stats.append(f"\u2605 {human(repo['stargazerCount'])}")
        if repo.get("forkCount"):
            stats.append(f"\u2387 {human(repo['forkCount'])}")
        if stats:
            out.append(right(pad, f'<text x="100%" y="{lang_y}" fill="{DIM}" font-size="12" '
                                  f'text-anchor="end" font-family="{MONO}">'
                                  f'{esc("  ".join(stats))}</text>'))
        out.append("</g>")

    out += card_close()
    return "\n".join(out)


def main():
    if not TOKEN:
        print("::error::GH_TOKEN is empty; cannot query the GitHub API")
        return 1
    try:
        user = graphql(PROFILE_Q, login=LOGIN)["user"]
        created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
        days = calendar_days(created)
        commits = rest(f"search/commits?q=author:{LOGIN}&per_page=1")["total_count"]
        # Featured Projects is every public repo carrying a published
        # write-up, newest push first. Detected rather than listed, so a
        # write-up added later shows up without editing the workflow, and a
        # repo made private drops out instead of 404ing for visitors.
        names = PINS or [r["name"] for r in
                         graphql(PUBLIC_Q, login=LOGIN)["user"]["repositories"]["nodes"]]
        pins = []
        for name in names:
            page = pages_url(name)
            if not page:
                continue
            repo = graphql(REPO_Q, owner=LOGIN, name=name)["repository"]
            repo["pages"] = page
            pins.append(repo)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError) as exc:
        print(f"::warning::GitHub API call failed ({exc}); keeping existing panels")
        return 0

    year = dt.datetime.now(dt.timezone.utc).year
    year_total = sum(c for d, c in days.items() if d.startswith(str(year)))
    # Days actually worked, not the calendar's length: the count of days
    # this year that carry at least one contribution.
    active_days = sum(1 for d, c in days.items() if d.startswith(str(year)) and c)
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    # include_all_commits counts every commit the search index knows about,
    # which is larger than this calendar year's contributions.
    all_commits = max(commits, year_total)

    agg = collections.Counter()
    colours = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name.lower() in EXCLUDE_LANGS:
                continue
            agg[name] += edge["size"]
            colours[name] = edge["node"]["color"]

    write(f"{OUTDIR}/stats.svg",
          build_overview(user, all_commits, year_total, active_days, stars, agg,
                         colours))
    for repo in pins:
        write(f"{OUTDIR}/pin-{repo['name']}.svg", build_pin(repo))
    print(f"{len(pins)} project(s) with a write-up")

    # One card per line, each the full width of the column. Two 415px cards
    # side by side only ever lined up at desktop width: on a tablet column
    # they wrapped to one per line anyway, stranded in the middle with a
    # third of the column empty either side.
    cards = "\n".join(
        f'<a href="{r["pages"]}"><img src="{OUTDIR}/pin-{r["name"]}.svg" '
        f'width="100%" alt="{esc(r["name"])}"/></a>' for r in pins)
    readme = pathlib.Path(README)
    if readme.exists():
        text = readme.read_text()
        block = f"<!--START_SECTION:featured-->\n{cards}\n<!--END_SECTION:featured-->"
        updated = re.sub(r"<!--START_SECTION:featured-->.*?<!--END_SECTION:featured-->",
                         lambda _m: block, text, flags=re.S)
        if updated != text:
            readme.write_text(updated)
            print("updated the featured block in README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
