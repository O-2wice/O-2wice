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
import pathlib
import re
import sys

from svg_common import (ACCENT, ACCENT_ALT, BG, FONT, MONO, MUTED, NARROW_MAX, light_css,
                        NARROW_REF, TITLE, WIDE_REF, esc, fetch, mono_width,
                        text_width, wrap, write)

OUTDIR = os.environ.get("OUT_DIR", "metrics")
README = os.environ.get("README_PATH", "README.md")

# The live service returns a different quote per request, which the built
# panel cannot do: an SVG loaded through <img> runs no script, so a
# committed file can only cycle on a timer. Point at the service while it
# answers and fall back to the committed panel when it does not, so an
# outage costs freshness rather than leaving a broken image.
QUOTE_SERVICE = ("https://quotes-github-readme.vercel.app/api"
                 "?type=horizontal&theme=tokyonight")
NAME = os.environ.get("PROFILE_NAME", "O_2wice")
TAGLINE = os.environ.get("PROFILE_TAGLINE",
                         "Data Scientist")

TYPING_LINES = [
    "Actuarial Science to Data Science",
    "Nairobi to Budapest",
    "Eight years in industry, now back in class",
    "Still reads the balance sheet first",
]

# Cycled inside the SVG rather than picked per build: the panel is a static
# file, so a daily rebuild is the most it could otherwise change, and the
# service this replaced rotated on every page load.
QUOTES = [
    ("All models are wrong, but some are useful.", "George Box"),
    ("In God we trust. All others must bring data.", "W. Edwards Deming"),
    ("Without data you're just another person with an opinion.", "W. Edwards Deming"),
    ("The goal is to turn data into information, and information into insight.",
     "Carly Fiorina"),
    ("The purpose of computing is insight, not numbers.", "Richard Hamming"),
    ("Statistics are the grammar of science.", "Karl Pearson"),
    ("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
    ("It is a capital mistake to theorise before one has data.",
     "Arthur Conan Doyle"),
    ("Torture the data, and it will confess to anything.", "Ronald Coase"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("An approximate answer to the right problem is worth a good deal more "
     "than an exact answer to an approximate problem.", "John Tukey"),
    ("The greatest value of a picture is that it forces us to notice what we "
     "never expected to see.", "John Tukey"),
    ("Programs must be written for people to read.", "Harold Abelson"),
    ("Data is a precious thing and will last longer than the systems themselves.",
     "Tim Berners-Lee"),
    ("Prediction is very difficult, especially about the future.", "Niels Bohr"),
    ("Debugging is twice as hard as writing the code in the first place.",
     "Brian Kernighan"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Measure what is measurable, and make measurable what is not so.",
     "Galileo Galilei"),
    ("Errors using inadequate data are much less than those using no data at all.",
     "Charles Babbage"),
    ("Simple things should be simple, complex things should be possible.",
     "Alan Kay"),
    ("Not everything that can be counted counts, and not everything that counts "
     "can be counted.", "William Bruce Cameron"),
    ("It is easy to lie with statistics. It is hard to tell the truth without them.",
     "Andrejs Dunkels"),
    ("A distributed system is one in which the failure of a computer you did not "
     "know existed can render your own computer unusable.", "Leslie Lamport"),
]

# How many of the pool appear in any one build. The panel cycles these
# in-page; the window advances each day so the set differs day to day.
QUOTES_SHOWN = int(os.environ.get("QUOTES_SHOWN", "8"))


def todays_quotes(pool, count, today=None):
    """A window into the pool, advanced by one each day and wrapping round."""
    today = today or dt.date.today()
    start = today.toordinal() % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(min(count, len(pool)))]

# tokyonight, the gradient the rest of the profile uses
WAVE_STOPS = ("#1a1b27", "#414868", "#7aa2f7")


# The waves are one long path rather than a percentage of the panel: SVG
# path data takes no percentages, so it is drawn wide enough for any README
# column and the panel clips what it does not use.
NOMINAL_W = 1200
WAVELENGTH = 300


def wave(height, y_base, amplitude, opacity, seconds, colour):
    """One wave band, scrolled sideways forever by a single transform.

    The path runs from -NOMINAL_W to twice that and shifts by exactly one
    wavelength, so the loop is seamless at any rendered width.
    """
    pts = [f"M{-NOMINAL_W},{y_base}"]
    x = -NOMINAL_W
    up = True
    while x < NOMINAL_W * 2:
        half = WAVELENGTH / 2
        y = y_base - amplitude if up else y_base + amplitude
        pts.append(f"q{half / 2},{y - y_base} {half},{0} "
                   f"q{half / 2},{y_base - y} {half},{0}")
        x += WAVELENGTH
        up = not up
    pts.append(f"L{NOMINAL_W * 2},{height + 4} L{-NOMINAL_W},{height + 4} Z")
    return (f'<path d="{" ".join(pts)}" fill="{colour}" opacity="{opacity}">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="0 0" to="{WAVELENGTH * 2} 0" dur="{seconds}s" '
            f'repeatCount="indefinite"/>'
            f"</path>")


def banner(height, title=None, subtitle=None, flip=False):
    """The header and footer bands: full width, fixed height.

    Sized in real pixels rather than scaled with the column, so the name is
    the same size on a phone as on a desktop. The title drops a size below
    the breakpoint so it cannot crowd the edges of a narrow column.
    """
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
           f'role="img" aria-label="{esc(title or "section divider")}">',
           "<style>"
           ".n{display:none}"
           f"@media(max-width:{NARROW_MAX}px){{.w{{display:none}}.n{{display:inline}}}}"
           "</style>",
           "<defs>",
           '<linearGradient id="sky" x1="0" y1="0" x2="1" y2="0">'
           f'<stop offset="0" stop-color="{WAVE_STOPS[0]}"/>'
           f'<stop offset="0.55" stop-color="{WAVE_STOPS[1]}"/>'
           f'<stop offset="1" stop-color="{WAVE_STOPS[2]}"/></linearGradient>',
           "</defs>",
           f'<rect width="100%" height="{height}" fill="url(#sky)"/>']

    # Three bands at different speeds, each a touch darker than the sky, so
    # the crests stay legible whatever the viewer's theme.
    body = [wave(height, height * 0.60, height * 0.11, 0.30, 13, "#1a1b27"),
            wave(height, height * 0.74, height * 0.09, 0.45, 18, "#161722"),
            wave(height, height * 0.88, height * 0.07, 0.75, 24, "#12131c")]
    if flip:
        out.append(f'<g transform="translate(0,{height}) scale(1,-1)">')
        out += body
        out.append("</g>")
    else:
        out += body

    if title:
        out.append(f'<g font-family="{FONT}" text-anchor="middle">')
        for cls, size, sub_size in (("w", 42, 15), ("n", 31, 13)):
            out.append(f'<g class="{cls}">')
            out.append(f'<text x="50%" y="{height * 0.44}" fill="#ffffff" '
                       f'font-size="{size}" font-weight="700" letter-spacing="1">{esc(title)}'
                       f'<animate attributeName="opacity" from="0" to="1" dur="1.2s" '
                       f'fill="freeze"/></text>')
            if subtitle:
                out.append(f'<text x="50%" y="{height * 0.62}" fill="#dfe4f5" '
                           f'font-size="{sub_size}" letter-spacing="0.6">{esc(subtitle)}'
                           f'<animate attributeName="opacity" from="0" to="1" dur="1.8s" '
                           f'fill="freeze"/></text>')
            out.append("</g>")
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def typing_lines(lines, size, height, cls, hold=2.2, per_char=0.055):
    """One typed-out set of lines at one font size, centred on the panel.

    Each line is revealed by animating the width of its own clip rectangle,
    so nothing is ever painted over the page background. A mask filled with
    the panel colour would show as a dark block in GitHub's light theme.
    The clip rectangle is anchored at x="50%" and pulled back by half the
    line, which is the only way to centre a fixed-width box in a fluid
    panel: percentages resolve against the viewport and SVG has no calc().
    """
    steps = [(text, len(text) * per_char, hold, len(text) * per_char * 0.4)
             for text in lines]
    total = sum(draw + hold + erase for _, draw, hold, erase in steps)

    defs, marks, at = [], [], 0.0
    for i, (text, draw, hold_s, erase) in enumerate(steps):
        w = mono_width(text, size)
        cycle = draw + hold_s + erase
        # 0 -> full while typing, full while held, back to 0 while erasing.
        keys = (f"0;{at / total:.4f};{(at + draw) / total:.4f};"
                f"{(at + draw + hold_s) / total:.4f};{(at + cycle) / total:.4f};1")
        defs.append(
            f'<clipPath id="{cls}{i}"><rect x="50%" y="0" height="{height}" width="0" '
            f'transform="translate({-w / 2:.1f},0)">'
            f'<animate attributeName="width" values="0;0;{w:.1f};{w:.1f};0;0" '
            f'keyTimes="{keys}" dur="{total:.2f}s" repeatCount="indefinite"/>'
            f"</rect></clipPath>")
        marks.append((i, text, w, at, draw, hold_s, cycle, keys))
        at += cycle

    out = [f'<g class="{cls}" font-family="{MONO}" font-size="{size}" '
           f'font-weight="600" fill="#6AD3F7">']
    for i, text, w, at, draw, hold_s, cycle, keys in marks:
        out.append(f'<text x="50%" y="{height * 0.63}" text-anchor="middle" '
                   f'clip-path="url(#{cls}{i})">{esc(text)}</text>')
        # Caret rides the right edge of the reveal, then blinks during the hold.
        # Opacity must sit at 0 across the whole lead-in and tail. Values of
        # 0;1;...;1;0 interpolate linearly from the first keyTime, so every
        # caret faded in over the preceding line and out over the following
        # ones, leaving several bars stacked on the text at once.
        # The caret animates in plain user units, so it rides inside a nested
        # viewport pinned to the centre of the panel and is allowed to draw
        # outside it; animating a percentage x directly is not expressible.
        x0, x1 = -w / 2, w / 2
        out.append(
            f'<svg x="50%" y="0" width="50%" height="{height}" style="overflow:visible">'
            f'<rect y="{height * 0.26}" width="2" height="{size * 1.05:.1f}" '
            f'fill="#6AD3F7" opacity="0" x="{x0:.1f}">'
            f'<animate attributeName="x" values="{x0:.1f};{x0:.1f};{x1:.1f};'
            f'{x1:.1f};{x0:.1f};{x0:.1f}" '
            f'keyTimes="{keys}" dur="{total:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;1;1;1;0;0" keyTimes="{keys}" '
            f'calcMode="discrete" dur="{total:.2f}s" repeatCount="indefinite"/>'
            f"</rect></svg>")
    out.append("</g>")
    return defs, out


