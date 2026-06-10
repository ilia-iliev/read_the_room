"""Scenario definitions. Add one as `scenarios/<name>.py` exposing `SCENARIO`, list it
below, and it appears in the app — no engine changes. Every scenario is a standoff the
player talks through: the player speaks, one or two characters react in their own voice
(each acting on its private disposition, then refreshing it), and a situation driver
advances the scene and sets the next beat. A scenario runs up to `max_turns`; it can end
sooner (a fatal line, or the goal reached), and if the cap is hit the model decides the
outcome.
"""

from scenarios.hero import SCENARIO as HERO
from scenarios.shark import SCENARIO as SHARK

SCENARIOS = [HERO, SHARK]

REGISTRY = {s.id: s for s in SCENARIOS}
