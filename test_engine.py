"""Deterministic unit tests for the engine's non-LLM decision points.

These touch no model: they pin the pure plumbing the LLM tests sit on top of —
the player-POV rewrite, the transcript renderer, and the turn-taking picker.
Each test fixes one input and asserts the one thing that must happen, every time.

  uv run pytest test_engine.py
"""

import engine
from engine import (
    Event,
    new_game,
    pick_speakers,
    render_window,
    rewind_to,
    to_model_pov,
)
from scenarios.format import Character, Scenario


def make_scen(*chars):
    return Scenario(
        id="t",
        title="t",
        intro="",
        goal="",
        characters=list(chars),
        max_turns=5,
        verdict_labels=["W", "L"],
    )


def make_char(name):
    return Character(name=name, persona="", disposition={})


# ----- to_model_pov: second-person 'you' (the player) -> third person -----


def test_bare_you_becomes_they():
    assert to_model_pov("Will you let me go?") == "Will they let me go?"


def test_leading_capital_is_preserved():
    assert to_model_pov("You are doomed.") == "They are doomed."


def test_verb_agreement_holds_without_conjugation():
    # the whole point of 'they': second-person verbs stay correct, no re-conjugation
    assert to_model_pov("You have no weapon.") == "They have no weapon."


def test_contraction_beats_bare_you():
    # 'you're' must be rewritten as a unit, not as 'you' + 're'
    assert to_model_pov("You're brave.") == "They're brave."
    assert to_model_pov("You've earned this.") == "They've earned this."


def test_possessive_your_is_not_swallowed_by_bare_you():
    assert to_model_pov("Drop your sword.") == "Drop their sword."
    assert to_model_pov("The choice is yours.") == "The choice is theirs."


def test_reflexive_yourself():
    assert to_model_pov("Defend yourself.") == "Defend themselves."


def test_word_boundary_leaves_lookalikes_alone():
    # 'you' is a substring of 'young' but not a whole word there
    assert to_model_pov("The young warrior waits.") == "The young warrior waits."


# ----- render_window: log events -> transcript text -----


def test_player_event_is_labelled():
    assert render_window([Event("player", "", "hello")]) == "PLAYER: hello"


def test_line_event_uses_speaker_name():
    assert (
        render_window([Event("line", "Warden", "Gate's closed.")])
        == "Warden: Gate's closed."
    )


def test_beat_event_is_bare_text():
    assert (
        render_window([Event("beat", "", "The hall falls silent.")])
        == "The hall falls silent."
    )


def test_events_join_with_newlines_in_order():
    events = [
        Event("beat", "", "The gate looms."),
        Event("player", "", "Let me pass."),
        Event("line", "Warden", "No."),
    ]
    assert render_window(events) == "The gate looms.\nPLAYER: Let me pass.\nWarden: No."


# ----- pick_speakers: who reacts this turn -----


def pick_first(seq, weights):
    return [seq[0]]


def test_single_character_room_always_returns_the_one():
    a = make_char("Solo")
    game = new_game(make_scen(a))
    # even with a name match impossible and randomness irrelevant, it's always [a]
    assert pick_speakers(game, "anything at all") == [a]


def test_named_character_speaks(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 1.0)  # suppress interjections
    assert pick_speakers(game, "Warden, open up.") == [a]


def test_only_named_characters_when_interjection_suppressed(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 1.0)
    assert pick_speakers(game, "Scribe and Warden, hear me.") == [a, b]


def test_interjection_appends_the_others(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)  # force interjection
    speakers = pick_speakers(game, "Warden, open up.")
    assert speakers[0] is a
    assert b in speakers and len(speakers) == 2


def test_name_inside_a_word_does_not_match(monkeypatch):
    # "Ann" must not be summoned by "cannot" — whole-word matches only
    a, b = make_char("Ann"), make_char("Bo")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 1.0)  # suppress interjections
    monkeypatch.setattr(engine.random, "choices", lambda seq, weights: [seq[1]])
    assert pick_speakers(game, "I cannot say.") == [b]


def test_name_match_is_case_insensitive(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 1.0)
    assert pick_speakers(game, "open up, WARDEN.") == [a]


