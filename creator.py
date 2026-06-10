"""Promptable scenario authoring: `author` runs one model call that fills a `ScenarioSpec`
(the same shape the hand-written scenarios have). The spec round-trips through JSON so the
player can edit any field — or start from a blank template — before it becomes a live
`Scenario`. The fairness rules live in the shared STAGE_RULES (scenarios/format.py), so
the author invents only the cast and the situation, never the glue.
"""

import uuid

import dspy
from pydantic import BaseModel, Field

import engine
from art import slug
from scenarios.format import Character, Scenario


DEFAULT_LABELS = ["WON", "LOST"]


class CharSpec(BaseModel):
    name: str = ""  # the room shows the avatar as the initial of this name
    persona: str = ""  # who they are, their voice, their standing agenda (2nd person)
    # the opening disposition ROW: keyed by "Player", this character's OWN name (its current
    # mood — the self/diagonal entry), and each other character's name. One clause per key.
    disposition: dict[str, str] = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    """The editable shape of a scenario. Non-essential fields default so a partial or
    hand-started spec still loads."""

    title: str = ""
    intro: str = ""  # second-person premise/scene the player answers (the setup card)
    goal: str = ""  # the win condition, in plain words
    max_turns: int = 5
    verdict_labels: list[str] = Field(default_factory=lambda: list(DEFAULT_LABELS))
    characters: list[CharSpec] = Field(default_factory=list)


class AuthorScenario(dspy.Signature):
    """Author a complete, genuinely WINNABLE social-standoff scenario from a short idea.

    The game: a player talks their way through a room of `num_characters` distinct minds to
    reach a goal. Each turn the player speaks, one or two characters react in their own voice,
    and a hidden driver advances the scene. The engine already enforces the fairness rules that
    keep the game hard-but-winnable, so you invent ONLY the cast and the situation — never the
    glue. The scenario MUST be winnable by a perceptive player who finds each character's lever.

    Write EXACTLY `num_characters` characters, each a sharply different person with a DIFFERENT
    lever — what genuinely moves them, and what hardens them. Each `disposition` is an object
    (a row of the room's relationship matrix) with one short clause per key: "Player" (their
    opening stance toward the player), the character's OWN name (how they feel right now — their
    mood), and EACH other character by name (what they think of them). Fill every key.

    `intro` is present tense and addresses the player directly as "you" — it sets the scene and
    the room's challenge, the premise the player answers, no long quoted dialogue. `goal` is a
    concrete win condition (actually achieved, not merely being tolerated or praised)."""

    idea: str = dspy.InputField(
        desc="the player's one- or two-line premise for the scenario"
    )
    num_characters: int = dspy.InputField(
        desc="how many characters must be in the room"
    )
    spec: ScenarioSpec = dspy.OutputField(desc="the complete, ready-to-play scenario")


# higher ceiling than a play turn: a full scenario with several personas is a long answer
AUTHOR_LM = engine.make_lm(0.8, max_tokens=3000)


def author(idea, num_characters):
    """One model call: idea + headcount -> a full ScenarioSpec."""
    with dspy.context(lm=AUTHOR_LM):
        return dspy.Predict(AuthorScenario)(
            idea=idea, num_characters=num_characters
        ).spec


def to_json(spec):
    return spec.model_dump_json(indent=2)


def blank_json(num_characters):
    names = [f"Character {i + 1}" for i in range(num_characters)]
    keys = ["Player", *names]  # show the matrix shape: a cell per party, incl. self
    spec = ScenarioSpec(
        characters=[
            CharSpec(name=n, disposition=dict.fromkeys(keys, "")) for n in names
        ]
    )
    return to_json(spec)


def spec_to_scenario(spec, art=None):
    """Build a live Scenario. `art` is the creator UI's mapping of 'scene' and character
    slugs to uploaded image filepaths; matching entries become inline art on the objects so
    an authored scenario shows its own pictures (absent -> the usual placeholders)."""
    if not spec.characters:
        raise ValueError("a scenario needs at least one character")
    art = art or {}
    labels = spec.verdict_labels or list(DEFAULT_LABELS)
    if len(labels) < 2:
        labels = [labels[0], labels[0]]
    # normalize every disposition to the canonical row (Player + each name, incl. self), so an
    # author/edited spec that filled only some cells still loads with a complete, gap-free matrix.
    keys = engine.row_keys(spec)
    chars = [
        Character(
            name=c.name,
            persona=c.persona,
            disposition=engine.merge_row({}, c.disposition, keys),
            avatar=art.get(slug(c.name), ""),
        )
        for c in spec.characters
    ]
    return Scenario(
        id=uuid.uuid4().hex,  # unique per build so replaying a tweaked spec re-renders
        title=spec.title or "Custom scenario",
        intro=spec.intro,
        goal=spec.goal,
        characters=chars,
        max_turns=spec.max_turns,
        verdict_labels=labels,
        scene_image=art.get("scene", ""),
    )


def scenario_from_json(text, art=None):
    return spec_to_scenario(ScenarioSpec.model_validate_json(text), art)


def cast_names(text):
    """The character names in a spec JSON — used to lay out one art uploader per character."""
    return [c.name for c in ScenarioSpec.model_validate_json(text).characters]
