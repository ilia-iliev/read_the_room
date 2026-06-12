"""Community scenarios: a public HF dataset repo anyone can publish to through the app.

Each entry is one folder — `<timestamp>-<id>/scenario.txt` (the same spec JSON the creator
saves) plus an optional `scene.<ext>` picture, shown on the gallery card and as the in-game
backdrop. The folder name sorts chronologically, so newest-first is a reverse sort. Reads
are anonymous; publishing needs HF_TOKEN (the Space's secret) with write access. Like the
endpoint config, the repo id comes from the environment with no in-code default.
"""

import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import RepositoryNotFoundError

import creator
from art import IMAGE_EXTS

load_dotenv()
REPO = os.getenv("RTR_COMMUNITY_REPO")  # the dataset id, e.g. "<owner>/rtr-community"

SPEC_FILE = "scenario.txt"
SCENE_FILES = tuple(f"scene{ext}" for ext in IMAGE_EXTS)


@dataclass
class Entry:
    folder: str
    spec: creator.ScenarioSpec
    image: str  # local path to the downloaded picture; "" when the entry has none


def _repo():
    if not REPO:
        raise RuntimeError(
            "RTR_COMMUNITY_REPO is not set — point it at the community dataset repo"
        )
    return REPO


def group_files(files):
    """Repo paths grouped into entry folders: {folder: [filename, ...]}. Root files and
    deeper nesting aren't ours — ignored."""
    folders = {}
    for f in files:
        folder, _, name = f.partition("/")
        if name and "/" not in name:
            folders.setdefault(folder, []).append(name)
    return folders


def _fetch(path):
    """One repo file as a local path (hub-cached, so refreshes only re-download changes)."""
    return hf_hub_download(_repo(), path, repo_type="dataset")


def entries():
    """Every playable community entry, newest first. Folders without a valid spec are
    skipped — submissions are open, so junk can land in the dataset."""
    try:
        files = HfApi().list_repo_files(_repo(), repo_type="dataset")
    except RepositoryNotFoundError:  # nobody has shared yet — created on first publish
        return []
    out = []
    for folder, names in sorted(group_files(files).items(), reverse=True):
        if SPEC_FILE not in names:
            continue
        try:
            spec = creator.load_spec(_fetch(f"{folder}/{SPEC_FILE}"))
        except Exception:  # junk upload — skip the entry, keep the gallery alive
            continue
        scene = next((n for n in names if n in SCENE_FILES), None)
        out.append(Entry(folder, spec, _fetch(f"{folder}/{scene}") if scene else ""))
    return out


def publish(spec, image_path):
    """Push one scenario (+ optional picture) as a fresh entry; the first publish ever
    creates the dataset repo."""
    folder = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    tmp = Path(tempfile.mkdtemp())
    (tmp / SPEC_FILE).write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    if image_path:
        ext = Path(image_path).suffix.lower()
        if ext not in IMAGE_EXTS:
            raise ValueError(f"picture must be one of: {', '.join(IMAGE_EXTS)}")
        shutil.copy(image_path, tmp / f"scene{ext}")
    api = HfApi()
    api.create_repo(_repo(), repo_type="dataset", exist_ok=True)
    api.upload_folder(
        folder_path=tmp, path_in_repo=folder, repo_id=_repo(), repo_type="dataset"
    )
    return folder


def to_scenario(entry):
    """A community entry as a live Scenario, its picture riding along as the backdrop."""
    scen = creator.spec_to_scenario(entry.spec)
    scen.scene = entry.image
    return scen
