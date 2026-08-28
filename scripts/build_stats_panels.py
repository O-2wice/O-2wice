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
import sys
import urllib.error
import urllib.request

from svg_common import (ACCENT, ACCENT_ALT, BG, DIM, FONT, MONO, MUTED, ROW,
                        TITLE, card_close, card_open, esc, heading, human,
                        truncate, write)

LOGIN = os.environ.get("GH_LOGIN", "O-2wice")
TOKEN = os.environ.get("GH_TOKEN", "")
OUTDIR = os.environ.get("OUT_DIR", "metrics")
PINS = [r.strip() for r in os.environ.get("PIN_REPOS", "").split(",") if r.strip()]
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


def streaks(days):
    """Current and longest run of consecutive contributing days.

    Today is excluded from a broken streak: a day with no commits yet is not
    the same as a day that ended with none, and the panel would otherwise
    reset to zero every midnight UTC.
    """
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    longest = longest_start = longest_end = None
    run = run_start = None
    best = 0
    for date, count in days.items():
        if count > 0:
            run = 1 if run is None else run + 1
            run_start = date if run == 1 else run_start
            if run > best:
                best, longest, longest_start, longest_end = run, run, run_start, date
        elif date != today:
            run = None

    current = 0
    current_start = current_end = None
    for date, count in reversed(list(days.items())):
        if count > 0:
            current += 1
            current_end = current_end or date
            current_start = date
        elif date != today:
            break
    return (current, current_start, current_end), (best, longest_start, longest_end)


def fmt_range(start, end):
    if not start or not end:
        return "—"
    d1 = dt.date.fromisoformat(start)
    d2 = dt.date.fromisoformat(end)
    if d1 == d2:
        return d1.strftime("%b %-d")
    if d1.year != d2.year:
        return f"{d1.strftime('%b %-d, %Y')} – {d2.strftime('%b %-d, %Y')}"
    return f"{d1.strftime('%b %-d')} – {d2.strftime('%b %-d, %Y')}"


# Measured on a 2560px window: GitHub caps the README column at about 862px
# on the profile page and 854px on the repo page, so it never goes truly
# full width. Two 424px cards plus the inline gap land on that limit and
# wrap to separate lines. The stats and language halves need no links,
# so they are drawn into one full-width panel that cannot wrap at all; the
# repo cards stay separate because each links to its own repo, and are sized
# to fit two per row.
FULL_W = 860
HALF_W = FULL_W // 2
PIN_W = 415
PAD = 20


def stats_half(user, all_commits, total_contribs, stars, x=0):
    """Four figures as the hero, two per row.

    No card title and no @handle: the README section heading already says
    "GitHub Stats", and the handle is on every other part of the page.
    """
    year = dt.datetime.now(dt.timezone.utc).year
    cells = [("Total commits", human(all_commits)),
             (f"Contributions in {year}", human(total_contribs)),
             ("Public repositories", human(user["repositories"]["totalCount"])),
             ("Followers", human(user["followers"]["totalCount"]))]
    # A row of zeros reads worse than no row at all.
    if stars:
        cells[3] = ("Stars earned", human(stars))

    out = []
    col_w = (HALF_W - PAD * 2) / 2
    for i, (label, value) in enumerate(cells):
        col, row = i % 2, i // 2
        cx = x + PAD + col * col_w
        ly = 54 + row * 68
        out.append(f'<text x="{cx}" y="{ly}" fill="{MUTED}" font-size="11.5">{esc(label)}</text>')
        out.append(f'<text x="{cx}" y="{ly + 33}" fill="{TITLE}" font-size="28" '
                   f'font-weight="600" font-family="{MONO}">{esc(value)}</text>')

    since = dt.date.fromisoformat(user["createdAt"][:10]).strftime("%B %Y")
    out.append(f'<text x="{x + PAD}" y="196" fill="{DIM}" font-size="10">'
               f'since {esc(since)}</text>')
    return out


