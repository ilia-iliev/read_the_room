"""Scenario registry. Add one as `scenarios/<name>.py` exposing `SCENARIO`, list it below,
and it appears in the app — no engine changes."""

from scenarios.blessing import SCENARIO as BLESSING
from scenarios.hero import SCENARIO as HERO

SCENARIOS = [HERO, BLESSING]

REGISTRY = {s.id: s for s in SCENARIOS}
