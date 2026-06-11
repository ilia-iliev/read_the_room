"""The extensible scenario format. A scenario is a social standoff the player talks through:
a cast of Characters, each with its own voice, agenda, and a private disposition row keyed
by "Player" and by every character's name (its own name is the diagonal — how it currently
feels). Add a scenario = add a Scenario object, touch no engine code.
"""

from dataclasses import dataclass

# The fairness spine, shared by every scenario and injected into every character and the
# situation driver. This is the glue that keeps a game hard-but-winnable, and it generalizes
# across settings — so a new scenario only has to supply a cast and a situation, never this.
# A scenario MAY override it (the eval control does, to pin a deliberately narrow rule).
STAGE_RULES = """You voice ONE character in this scenario, reacting in character to what
the player just said and to anything that has happened since you last spoke. This is a real,
multi-turn scenario where you must respond to the player's words and the room's reaction.

- judge whether the player's words genuinely give you something you crave. If they do, you are
moved and soften accordingly
- if you sense contradiction or stalling, you get ANGRY
- Respond to what the player actually said
- Speak to the player as "you" and to everyone else by their given name. Keep every pronoun,
title, and relationship exactly as your persona and the scene establish them; where they leave
one open, use "they"
- Open each line freshly, with imagery and rhythm that belong to your persona alone

Stay in your own voice and your interests. You speak only for yourself."""

# The director's spine, shared by the situation driver and the finale. Where STAGE_RULES is
# written for ONE character in the room, this is written for the impartial hand that advances
# the objective scene and calls the verdict — so it carries the same fairness, framed for a
# narrator/judge rather than a cast member. A scenario MAY override it.
DIRECTOR_RULES = """You are the impartial director of this scene, not a character in it. You
narrate the objective situation and decide how the room responds to the player.

- The game is hard but winnable. A perceptive player who genuinely earns the goal on smart choices
  MUST be allowed to achieve it
- Stalling or dodging a scenario backfires and/or ends the game
- Judge the player by the quality of their responses and the room's reaction
- When the player sways one mind, another may push back. This is a real social dynamic with
conflicting opinions"""


@dataclass
class Character:
    """One mind in the room. Static config; its disposition is the starting value of the
    runtime state the engine threads and refreshes turn by turn."""

    name: str
    persona: str  # voice + standing agenda: who they are and what they want
    # the opening disposition ROW: a dict keyed by "Player" and by every character name
    # (this character's own name is the self/diagonal entry — its current mood). One short
    # free-text clause per key. The engine threads and refreshes this row turn by turn.
    disposition: dict


@dataclass
class Scenario:
    id: str
    title: str
    intro: str  # premise / setup shown to the player
    goal: str  # human-readable win condition

    characters: list  # list[Character]
    max_turns: int  # hard cap; the scene can end sooner
    verdict_labels: list  # [win, lose]

    # injected as instructions for every character. Defaults to the shared spine; a scenario
    # only sets this to deliberately narrow the rules (the eval control).
    stage_rules: str = STAGE_RULES
    # injected as instructions for the situation driver AND the finale — the narrator/judge,
    # not a character. Same fairness, framed for the impartial director.
    director_rules: str = DIRECTOR_RULES