def langs_half(agg, colours, x=0):
    total = sum(agg.values()) or 1
    top = agg.most_common(6)

    bar_w = HALF_W - PAD * 2
    out = [f'<text x="{x + PAD}" y="40" fill="{MUTED}" font-size="11.5">Most used languages</text>',
           f'<clipPath id="bar"><rect x="{x + PAD}" y="52" width="{bar_w}" '
           f'height="10" rx="5"/></clipPath>',
           '<g clip-path="url(#bar)">']
    bx = x + PAD
    for name, size in top:
        seg = bar_w * size / total
        out.append(f'<rect x="{bx:.2f}" y="52" width="{seg + 0.5:.2f}" height="10" '
                   f'fill="{colours.get(name) or ACCENT}"/>')
        bx += seg
    if bx < x + PAD + bar_w:
        out.append(f'<rect x="{bx:.2f}" y="52" width="{x + PAD + bar_w - bx:.2f}" '
                   f'height="10" fill="{ROW}" fill-opacity="0.08"/>')
    out.append("</g>")

    col_w = bar_w / 2
    for i, (name, size) in enumerate(top):
        col, row = divmod(i, 3)
        cx = x + PAD + col * col_w
        cy = 92 + row * 26
        out.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" '
                   f'fill="{colours.get(name) or ACCENT}"/>')
        out.append(f'<text x="{cx + 17}" y="{cy}" fill="{TITLE}" font-size="12">'
                   f'{esc(truncate(name, 12, col_w - 74))}</text>')
        out.append(f'<text x="{cx + col_w - 20}" y="{cy}" fill="{MUTED}" font-size="11.5" '
                   f'text-anchor="end" font-family="{MONO}">{100 * size / total:.1f}%</text>')

    if EXCLUDE_LANGS:
        pretty = ", ".join(sorted(w.title() for w in EXCLUDE_LANGS))
        out.append(f'<text x="{x + PAD}" y="196" fill="{DIM}" font-size="10">'
                   f'by bytes of source, excluding {esc(pretty)}</text>')
    return out


def build_overview(user, all_commits, total_contribs, stars, agg, colours):
    """Stats and languages as two halves of one panel, so neither can wrap."""
    h = 212
    out = card_open(FULL_W, h, "GitHub statistics and most used languages")
    out += stats_half(user, all_commits, total_contribs, stars, 0)
    out.append(f'<line x1="{HALF_W}" y1="26" x2="{HALF_W}" y2="{h - 26}" '
               f'stroke="{ROW}" stroke-opacity="0.08"/>')
    out += langs_half(agg, colours, HALF_W)
    out += card_close()
    return "\n".join(out)


def build_streak(days, current, longest):
    w, h = 860, 150
    total = sum(days.values())
    cur_n, cur_s, cur_e = current
    long_n, long_s, long_e = longest
    first = next(iter(days)) if days else None

    cells = [
        ("Total contributions", human(total), fmt_range(first, max(days)) if days else "—"),
        ("Current streak", f"{cur_n} {'day' if cur_n == 1 else 'days'}", fmt_range(cur_s, cur_e)),
        ("Longest streak", f"{long_n} {'day' if long_n == 1 else 'days'}", fmt_range(long_s, long_e)),
    ]

    out = card_open(w, h, "Contribution streak")
    third = w / 3
    for i, (label, value, sub) in enumerate(cells):
        cx = third * i + third / 2
        if i:
            out.append(f'<line x1="{third * i}" y1="34" x2="{third * i}" y2="{h - 26}" '
                       f'stroke="{ROW}" stroke-opacity="0.08"/>')
        colour = ACCENT if i == 1 else TITLE
        out.append(f'<text x="{cx}" y="52" fill="{MUTED}" font-size="12" '
                   f'text-anchor="middle">{esc(label)}</text>')
        out.append(f'<text x="{cx}" y="96" fill="{colour}" font-size="34" font-weight="600" '
                   f'text-anchor="middle" font-family="{MONO}">{esc(value)}</text>')
        out.append(f'<text x="{cx}" y="120" fill="{DIM}" font-size="11" '
                   f'text-anchor="middle">{esc(sub)}</text>')
    out += card_close()
    return "\n".join(out)


