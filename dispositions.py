"""The disposition matrix: per-character rows of free-text stances, keyed by "Player" and
by every character name (a character's own name is its self/diagonal entry). This module
owns the row vocabulary — the canonical keys, the closed schema the model fills, the
no-deletion merge, and the renderings fed back into prompts. The turn loop that threads
the rows lives in engine.py.
"""

from pydantic import ConfigDict, Field, create_model


def party_keys(names):
    """The canonical disposition keys a row carries, in canonical order: the player first,
    then every character name (a character's own name is its self/diagonal entry)."""
    return ["Player", *names]


def row_keys(scen):
    """party_keys over a scenario's (or spec's) cast."""
    return party_keys([c.name for c in scen.characters])


def disposition_model(keys):
    """The disposition row as a closed pydantic schema, fixed the moment the game starts: one
    string slot per canonical key. The model fills slots — it cannot invent, rename, or drop
    keys. A skipped slot defaults to '' (merge_row falls back to the prior value) rather than
    failing the turn. Field names are positional placeholders; the alias carries the real
    name — any spelling a creator typed, spaces and punctuation included — into the JSON
    schema the model sees."""
    fields = {
        f"slot{i}": (
            str,
            Field(
                "",
                alias=key,
                description=(
                    "how you now regard the player"
                    if key == "Player"
                    else f"how you now regard {key} — or, if {key} is you, how you feel right now"
                ),
            ),
        )
        for i, key in enumerate(keys)
    }
    return create_model(
        "Dispositions", __config__=ConfigDict(populate_by_name=True), **fields
    )


def merge_row(prior, update, keys):
    """A refreshed row over exactly `keys`: take each cell from `update` — a plain dict or the
    filled disposition_model a turn produced — but fall back to the prior value when the model
    left it blank or dropped it. Unknown keys are discarded. This is the no-deletion
    guarantee — a party can never vanish from a character's stance."""
    if hasattr(update, "model_dump"):
        update = update.model_dump(by_alias=True)
    update = update or {}
    prior = prior or {}
    return {k: (str(update.get(k) or "").strip() or prior.get(k, "")) for k in keys}


def render_row(name, row, keys):
    """Render character `name`'s row as the labelled stance text fed into its own turn: how it
    regards the player, itself right now (the self/diagonal cell), and each other character."""
    lines = [f"Toward the player: {row.get('Player', '')}"]
    lines.append(f"Yourself right now: {row.get(name, '')}")
    lines += [
        f"Toward {k}: {row.get(k, '')}" for k in keys if k not in ("Player", name)
    ]
    return "\n".join(lines)


def _cell(prior, new, key):
    """One room cell: `<prior>  →  <new>` if it moved this turn, else just `<new>`."""
    b = new.get(key, "")
    a = (prior or {}).get(key)
    return f"{a}  →  {b}" if a is not None and a != b else b


def render_room(scen, moved, chars):
    """The `room` block for the driver/referee/finale: one line per character with its stance
    toward the player and each OTHER character, arrows on the cells that moved this turn. `moved`
    maps name -> the character's prior row for those that spoke. Self is omitted — internal only."""
    lines = []
    for c in scen.characters:
        row = chars[c.name].disposition
        prior = moved.get(c.name)
        cells = [f"Player: {_cell(prior, row, 'Player')}"]
        cells += [
            f"{o.name}: {_cell(prior, row, o.name)}"
            for o in scen.characters
            if o.name != c.name
        ]
        lines.append(f"{c.name} — " + "; ".join(cells))
    return "\n".join(lines)
