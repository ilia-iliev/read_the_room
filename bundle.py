"""A scenario bundle: one shareable `.zip` carrying the spec plus its art.

An authored scenario has no asset folder on disk (its id is transient), so its art rides
along with it instead. A bundle is a zip of:

    scenario.json      <- the editable spec (exactly what's in the editor)
    scene.<ext>        <- the scene banner, if one was added
    <character>.<ext>  <- one avatar per character, named by the same slug as on disk

That mirrors `scenarios/assets/<id>/` one-for-one, so a downloaded bundle's art could even
be dropped straight into a permanent asset folder. `art` here is the in-session mapping the
creator UI holds: 'scene' and each character slug -> an image filepath (the upload).
"""

import tempfile
import zipfile
from pathlib import Path

from art import IMAGE_EXTS

SPEC_NAME = "scenario.json"


def pack(spec_text, art):
    """Zip the spec text plus any uploaded art into a downloadable bundle; return its path."""
    out = Path(tempfile.mkdtemp()) / "scenario-bundle.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(SPEC_NAME, spec_text or "")
        for key, path in (art or {}).items():
            p = Path(path) if path else None
            if p and p.is_file():
                z.write(p, f"{key}{p.suffix.lower() or '.png'}")
    return str(out)


def unpack(zip_path):
    """Read a bundle back into `(spec_text, art)`. Images are extracted to a temp dir and the
    art mapping holds their filepaths, keyed by stem ('scene' or a character slug)."""
    out = Path(tempfile.mkdtemp())
    spec_text, art = "", {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name == SPEC_NAME:
                spec_text = z.read(name).decode("utf-8")
            elif name.lower().endswith(IMAGE_EXTS):
                dest = out / Path(name).name
                dest.write_bytes(z.read(name))
                art[dest.stem] = str(dest)
    return spec_text, art
