"""DSPy engine: a room of characters the player talks through.

Each turn: the player speaks; one or two characters react in their own voice (acting on
their current disposition, then refreshing it); the referee — sole arbiter — rules the turn
won, lost, or ongoing. If the game continues, the situation driver advances the scene; if
it resolved, the finale narrates the ending the referee settled. Characters are pure
reactors; only the driver writes the shared scene state.
"""

import copy
import random
import re
from dataclasses import dataclass, field

import dspy

from signatures import CharacterTurn, Finale, Referee, SituationDriver

MODEL = "openai/Qwen3.6-27B"
API_BASE = "http://localhost:8081/v1"
# Qwen3.6 is a reasoning model; this toggle stops it burning the budget on hidden
# thinking and returning empty content.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


def make_lm(temperature, max_tokens=1500, cache=True):
    return dspy.LM(
        MODEL,
        api_base=API_BASE,
        api_key="not-needed",
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=NO_THINK,
        cache=cache,
    )


PLAY_TEMP = 0.7  # creative enough for twists, low enough to obey the concede rule
# Cache OFF for live play: each turn's prompt is unique (the transcript grows), so caching never
# helps going forward — but it WOULD make a rewind/regenerate echo the cached original instead of
# reacting anew. Off, a replayed line genuinely regenerates. (evaluate.py sets its own LM + cache.)
dspy.configure(lm=make_lm(PLAY_TEMP, cache=False))


# each character not already speaking interjects independently with this chance, so a
# bigger cast yields more voices per turn (expected speakers, none named: 1 + 0.4·(n-1))
INTERJECT_CHANCE = 0.4
# bound on voices per turn: each speaker is a full streamed model call, so an uncapped big
# cast would drag the turn. Characters the player named are exempt — they were asked for.
MAX_SPEAKERS_TO_SAMPLE = 3


# ----- runtime state -----


@dataclass
class Event:
    """One beat of the transcript, in order."""

    kind: str  # "beat" (scene/driver) | "player" | "line" (a character)
    who: str  # character name for "line"; "" otherwise
    text: str
    reasoning: str = ""  # private read, for "line" events only


@dataclass
class CharState:
    disposition: dict  # the live disposition ROW: "Player"/own-name(self)/each other name -> clause
    last_spoke_at: (
        int  # index in the log of this character's last "line" (or the intro)
    )


@dataclass
class Game:
    scenario: object
    scene: str  # objective scene state (driver-owned)
    chars: dict  # character id -> CharState
    log: list = field(default_factory=list)
    trace: list = field(
        default_factory=list
    )  # raw LM input+output per call, for debug export
    snapshots: list = field(
        default_factory=list
    )  # frozen turn-start state, one per turn played, for rewind
    turn: int = 0
    concluded: bool = False
    outcome: str = "ongoing"  # set by the driver: "ongoing" | "won" | "lost"

    @property
    def active(self):
        return not self.concluded and self.turn < self.scenario.max_turns


# The intro addresses the player as "you" so the setup card reads in second person. The model
# channel can't use "you" — it collides with each persona's own "You are <name>". We rewrite the
# player to singular "they": unlike "the player", it shares every verb form with "you", so the
# swap needs no re-conjugation ("you have" -> "they have", not "the player has"). Runs ONLY when
# seeding the engine (game.scene and log[0]), never on the card copy. Contractions and possessives
# come first so the bare "you" rule can't pre-empt them.
_PLAYER_POV = [
    ("yourselves", "themselves"),
    ("yourself", "themselves"),
    ("you're", "they're"),
    ("you've", "they've"),
    ("you'll", "they'll"),
    ("you'd", "they'd"),
    ("yours", "theirs"),
    ("your", "their"),
    ("you", "they"),
]


def to_model_pov(text):
    """Rewrite an intro's second-person 'you' (the player) into singular 'they' for model prompts."""
    for word, replacement in _PLAYER_POV:
        text = re.sub(
            rf"\b{word}\b",
            lambda m, r=replacement: (
                r[0].upper() + r[1:] if m.group()[0].isupper() else r
            ),
            text,
            flags=re.IGNORECASE,
        )
    return text


