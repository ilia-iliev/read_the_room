"""The dspy signatures: the prompt contract for every model call the engine makes.

CharacterTurn voices one mind in the room. The Referee is the sole judge of the verdict.
The SituationDriver advances the scene when the game continues; the Finale narrates the
ending the referee already settled. Pure prompt definitions — no runtime logic; the turn
loop that drives them lives in engine.py.
"""

import dspy


class CharacterTurn(dspy.Signature):
    persona: str = dspy.InputField(desc="who you are")
    disposition: str = dspy.InputField(
        desc="how you CURRENTLY regard the player, yourself, and each other character — act on this"
    )
    scene: str = dspy.InputField(desc="the objective situation in the room right now")
    since_you_spoke: str = dspy.InputField(
        desc="what was said and done since you last spoke"
    )
    reasoning: str = dspy.OutputField(
        desc="In character, private thoughts. 1-2 punchy sentences of your thoughts on "
        "what happened since you last spoke"
    )
    line: str = dspy.OutputField(
        desc="what you say and/or do now. In your own distinct voice, present tense"
    )
    updated_dispositions: dict[str, str] = dspy.OutputField(
        desc="your REFRESHED stance after speaking, reflecting all of `since_you_spoke`. A JSON "
        "object with one short clause per key: 'Player' (the player), your OWN name (how you "
        "feel right now), and EACH other character by their name. Include every key."
    )


_ROOM_DESC = (
    "where each character now stands, one line each: `Name — Player: <stance>; Other: "
    "<stance>; …` — their stance toward the player and toward every OTHER character. A cell "
    "that moved THIS turn shows it as `<prior>  →  <new>`, the net effect of the player's "
    "recent moves; a cell with no arrow is unchanged since that character last spoke."
)


class SituationDriver(dspy.Signature):
    """Advance the scene only — the referee has already ruled this turn ongoing. Never judge
    the outcome and never narrate an ending; just move the story forward one beat."""

    goal: str = dspy.InputField(desc="what the player is trying to achieve")
    scene: str = dspy.InputField(desc="the situation at the start of this turn")
    this_turn: str = dspy.InputField(
        desc="the player's words and the subsequent social dynamic"
    )
    room: str = dspy.InputField(desc=_ROOM_DESC)
    current_scene: str = dspy.OutputField(
        desc="the room as it now stands — a terse status summary of where everyone is, the mood, "
        "and what hangs unresolved. A snapshot to orient the next beat, NOT prose narration."
    )
    next_scene: str = dspy.OutputField(
        desc="what happens next as a result of this turn, present tense, NO quoted dialogue. Narrate "
        "objective events in the room; never address the player or tell them what they 'must' do. "
        "Present the next beat for the player to answer."
    )


class Referee(dspy.Signature):
    """The sole judge of the verdict. Rule won/lost/ongoing from where the room actually stands —
    you do not narrate, you only call it."""

    goal: str = dspy.InputField(desc="what the player is trying to achieve")
    situation: str = dspy.InputField(
        desc="the objective scene at the START of this turn — where everyone stood before the "
        "player's latest move"
    )
    this_turn: str = dspy.InputField(
        desc="the player's latest words and how the room reacted to them this turn"
    )
    room: str = dspy.InputField(desc=_ROOM_DESC)
    player_so_far: str = dspy.InputField(
        desc="everything the player said BEFORE this turn, in order — their trajectory"
    )
    final_turn: bool = dspy.InputField(
        desc="True if this is the last turn allowed. You MUST commit 'won' or 'lost', never 'ongoing'."
    )
    reasoning: str = dspy.OutputField(
        desc="one-two sentence:s where the player now stands relative to the goal, and which way the "
        "room moved this turn"
    )
    outcome: str = dspy.OutputField(
        desc="'won' if the player has genuinely achieved the `goal`. This involves on-point persuasion, leverage, or turning "
        "characters against each other in a way that serves the goal. \n"
        "'lost' if the room is against the player or his trajectory shows stalling, repeating, ignoring a scene, or cheating. \n"
        "'ongoing' otherwise - for example if the player is making progress or regress but still has a way to go.\n"
        "FINAL TURN - commit to a decision considering the current situation: 'won' or 'lost' only."
    )


class Finale(dspy.Signature):
    """Narrate the ending the referee already settled. You do not decide the verdict — you render it."""

    goal: str = dspy.InputField(desc="what the player was trying to achieve")
    transcript: str = dspy.InputField(desc="the whole encounter, start to finish")
    room: str = dspy.InputField(
        desc="where each character finally stands toward the player"
    )
    outcome: str = dspy.InputField(
        desc="the verdict already settled by the referee: 'won' or 'lost'"
    )
    closing: str = dspy.OutputField(
        desc="the final scene, present tense, NO quoted dialogue. If 'won', narrate the player "
        "achieving the goal — they get what they came for. If 'lost', narrate how it ends against "
        "them. Resolve it decisively; never address the player."
    )