def test_no_name_guarantees_one_speaker(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    monkeypatch.setattr(engine.random, "random", lambda: 1.0)  # every roll fails
    monkeypatch.setattr(engine.random, "choices", pick_first)
    assert pick_speakers(game, "Hello, anyone there?") == [a]


def test_guaranteed_pick_is_staleness_weighted(monkeypatch):
    a, b = make_char("Warden"), make_char("Scribe")
    game = new_game(make_scen(a, b))
    game.log += [Event("line", "Warden", "x"), Event("player", "", "y")]
    game.chars["Warden"].last_spoke_at = 1  # just spoke; Scribe silent since the intro
    seen = {}

    def spy_choices(seq, weights):
        seen.update(zip([c.name for c in seq], weights))
        return [seq[0]]

    monkeypatch.setattr(engine.random, "random", lambda: 1.0)
    monkeypatch.setattr(engine.random, "choices", spy_choices)
    pick_speakers(game, "Hello, anyone there?")
    assert seen["Scribe"] > seen["Warden"]


def test_rolled_speakers_capped_at_the_stalest_three(monkeypatch):
    cast = [make_char(f"C{i}") for i in range(5)]
    game = new_game(make_scen(*cast))
    game.log += [Event("player", "", "x")] * 4
    for i, c in enumerate(cast):
        game.chars[c.name].last_spoke_at = i  # C0 longest silent … C4 freshest
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)  # everyone rolls in
    # the cap keeps the three stalest and drops the freshest, in cast order
    assert pick_speakers(game, "no names here") == cast[:3]


def test_named_characters_are_exempt_from_the_cap(monkeypatch):
    cast = [make_char(n) for n in ("Ada", "Ben", "Cy", "Dot")]
    game = new_game(make_scen(*cast))
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)
    speakers = pick_speakers(game, "Ada, Ben, Cy, Dot — all of you, listen.")
    assert speakers == cast  # all four named: every one speaks, no dice slots left


# ----- rewind: snapshots, restoring an earlier point -----


def play_fake_turn(game, directive, line, scene):
    """Mirror the turn-start bookkeeping play_turn_stream does, without any model:
    snapshot, record the player and a reply, then advance the objective scene and clock."""
    game.snapshots = game.snapshots[: game.turn]
    game.snapshots.append(engine._snapshot(game))
    game.log.append(Event("player", "", directive))
    name = next(iter(game.chars))
    game.log.append(Event("line", name, line))
    game.chars[name].disposition = {"Player": f"reacts to: {directive}"}
    game.scene = scene
    game.log.append(Event("beat", "", scene))
    game.turn += 1


def two_turn_game():
    scen = make_scen(make_char("Warden"))
    game = new_game(scen)
    play_fake_turn(game, "Let me pass.", "No.", "The gate stays shut.")
    play_fake_turn(game, "I have gold.", "Show me.", "The Warden eyes the purse.")
    return game


def test_rewind_returns_the_original_directive():
    assert rewind_to(two_turn_game(), 1) == "I have gold."


def test_rewind_restores_scene_disposition_and_clock():
    game = two_turn_game()
    rewind_to(game, 1)
    # back to the start of turn 1: turn 0 stands, turn 1 and after are gone
    assert game.turn == 1
    assert game.scene == "The gate stays shut."
    assert game.chars["Warden"].disposition == {"Player": "reacts to: Let me pass."}
    assert [e.text for e in game.log if e.kind == "player"] == ["Let me pass."]


def test_rewind_to_first_turn_clears_to_opening():
    game = two_turn_game()
    rewind_to(game, 0)
    assert game.turn == 0
    assert game.scene == new_game(game.scenario).scene
    assert [e for e in game.log if e.kind == "player"] == []
    assert game.snapshots == []


def test_replaying_after_rewind_overwrites_the_abandoned_future():
    game = two_turn_game()
    rewind_to(game, 1)
    play_fake_turn(game, "I bring a warning.", "Speak.", "The Warden leans in.")
    assert [e.text for e in game.log if e.kind == "player"] == [
        "Let me pass.",
        "I bring a warning.",
    ]
    assert len(game.snapshots) == 2