def norm_label(text):
    """Normalize a model-emitted label for comparison: lowercased, trailing period stripped."""
    return text.strip().lower().rstrip(".")


def row_keys(scen):
    """The canonical disposition keys every character's row carries: the player plus every
    character name (a character's own name is its self/diagonal entry)."""
    return ["Player", *[c.name for c in scen.characters]]


def merge_row(prior, update, keys):
    """A refreshed row over exactly `keys`: take each cell from `update`, but fall back to the
    prior value when the model left it blank or dropped it. Unknown keys are discarded. This is
    the no-deletion guarantee — a party can never vanish from a character's stance."""
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


def new_game(scen):
    scene = to_model_pov(scen.intro)
    log = [Event("beat", "", scene)]
    keys = row_keys(scen)
    chars = {
        c.name: CharState(merge_row({}, c.disposition, keys), last_spoke_at=0)
        for c in scen.characters
    }
    return Game(scenario=scen, scene=scene, chars=chars, log=log)


# everything a turn mutates, save the constant scenario — what a snapshot must carry to restore
_RESTORABLE = ("scene", "chars", "log", "trace", "turn", "outcome", "concluded")


def _snapshot(game):
    """A deep, independent copy of the game's restorable state at this instant."""
    return {f: copy.deepcopy(getattr(game, f)) for f in _RESTORABLE}


def rewind_to(game, turn_no):
    """Restore `game` to the start of player turn `turn_no`, discarding that turn and everything
    after it, so the player can replay it with a different answer. Returns the directive they'd
    originally entered for that turn, for the UI to pre-fill."""
    snap = game.snapshots[turn_no]
    directive = game.log[
        len(snap["log"])
    ].text  # the player event recorded just after the snap
    for f in _RESTORABLE:
        setattr(game, f, copy.deepcopy(snap[f]))
    game.snapshots = game.snapshots[
        :turn_no
    ]  # the next play re-appends this turn's snapshot
    return directive


def render_window(events):
    """Render a slice of the log as plain transcript text for a model prompt."""
    out = []
    for e in events:
        if e.kind == "player":
            out.append(f"PLAYER: {e.text}")
        elif e.kind == "line":
            out.append(f"{e.who}: {e.text}")
        else:  # beat
            out.append(e.text)
    return "\n".join(out)


def trace_last_call(game, label):
    """Snapshot the most recent LM call's full input and output onto game.trace, for the
    debug export. Reads dspy's per-LM history, so it captures the real prompt and completion
    of whatever Predict/stream just ran — characters, driver, and finale alike."""
    history = getattr(dspy.settings.lm, "history", None) or []
    if not history:
        return
    e = history[-1]
    msgs = e.get("messages") or []
    inp = "\n\n".join(
        f"[{m.get('role', '?')}]\n{m.get('content', '')}" for m in msgs
    ) or str(e.get("prompt", ""))
    out = "\n".join(str(o) for o in (e.get("outputs") or []))
    game.trace.append(
        f"===== {label} =====\n--- INPUT ---\n{inp}\n\n--- OUTPUT ---\n{out}\n"
    )


def _staleness(game, char):
    """Log-distance since this character last spoke: the longer silent, the larger."""
    return len(game.log) - game.chars[char.name].last_spoke_at


def pick_speakers(game, directive):
    """Turn-taking: characters named in the directive always speak; every other character
    rolls an independent interjection, with at least one voice guaranteed. The dice favor
    the longest-silent — the guaranteed pick is staleness-weighted and the cap drops the
    freshest voices first — so nobody starves as the cast grows."""
    chars = game.scenario.characters
    if len(chars) == 1:
        return list(chars)
    named = [
        c
        for c in chars
        if re.search(rf"\b{re.escape(c.name)}\b", directive, re.IGNORECASE)
    ]
    others = [c for c in chars if c not in named]
    rolled = [c for c in others if random.random() < INTERJECT_CHANCE]
    if not named and not rolled:
        rolled = random.choices(others, weights=[_staleness(game, c) for c in others])
    quota = max(0, MAX_SPEAKERS_TO_SAMPLE - len(named))
    kept = sorted(rolled, key=lambda c: _staleness(game, c), reverse=True)[:quota]
    return named + [c for c in others if c in kept]