def typing(lines, height=46):
    """The typing panel, carrying a large and a small set of the same lines.

    The longest line is 41 characters; at 21px monospace that needs 520px,
    which a phone column does not have, so the narrow variant re-runs the
    same animation at 13px rather than dropping lines.
    """
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
           f'role="img" aria-label="{esc(" · ".join(lines))}">',
           "<style>"
           ".n{display:none}"
           f"@media(max-width:{NARROW_MAX}px){{.w{{display:none}}.n{{display:inline}}}}"
           "@media(prefers-color-scheme:light){[fill=\"#6AD3F7\"]{fill:#0b6f8a}}"
           "</style>"]
    wide_defs, wide_body = typing_lines(lines, 21, height, "w")
    narrow_defs, narrow_body = typing_lines(lines, 13, height, "n")
    out.append("<defs>")
    out += wide_defs + narrow_defs
    out.append("</defs>")
    out += wide_body + narrow_body
    out.append("</svg>")
    return "\n".join(out)


def quote_card(quotes, seconds_each=7.0, fade=0.5):
    """All the quotes in one fluid panel, cross-fading forever.

    Wrapped twice, once for a phone column and once for anything wider, and
    sized for whichever variant runs to the most lines. Each quote holds at
    zero through the whole lead-in and tail, with equal values either side
    of its slot, so nothing bleeds into a neighbour the way the typing
    carets did.
    """
    size = 15
    # x of the text, and the width budget, per variant. The narrow one drops
    # the hanging quotation mark rather than spend 36px of a phone column on it.
    variants = {"w": (66, WIDE_REF - 40), "n": (18, NARROW_REF - 34)}

    wrapped = {cls: [(wrap(t, size, budget, 6), a) for t, a in quotes]
               for cls, (_, budget) in variants.items()}
    tallest = max(len(lines) for v in wrapped.values() for lines, _ in v)
    height = 74 + tallest * 24
    total = seconds_each * len(quotes)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
           f'role="img" aria-label="{esc(quotes[0][0])}">',
           "<style>"
           ".n{display:none}"
           f"@media(max-width:{NARROW_MAX}px){{.w{{display:none}}.n{{display:inline}}}}"
           f"{light_css()}"
           "</style>",
           "<defs>",
           '<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
           f'<stop offset="0" stop-color="{ACCENT}"/>'
           f'<stop offset="1" stop-color="{ACCENT_ALT}"/></linearGradient>',
           "</defs>",
           f'<rect width="100%" height="{height}" rx="12" fill="{BG}"/>',
           f'<rect width="100%" height="3" rx="1.5" fill="url(#accent)" opacity="0.85"/>',
           f'<text class="w" x="30" y="{44 + (tallest - 1) * 12}" fill="{ACCENT}" '
           f'font-family="Georgia,serif" font-size="52" opacity="0.5">\u201c</text>',
           f'<g font-family="{FONT}">']

    for cls, (x, _) in variants.items():
        out.append(f'<g class="{cls}">')
        for i, (lines, author) in enumerate(wrapped[cls]):
            s0, e0 = i * seconds_each / total, (i + 1) * seconds_each / total
            f0 = fade / total
            keys = (f"0;{s0:.5f};{min(s0 + f0, e0):.5f};"
                    f"{max(e0 - f0, s0):.5f};{e0:.5f};1")
            top = 48 + (tallest - len(lines)) * 12
            out.append(f'<g opacity="0"><animate attributeName="opacity" '
                       f'values="0;0;1;1;0;0" keyTimes="{keys}" dur="{total:.2f}s" '
                       f'repeatCount="indefinite"/>')
            for j, line in enumerate(lines):
                out.append(f'<text x="{x}" y="{top + j * 24}" fill="{TITLE}" '
                           f'font-size="{size}">{esc(line)}</text>')
            out.append(f'<text x="{x}" y="{top + len(lines) * 24 + 12}" fill="{MUTED}" '
                       f'font-size="12.5">\u2014 {esc(author)}</text>')
            out.append("</g>")
        out.append("</g>")

    out.append("</g></svg>")
    return "\n".join(out)


