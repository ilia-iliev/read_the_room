"""Scenario registry. Add one as `scenarios/<name>.py` exposing `SCENARIO`, list it below,
and it appears in the app — no engine changes."""

from scenarios.hero import SCENARIO as HERO
from scenarios.shark import SCENARIO as SHARK

SCENARIOS = [HERO, SHARK]

REGISTRY = {s.id: s for s in SCENARIOS}
