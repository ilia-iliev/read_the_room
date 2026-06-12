"""Images for the room — all returned as inline data URIs so nothing depends on Gradio's
file serving and the whole app stays a single drop-in.

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
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

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