def build_activity(days, window=30):
    w, h = 860, 240
    recent = list(days.items())[-window:]
    counts = [c for _, c in recent]
    peak = max(counts) if counts else 0
    scale_top = max(peak, 4)

    left, right, top, bottom = 52, w - PAD, 74, h - 36
    span = right - left
    plot_h = bottom - top
    step = span / max(len(recent) - 1, 1)

    def px(i):
        return left + i * step

    def py(v):
        return bottom - (v / scale_top) * plot_h

    out = card_open(w, h, "Contribution activity")
    out.append(f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
               f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.45"/>'
               f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0.02"/></linearGradient>')
    out.append(heading(PAD, 34, "Contribution Activity"))
    out.append(f'<text x="{w - PAD}" y="34" fill="{DIM}" font-size="11" text-anchor="end">'
               f'last {len(recent)} days · {sum(counts)} contributions</text>')

    for frac in (0, 0.5, 1):
        gy = bottom - frac * plot_h
        out.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                   f'stroke="{ROW}" stroke-opacity="0.07"/>')
        out.append(f'<text x="{left - 10}" y="{gy + 4:.1f}" fill="{DIM}" font-size="10.5" '
                   f'text-anchor="end" font-family="{MONO}">{round(frac * scale_top)}</text>')

    pts = " ".join(f"{px(i):.1f},{py(c):.1f}" for i, c in enumerate(counts))
    out.append(f'<polygon points="{left},{bottom} {pts} {right},{bottom}" fill="url(#fill)"/>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="{ACCENT}" stroke-width="2" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')

    for i, (date, count) in enumerate(recent):
        if count == peak and peak:
            out.append(f'<circle cx="{px(i):.1f}" cy="{py(count):.1f}" r="3.5" fill="{ACCENT_ALT}" '
                       f'stroke="{BG}" stroke-width="1.5"/>')
    # A label every fifth day keeps the axis readable at 860px.
    for i, (date, _) in enumerate(recent):
        if i % 5 == 0 or i == len(recent) - 1:
            out.append(f'<text x="{px(i):.1f}" y="{bottom + 18}" fill="{DIM}" font-size="10" '
                       f'text-anchor="middle">'
                       f'{dt.date.fromisoformat(date).strftime("%-d %b")}</text>')
    out += card_close()
    return "\n".join(out)


def build_pin(repo):
    w, h = PIN_W, 140
    out = card_open(w, h, f"{repo['name']} repository")
    out.append(f'<path d="M{PAD} 26 h11 a2 2 0 0 1 2 2 v12 a2 2 0 0 1 -2 2 h-11 z" fill="none" '
               f'stroke="{ACCENT}" stroke-width="1.4"/>')
    chip_w = 74
    name_max = w - PAD * 2 - 26 - (chip_w + 10 if repo.get("pages") else 0)
    out.append(f'<text x="{PAD + 22}" y="40" fill="{ACCENT}" font-size="14.5" font-weight="600">'
               f'{esc(truncate(repo["name"], 14.5, name_max))}</text>')
    if repo.get("pages"):
        out.append(f'<rect x="{w - PAD - chip_w}" y="24" width="{chip_w}" height="19" rx="9.5" '
                   f'fill="{ACCENT_ALT}" fill-opacity="0.16"/>')
        out.append(f'<text x="{w - PAD - chip_w / 2}" y="37.5" fill="{ACCENT_ALT}" '
                   f'font-size="10.5" text-anchor="middle">Write-up →</text>')

    desc = repo.get("description") or ""
    words, line, lines = desc.split(), "", []
    clipped = False
    for word in words:
        trial = f"{line} {word}".strip()
        if truncate(trial, 12, w - PAD * 2) != trial:
            lines.append(line)
            line = word
            if len(lines) == 3:
                clipped = True
                break
        else:
            line = trial
    if line and len(lines) < 3:
        lines.append(line)
    for i, text in enumerate(lines):
        # Mark the cut so a clipped description does not read as a full one.
        if clipped and i == len(lines) - 1:
            text = truncate(text + " …", 12, w - PAD * 2)
        out.append(f'<text x="{PAD}" y="{64 + i * 17}" fill="{MUTED}" font-size="12">'
                   f'{esc(text)}</text>')

    lang = repo.get("primaryLanguage") or {}
    y = h - 20
    if lang.get("name"):
        out.append(f'<circle cx="{PAD + 5}" cy="{y - 4}" r="5" fill="{lang.get("color") or ACCENT}"/>')
        out.append(f'<text x="{PAD + 17}" y="{y}" fill="{TITLE}" font-size="12">'
                   f'{esc(lang["name"])}</text>')
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
        pins = []
        for name in PINS:
            repo = graphql(REPO_Q, owner=LOGIN, name=name)["repository"]
            repo["pages"] = pages_url(name)
            pins.append(repo)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError) as exc:
        print(f"::warning::GitHub API call failed ({exc}); keeping existing panels")
        return 0

    year = dt.datetime.now(dt.timezone.utc).year
    year_total = sum(c for d, c in days.items() if d.startswith(str(year)))
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

    current, longest = streaks(days)

    write(f"{OUTDIR}/stats.svg",
          build_overview(user, all_commits, year_total, stars, agg, colours))
    write(f"{OUTDIR}/streak.svg", build_streak(days, current, longest))
    write(f"{OUTDIR}/activity.svg", build_activity(days))
    for repo in pins:
        write(f"{OUTDIR}/pin-{repo['name']}.svg", build_pin(repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
