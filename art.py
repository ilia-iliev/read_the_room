"""Images and the theme font for the room — all returned as inline data URIs so nothing
depends on Gradio's file serving (or the network) and the whole app stays a single drop-in.

Art is CONVENTION, not configuration. Drop files under `scenarios/assets/<scenario-id>/`:

    scenarios/assets/hero/scene.png     <- the shared scene banner
    scenarios/assets/hero/korg.png      <- one avatar per character, named after them
    scenarios/assets/hero/vesh.png         (slug of the character's name; png/jpg/jpeg/webp)

If a file is there it's used; if not, an avatar falls back to a generated coloured initial
disc and a scene banner is simply not shown — real art swaps in just by adding a file.
Authored (Create-your-own) scenarios have transient ids and no asset folder, so they get
the generated placeholders.
"""

import base64
import hashlib
import mimetypes
import re
from pathlib import Path

ASSETS = Path(__file__).parent / "scenarios" / "assets"
FONTS = Path(__file__).parent / "fonts"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Alkatra (variable, weights 400–700) bundled per script subset, mirroring the split —
# and unicode-range — of fonts.googleapis.com, so the page never fetches a font.
FONT_SUBSETS = {
    "alkatra-latin.woff2": (
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,"
        "U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,"
        "U+FEFF,U+FFFD"
    ),
    "alkatra-latin-ext.woff2": (
        "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,"
        "U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,"
        "U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
    ),
}

# muted, slightly grim palette — picked per character so the cast reads as distinct discs
PALETTE = [
    "#774936",
    "#6d597a",
    "#355070",
    "#3a5a40",
    "#9a031e",
    "#5f0f40",
    "#1b4332",
    "#4a4e69",
]


def slug(name):
    """A character's name as a filesystem-safe stem: 'Sal "the Whale"' -> 'sal-the-whale'."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _color(name):
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return PALETTE[h % len(PALETTE)]


def _initial(name):
    name = (name or "").strip()
    return name[0].upper() if name else "?"


def _find(scen_id, stem):
    """The art file for one slot (scene banner or a character avatar) under a scenario's
    asset folder, trying each supported extension; None if nothing is on disk."""
    folder = ASSETS / scen_id
    for ext in IMAGE_EXTS:
        p = folder / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def _data_uri(mime, raw):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _svg_uri(svg):
    return _data_uri("image/svg+xml", svg.encode("utf-8"))


def _file_uri(path):
    """A real image file as a data URI, or None when the slot has no art on disk."""
    if path is None:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return _data_uri(mime, path.read_bytes())


def _avatar_svg(initial, color):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" '
        'viewBox="0 0 120 120">'
        f'<circle cx="60" cy="60" r="57" fill="{color}" stroke="#1c1c22" stroke-width="3"/>'
        f'<text x="60" y="62" font-size="56" fill="#f2efe9" text-anchor="middle" '
        f'dominant-baseline="central" font-family="Helvetica,Arial,sans-serif" '
        f'font-weight="600">{initial}</text>'
        "</svg>"
    )


def avatar_uri(scen, char):
    """A round avatar for one character: `<scenario>/<name>.<ext>` on disk, else a
    coloured initial disc."""
    return _file_uri(_find(scen.id, slug(char.name))) or _svg_uri(
        _avatar_svg(_initial(char.name), _color(char.name))
    )


def scene_uri(scen):
    """The scene banner: `<scenario>/scene.<ext>` on disk, else None — no banner is
    shown unless a real image exists."""
    return _file_uri(_find(scen.id, "scene"))


def font_css():
    """@font-face rules with each woff2 inlined as a data URI — same drop-in policy as
    the images: the theme font works with the network cable pulled."""
    return "".join(
        "@font-face{font-family:Alkatra;font-style:normal;font-weight:400 700;"
        "font-display:swap;"
        f"src:url({_data_uri('font/woff2', (FONTS / fname).read_bytes())})"
        f" format('woff2');unicode-range:{urange}}}"
        for fname, urange in FONT_SUBSETS.items()
    )