def _streamed(module, *fields):
    """A streamified Predict that surfaces the named output fields token-by-token as it writes."""
    return dspy.streamify(
        module,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name=f) for f in fields
        ],
    )


def _actor(scen):
    return _streamed(
        dspy.Predict(CharacterTurn.with_instructions(scen.stage_rules)),
        "reasoning",
        "line",
    )


async def _stream_beat(stream, field):
    """Drive a streamified single-field call, yielding the field's partial text as it grows.
    Each yield is (text, prediction): prediction is None while streaming and the final
    Prediction on the last yield."""
    text = ""
    async for chunk in stream:
        if (
            isinstance(chunk, dspy.streaming.StreamResponse)
            and chunk.signature_field_name == field
        ):
            text += chunk.chunk
            yield text, None
        elif isinstance(chunk, dspy.Prediction):
            yield text, chunk


async def _judge(stream):
    """Drive a streamified call that produces no live output, returning its final Prediction.
    For the referee: its verdict is internal, so nothing streams to the player."""
    result = None
    async for chunk in stream:
        if isinstance(chunk, dspy.Prediction):
            result = chunk
    return result


def _refresh_silent(game, moved, keys, label):
    """Every character that did NOT speak this turn (a dice roll, not a choice) reflects on
    events since it last spoke, refreshing its row without saying a line — so no stance the
    referee or finale reads is stale. Reuses CharacterTurn minus its `line` output: same
    field strings, one source. Skips anyone already in `moved`; safe to call twice a turn."""
    scen = game.scenario
    refresher = dspy.Predict(
        CharacterTurn.delete("line").with_instructions(scen.stage_rules)
    )
    for char in scen.characters:
        if char.name in moved:
            continue
        cs = game.chars[char.name]
        pred = refresher(
            persona=char.persona,
            disposition=render_row(char.name, cs.disposition, keys),
            scene=game.scene,
            since_you_spoke=render_window(game.log[cs.last_spoke_at + 1 :]),
        )
        moved[char.name] = cs.disposition  # A: stance before this reflection
        cs.disposition = merge_row(cs.disposition, pred.updated_dispositions, keys)
        trace_last_call(game, f"Disposition refresh · {char.name}  ({label})")


