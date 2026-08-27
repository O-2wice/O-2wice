#!/usr/bin/env python3
"""Render the decorative README chrome: header, footer, typing line, quote.

These four were the last page-load calls to other people's servers
(capsule-render.vercel.app, readme-typing-svg.demolab.com and
quotes-github-readme.vercel.app). They hold no live data, so they are drawn
here and committed once; only the quote changes, rotating by date.

SVG animation survives GitHub's image proxy, so the wave and the typing
caret still move.
"""

import datetime as dt
import os
import sys

from svg_common import (ACCENT, ACCENT_ALT, BG, DIM, FONT, MONO, MUTED, ROW,
                        TITLE, esc, mono_width, text_width, write)

OUTDIR = os.environ.get("OUT_DIR", "metrics")
NAME = os.environ.get("PROFILE_NAME", "O_2wice")
TAGLINE = os.environ.get("PROFILE_TAGLINE",
                         "Data Scientist  |  ML Engineer  |  Risk & ERP Analytics")

TYPING_LINES = [
    "Actuarial Science to Machine Learning",
    "Turning Data into Decisions",
    "Building ML Systems that Scale",
    "Natural Language to SQL for ERP Systems",
]

# Rotated by day so the panel still changes without calling a quote service.
QUOTES = [
    ("All models are wrong, but some are useful.", "George Box"),
    ("In God we trust. All others must bring data.", "W. Edwards Deming"),
    ("The goal is to turn data into information, and information into insight.",
     "Carly Fiorina"),
    ("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
    ("It is a capital mistake to theorise before one has data.",
     "Arthur Conan Doyle"),
    ("Torture the data, and it will confess to anything.", "Ronald Coase"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("An approximate answer to the right problem is worth a good deal more "
     "than an exact answer to an approximate problem.", "John Tukey"),
    ("Programs must be written for people to read.", "Harold Abelson"),
    ("Data is a precious thing and will last longer than the systems themselves.",
     "Tim Berners-Lee"),
]

# tokyonight, the gradient the rest of the profile uses
WAVE_STOPS = ("#1a1b27", "#414868", "#7aa2f7")


def wave(width, height, y_base, amplitude, opacity, seconds, colour):
    """One wave band, scrolled sideways forever by a single transform.

    The path is drawn three widths wide and shifted by exactly one
    wavelength, so the loop is seamless.
    """
    length = width / 2.5
    pts = [f"M{-width},{y_base}"]
    x = -width
    up = True
    while x < width * 2:
        half = length / 2
        y = y_base - amplitude if up else y_base + amplitude
        pts.append(f"q{half / 2},{y - y_base} {half},{0} "
                   f"q{half / 2},{y_base - y} {half},{0}")
        x += length
        up = not up
    pts.append(f"L{width * 2},{height + 4} L{-width},{height + 4} Z")
    return (f'<path d="{" ".join(pts)}" fill="{colour}" opacity="{opacity}">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="0 0" to="{length * 2} 0" dur="{seconds}s" '
            f'repeatCount="indefinite"/>'
            f"</path>")


def banner(width, height, title=None, subtitle=None, flip=False):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{esc(title or "section divider")}">',
           "<defs>",
           '<linearGradient id="sky" x1="0" y1="0" x2="1" y2="0">'
           f'<stop offset="0" stop-color="{WAVE_STOPS[0]}"/>'
           f'<stop offset="0.55" stop-color="{WAVE_STOPS[1]}"/>'
           f'<stop offset="1" stop-color="{WAVE_STOPS[2]}"/></linearGradient>',
           "</defs>",
           f'<rect width="{width}" height="{height}" fill="url(#sky)"/>']

    # Three bands at different speeds, each a touch darker than the sky, so
    # the crests stay legible whatever the viewer's theme.
    body = [wave(width, height, height * 0.60, height * 0.11, 0.30, 13, "#1a1b27"),
            wave(width, height, height * 0.74, height * 0.09, 0.45, 18, "#161722"),
            wave(width, height, height * 0.88, height * 0.07, 0.75, 24, "#12131c")]
    if flip:
        out.append(f'<g transform="translate(0,{height}) scale(1,-1)">')
        out += body
        out.append("</g>")
    else:
        out += body

    if title:
        out.append(f'<g font-family="{FONT}" text-anchor="middle">')
        out.append(f'<text x="{width / 2}" y="{height * 0.44}" fill="#ffffff" '
                   f'font-size="42" font-weight="700" letter-spacing="1">{esc(title)}'
                   f'<animate attributeName="opacity" from="0" to="1" dur="1.2s" '
                   f'fill="freeze"/></text>')
        if subtitle:
            out.append(f'<text x="{width / 2}" y="{height * 0.62}" fill="#dfe4f5" '
                       f'font-size="15" letter-spacing="0.6">{esc(subtitle)}'
                       f'<animate attributeName="opacity" from="0" to="1" dur="1.8s" '
                       f'fill="freeze"/></text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def typing(lines, width=620, height=52, hold=2.2, per_char=0.055):
    """Type each line out, hold it, erase it, move on. Loops forever.

    Each line is revealed by animating the width of its own clip rectangle,
    so nothing is ever painted over the page background. A mask filled with
    the panel colour would show as a dark block in GitHub's light theme.
    """
    steps = [(text, len(text) * per_char, hold, len(text) * per_char * 0.4)
             for text in lines]
    total = sum(draw + hold + erase for _, draw, hold, erase in steps)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{esc(" · ".join(lines))}">',
           "<defs>"]

    at = 0.0
    marks = []
    for i, (text, draw, hold_s, erase) in enumerate(steps):
        w = mono_width(text, 21)
        x0 = width / 2 - w / 2
        cycle = draw + hold_s + erase
        # 0 -> full while typing, full while held, back to 0 while erasing.
        keys = (f"0;{at / total:.4f};{(at + draw) / total:.4f};"
                f"{(at + draw + hold_s) / total:.4f};{(at + cycle) / total:.4f};1")
        out.append(
            f'<clipPath id="t{i}"><rect x="{x0:.1f}" y="0" height="{height}" width="0">'
            f'<animate attributeName="width" values="0;0;{w:.1f};{w:.1f};0;0" '
            f'keyTimes="{keys}" dur="{total:.2f}s" repeatCount="indefinite"/>'
            f"</rect></clipPath>")
        marks.append((i, text, x0, w, at, draw, hold_s, cycle))
        at += cycle
    out.append("</defs>")
    out.append(f'<g font-family="{MONO}" font-size="21" font-weight="600" fill="#6AD3F7">')

    for i, text, x0, w, at, draw, hold_s, cycle in marks:
        out.append(f'<text x="{x0:.1f}" y="{height * 0.63}" clip-path="url(#t{i})">'
                   f'{esc(text)}</text>')
        # Caret rides the right edge of the reveal, then blinks during the hold.
        keys = (f"0;{at / total:.4f};{(at + draw) / total:.4f};"
                f"{(at + draw + hold_s) / total:.4f};{(at + cycle) / total:.4f};1")
        out.append(
            f'<rect y="{height * 0.26}" width="2" height="{height * 0.44}" '
            f'fill="#6AD3F7" opacity="0" x="{x0:.1f}">'
            f'<animate attributeName="x" values="{x0:.1f};{x0:.1f};{x0 + w:.1f};'
            f'{x0 + w:.1f};{x0:.1f};{x0:.1f}" keyTimes="{keys}" '
            f'dur="{total:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;1;1;1;1;0" keyTimes="{keys}" '
            f'dur="{total:.2f}s" repeatCount="indefinite"/></rect>')

    out.append("</g></svg>")
    return "\n".join(out)


def quote_card(text, author, width=760):
    size, inner = 15, width - 116
    words, line, lines = text.split(), "", []
    for word in words:
        trial = f"{line} {word}".strip()
        if text_width(trial, size) > inner:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)

    height = 74 + len(lines) * 24
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-label="Quote">',
           "<defs>",
           '<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
           f'<stop offset="0" stop-color="{ACCENT}"/>'
           f'<stop offset="1" stop-color="{ACCENT_ALT}"/></linearGradient>',
           "</defs>",
           f'<rect width="{width}" height="{height}" rx="12" fill="{BG}"/>',
           f'<rect width="{width}" height="3" rx="1.5" fill="url(#accent)" opacity="0.85"/>',
           f'<text x="30" y="{44 + (len(lines) - 1) * 12}" fill="{ACCENT}" '
           f'font-family="Georgia,serif" font-size="52" opacity="0.5">“</text>',
           f'<g font-family="{FONT}">']
    for i, text_line in enumerate(lines):
        out.append(f'<text x="66" y="{48 + i * 24}" fill="{TITLE}" font-size="{size}">'
                   f'{esc(text_line)}</text>')
    out.append(f'<text x="66" y="{60 + len(lines) * 24}" fill="{MUTED}" font-size="12.5">'
               f'— {esc(author)}</text>')
    out.append("</g></svg>")
    return "\n".join(out)


def main():
    today = dt.date.today()
    text, author = QUOTES[today.toordinal() % len(QUOTES)]
    write(f"{OUTDIR}/header.svg", banner(860, 180, NAME, TAGLINE))
    write(f"{OUTDIR}/footer.svg", banner(860, 100, flip=True))
    write(f"{OUTDIR}/typing.svg", typing(TYPING_LINES))
    write(f"{OUTDIR}/quote.svg", quote_card(text, author))
    return 0


if __name__ == "__main__":
    sys.exit(main())
