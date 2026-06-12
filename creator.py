"""Promptable scenario authoring: `author` runs one model call that fills a `ScenarioSpec`
(the same shape the hand-written scenarios have). The creator view edits the spec as a
form — or starts from a blank template — and it round-trips through JSON only for
saving to a shareable .txt, before it becomes a live `Scenario`. The fairness rules live
in the shared STAGE_RULES (scenarios/format.py), so the author invents only the cast and
the situation, never the glue.
"""

import tempfile
import uuid
from pathlib import Path

import dspy
from pydantic import BaseModel, Field

import dispositions
import engine
from scenarios.format import Character, Scenario


DEFAULT_LABELS = ["WON", "LOST"]
MIN_TURNS = 3  # fewer turns than this and the social arc has no room to develop


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
    and a hidden driver advances the scene. The engine supplies the fairness glue that keeps
    the game hard-but-winnable; you supply the cast and the situation. Write it so a
    perceptive player who finds each character's lever wins.

    Decide `cast` FIRST: exactly `num_characters` distinct names, the full roster. Then write
    one character per name, each a sharply different person with their OWN lever — what
    genuinely moves them, and what hardens them. Open each persona by stating plainly who this
    character is to the player and to every other character — names, roles, and the pronouns
    that go with them — so every relationship reads the same from every chair. Each
    `disposition` is an object (a row of the room's relationship matrix) with one short clause
    per key: "Player" (their opening stance toward the player), the character's OWN name (how
    they feel right now — their mood), and EACH other character by name (what they think of
    them). Every disposition carries ALL `num_characters` + 1 keys: "Player" plus every name
    in `cast`, first through last.

    `intro` is present tense and addresses the player directly as "you": a few tight sentences
    of pure setup that put the player in the room, name the stakes, and end where the player's
    first words begin. `goal` is a concrete win condition the room visibly grants once the
    player earns it. `max_turns` gives the player room to work: at least 3, typically 5-8."""

    idea: str = dspy.InputField(
        desc="the player's one- or two-line premise for the scenario"
    )
    num_characters: int = dspy.InputField(
        desc="how many characters must be in the room"
    )
    # committed first so every disposition row can reference the whole roster, including
    # names the spec hasn't introduced yet — without this the last character is omitted
    cast: list[str] = dspy.OutputField(
        desc="the full roster: every character's name, decided before anything else"
    )
    spec: ScenarioSpec = dspy.OutputField(desc="the complete, ready-to-play scenario")


class DispositionCell(BaseModel):
    character: str = ""  # whose row
    toward: str = ""  # the key: "Player", another name, or their own (their mood)
    stance: str = ""  # one short clause


class FillDispositions(dspy.Signature):
    """Write the missing cells of a scenario's disposition matrix, in keeping with each
    character's persona and the premise. Each cell is one character's stance toward one
    party: toward "Player" (the player), toward another character by name, or toward their
    OWN name (how they feel right now — their mood). One short clause per cell; write
    exactly the requested cells."""

    spec: ScenarioSpec = dspy.InputField(desc="the scenario authored so far")
    missing: list[str] = dspy.InputField(
        desc="the cells to write, each 'character -> toward'"
    )
    cells: list[DispositionCell] = dspy.OutputField(
        desc="one filled cell per missing entry"
    )


# higher ceiling than a play turn: a full scenario with several personas is a long answer
AUTHOR_LM = engine.make_lm(0.8, max_tokens=3000)


def missing_cells(spec):
    """Every (character, toward) disposition cell with no clause — small authoring models
    drop some even when told not to, typically the roster's last name."""
    keys = dispositions.row_keys(spec)
    return [
        (c.name, k)
        for c in spec.characters
        for k in keys
        if not (c.disposition.get(k) or "").strip()
    ]


def repair_dispositions(spec):
    """One follow-up call that writes just the missing disposition cells. Best-effort: a
    failed call or an unanswered cell simply stays blank and editable in the creator."""
    gaps = missing_cells(spec)
    if not gaps:
        return spec
    try:
        cells = dspy.Predict(FillDispositions)(
            spec=spec, missing=[f"{c} -> {k}" for c, k in gaps]
        ).cells
    except (
        Exception
    ):  # malformed model output — leave the gaps rather than fail authoring
        return spec
    wanted = set(gaps)
    rows = {c.name: c for c in spec.characters}
    for cell in cells:
        if (cell.character, cell.toward) in wanted and cell.stance:
            rows[cell.character].disposition[cell.toward] = cell.stance
    return spec


def author(idea, num_characters):
    """Idea + headcount -> a full ScenarioSpec: one authoring call, plus one repair call
    when disposition cells come back missing."""
    with dspy.context(lm=AUTHOR_LM):
        spec = dspy.Predict(AuthorScenario)(
            idea=idea, num_characters=num_characters
        ).spec
        return repair_dispositions(spec)


# the one wording every loader shows when load_spec raises
LOAD_ERROR = "Couldn't load that scenario"


def load_spec(path):
    """A saved scenario file back as a spec — the one parse boundary every loader shares.
    Raises on anything that doesn't hold a valid spec."""
    return ScenarioSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_spec(spec):
    """The spec serialized to a shareable .txt (the spec JSON); returns the file's path."""
    out = Path(tempfile.mkdtemp()) / "scenario.txt"
    out.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return str(out)


def verdict_pair(spec):
    """The spec's verdict labels normalized to exactly [win, lose]: defaulted when empty,
    a single label standing for both."""
    labels = spec.verdict_labels or list(DEFAULT_LABELS)
    return [labels[0], labels[-1]]


def blank_spec(num_characters):
    names = [f"Character {i + 1}" for i in range(num_characters)]
    keys = dispositions.party_keys(
        names
    )  # show the matrix shape: a cell per party, incl. self
    return ScenarioSpec(
        characters=[
            CharSpec(name=n, disposition=dict.fromkeys(keys, "")) for n in names
        ]
    )


def spec_to_scenario(spec):
    """Build a live Scenario from an authored/edited spec."""
    if not spec.characters:
        raise ValueError("a scenario needs at least one character")
    if spec.max_turns < MIN_TURNS:
        raise ValueError(f"a game lasts at least {MIN_TURNS} turns")
    labels = verdict_pair(spec)
    # normalize every disposition to the canonical row (Player + each name, incl. self), so an
    # author/edited spec that filled only some cells still loads with a complete, gap-free matrix.
    keys = dispositions.row_keys(spec)
    chars = [
        Character(
            name=c.name,
            persona=c.persona,
            disposition=dispositions.merge_row({}, c.disposition, keys),
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
    )
