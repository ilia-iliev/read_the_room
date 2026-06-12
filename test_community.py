"""Deterministic unit tests for the community hub's non-network decision points: how repo
paths group into entries, what publish refuses, and how a travelling picture wins the
backdrop. Nothing here touches the Hub.

  uv run pytest test_community.py
"""

import pytest

import art
import community
import communityview
import creator
from scenarios.format import Character, Scenario


# ----- group_files: repo paths -> entry folders -----


def test_groups_by_top_folder():
    files = ["a/scenario.txt", "a/scene.jpg", "b/scenario.txt"]
    assert community.group_files(files) == {
        "a": ["scenario.txt", "scene.jpg"],
        "b": ["scenario.txt"],
    }


def test_ignores_root_files_and_deep_nesting():
    files = ["README.md", ".gitattributes", "a/deep/scene.jpg", "a/scenario.txt"]
    assert community.group_files(files) == {"a": ["scenario.txt"]}


# ----- publish: input checks before anything leaves the machine -----


def test_publish_rejects_unknown_image_type(tmp_path):
    bad = tmp_path / "scene.bmp"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError, match="picture"):
        community.publish(creator.blank_spec(1), str(bad))


def test_repo_unset_fails_loudly(monkeypatch):
    monkeypatch.setattr(community, "REPO", None)
    with pytest.raises(RuntimeError, match="RTR_COMMUNITY_REPO"):
        community.entries()


# ----- the travelling picture -----


def make_scen(scene=""):
    return Scenario(
        id="t",
        title="t",
        intro="",
        goal="",
        characters=[Character(name="A", persona="", disposition={})],
        max_turns=5,
        verdict_labels=["W", "L"],
        scene=scene,
    )


def test_scene_uri_prefers_the_carried_picture(tmp_path):
    img = tmp_path / "scene.png"
    img.write_bytes(b"png-bytes")
    assert art.scene_uri(make_scen(str(img))).startswith("data:image/png;base64,")


def test_scene_uri_without_picture_or_assets_is_none():
    assert art.scene_uri(make_scen()) is None


def test_to_scenario_carries_the_entry_image():
    spec = creator.blank_spec(1)
    entry = community.Entry(folder="x", spec=spec, image="/tmp/scene.jpg")
    assert community.to_scenario(entry).scene == "/tmp/scene.jpg"


# ----- search: narrowing the shelf -----


def entry_with(**fields):
    spec = creator.blank_spec(1).model_copy(update=fields)
    return community.Entry(folder="x", spec=spec, image="")


def test_search_matches_title_intro_goal_and_names():
    entries = [
        entry_with(title="The Heist"),
        entry_with(intro="You walk into a heist gone wrong"),
        entry_with(goal="call off the heist"),
        entry_with(title="Dinner"),
    ]
    assert communityview.filter_entries(entries, "HEIST") == entries[:3]
    named = creator.blank_spec(1)
    named.characters[0].name = "Margot"
    assert communityview.matches(named, "margot")


def test_blank_query_keeps_everything():
    entries = [entry_with(title="A"), entry_with(title="B")]
    assert communityview.filter_entries(entries, "") == entries
    assert communityview.filter_entries(entries, "  ") == entries
    assert communityview.filter_entries(entries, None) == entries