def quote_markup():
    """The service if it is answering, otherwise the committed panel.

    The service is the live one: a different quote per request, which a
    committed file cannot do, since an SVG loaded through <img> runs no
    script and can only cycle on a timer. Its card is a fixed 600px box in a
    foreignObject, so unlike the panels here it scales with the column
    instead of reflowing - that is the price of the freshness, and it is
    paid deliberately. The committed panel is the fallback for an outage.
    """
    try:
        body = fetch(QUOTE_SERVICE, timeout=15).decode("utf-8", "replace")
        if "<svg" not in body:
            raise RuntimeError("response was not an SVG")
        print("quote: live service is up, pointing at it")
        return f'<img src="{QUOTE_SERVICE}" width="760" alt="Quote"/>'
    except Exception as exc:
        print(f"::warning::quote service unavailable ({exc}); using the committed panel")
        return '<img src="metrics/quote.svg" width="100%" alt="Quote"/>'


def main():
    write(f"{OUTDIR}/header.svg", banner(150, NAME, TAGLINE))
    write(f"{OUTDIR}/footer.svg", banner(84, flip=True))
    write(f"{OUTDIR}/typing.svg", typing(TYPING_LINES))
    write(f"{OUTDIR}/quote.svg", quote_card(todays_quotes(QUOTES, QUOTES_SHOWN)))

    readme = pathlib.Path(README)
    if readme.exists():
        text = readme.read_text()
        block = f"<!--START_SECTION:quote-->\n{quote_markup()}\n<!--END_SECTION:quote-->"
        updated = re.sub(r"<!--START_SECTION:quote-->.*?<!--END_SECTION:quote-->",
                         lambda _m: block, text, flags=re.S)
        if updated != text:
            readme.write_text(updated)
            print("updated the quote block in README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