async def play_turn_stream(game, directive):
    """Mutates `game` in place; yields (current, concluded) as the cast speaks.
    `current` is the in-progress speaker's partial dict, or None between speakers —
    finished speakers are already committed to game.log, so the caller renders log +
    current. The final yield (after the driver runs) carries the updated scene/beat."""
    scen = game.scenario
    # freeze the turn-start state so the player can rewind here and try a different answer.
    # a prior rewind set game.turn back, so drop any snapshots it left from the abandoned future.
    game.snapshots = game.snapshots[: game.turn]
    game.snapshots.append(_snapshot(game))
    game.log.append(Event("player", "", directive))
    turn_start = len(game.log) - 1

    keys = row_keys(scen)
    moved = {}  # name -> prior disposition ROW (A), for characters that spoke this turn
    for char in pick_speakers(game, directive):
        cs = game.chars[char.name]
        window = render_window(game.log[cs.last_spoke_at + 1 :])
        cur = {"name": char.name, "reasoning": "", "line": ""}
        updated = {}
        async for chunk in _actor(scen)(
            persona=char.persona,
            disposition=render_row(char.name, cs.disposition, keys),
            scene=game.scene,
            since_you_spoke=window,
        ):
            if isinstance(chunk, dspy.streaming.StreamResponse):
                if chunk.signature_field_name == "reasoning":
                    cur["reasoning"] += chunk.chunk
                else:
                    cur["line"] += chunk.chunk
                yield cur, False
            elif isinstance(chunk, dspy.Prediction):
                cur["reasoning"], cur["line"] = chunk.reasoning, chunk.line
                updated = chunk.updated_dispositions
        game.log.append(Event("line", char.name, cur["line"], cur["reasoning"]))
        moved[char.name] = cs.disposition  # A: stance before this turn's refresh
        cs.disposition = merge_row(cs.disposition, updated, keys)
        cs.last_spoke_at = len(game.log) - 1
        trace_last_call(game, f"CharacterTurn · {char.name}  (turn {game.turn + 1})")
        yield None, False

    final_turn = game.turn + 1 >= scen.max_turns
    label = f"turn {game.turn + 1}"
    if final_turn:
        # the verdict is forced this turn: let the silent minds catch up first, so the
        # referee rules on no stale row
        _refresh_silent(game, moved, keys, label)

    this_turn = render_window(game.log[turn_start:])
    room = render_room(scen, moved, game.chars)
    prior = [e.text for e in game.log[:turn_start] if e.kind == "player"]
    player_so_far = (
        "\n".join(f"- {t}" for t in prior) or "(first move — nothing said yet)"
    )

    # the referee is the SOLE judge: it rules before anyone narrates, so a later beat can never
    # second-guess the verdict. On the final turn it must commit — no 'ongoing' past the clock.
    verdict = await _judge(
        dspy.streamify(dspy.Predict(Referee.with_instructions(scen.director_rules)))(
            goal=scen.goal,
            situation=game.scene,
            this_turn=this_turn,
            room=room,
            player_so_far=player_so_far,
            final_turn=final_turn,
        )
    )
    trace_last_call(game, f"Referee  ({label})")
    game.outcome = norm_label(verdict.outcome)
    if final_turn and game.outcome not in ("won", "lost"):
        game.outcome = "lost"  # the clock is spent and the referee did not commit
    game.concluded = game.outcome in ("won", "lost")
    game.turn += 1

    if not game.concluded:
        # the game continues: the driver advances the scene and writes the next beat
        driver = _streamed(
            dspy.Predict(SituationDriver.with_instructions(scen.director_rules)),
            "next_scene",
        )(goal=scen.goal, scene=game.scene, this_turn=this_turn, room=room)
        d = None
        async for text, pred in _stream_beat(driver, "next_scene"):
            if pred is not None:
                d = pred
            else:
                yield {"beat": text}, False
        trace_last_call(game, f"SituationDriver  ({label})")
        game.scene = d.current_scene
        if d.next_scene.strip():
            game.log.append(Event("beat", "", d.next_scene))
    else:
        # resolved early (the final-turn path already refreshed before the referee). Before the
        # finale renders "how every mind finally read you", the silent characters reflect on the
        # closing events, so no stance is stale.
        _refresh_silent(game, moved, keys, label)
        room = render_room(scen, moved, game.chars)

        # the finale NARRATES the verdict the referee settled; it no longer judges, so it can't
        # turn an earned win into a death.
        finale = _streamed(
            dspy.Predict(Finale.with_instructions(scen.director_rules)), "closing"
        )(
            goal=scen.goal,
            transcript=render_window(game.log),
            room=room,
            outcome=game.outcome,
        )
        f = None
        async for text, pred in _stream_beat(finale, "closing"):
            if pred is not None:
                f = pred
            else:
                yield {"beat": text}, False
        trace_last_call(game, f"Finale  ({label})")
        game.log.append(Event("beat", "", f.closing))
    yield None, game.concluded


def final_verdict(game):
    """Reads the outcome the referee already settled — early, or forced to won/lost when
    the clock runs out."""
    labels = game.scenario.verdict_labels
    return labels[0] if game.outcome == "won" else labels[-1]
