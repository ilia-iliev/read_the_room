"""Evals on eval-owned fixtures (see eval_fixtures.py — not the shipping scenarios),
staged so the right answer can't be argued.

Disposition: run the real CharacterTurn on one staged line, diff its before/after stance
with the neutral DispositionShift comparator. Referee: one real Referee call per staged
turn, asserted on its outcome label. Driver voice: one real SituationDriver call per
staged turn, asserted with a deterministic regex — no judge.

  uv run evaluate.py                 quick (1 run)
  uv run evaluate.py --strict        all-of-3
  uv run evaluate.py [--strict] ferry   one fixture only
"""

import re
import sys

import dspy

import dispositions
import engine
from eval_fixtures import (
    EVAL_FIXTURES,
    GATE,
    GATE_SCENE,
    OUTCOME_CASES,
    SHIFT_CASES,
    VOICE_CASES,
)
from signatures import Referee, SituationDriver


def mark(ok):
    return "✅" if ok else "❌"


class DispositionShift(dspy.Signature):
    """Neutral before/after diff: which way did this stance move? Sees only the two stance
    cells — no persona, goal, or rules."""

    previous_disposition: str = dspy.InputField(
        desc="the character's stance before the line"
    )
    next_disposition: str = dspy.InputField(
        desc="the character's stance after the line"
    )
    shift: str = dspy.OutputField(
        desc="exactly one word. 'better' = warmer, 'worse' = harder, 'neutral' = unchanged."
    )


# the beat is player-facing: it must address the player as 'you', never in the third person
SECOND_PERSON = re.compile(r"\byou\b|\byours?\b", re.IGNORECASE)
PLAYER_IN_THIRD = re.compile(r"\bthe player\b|\bthe traveller\b", re.IGNORECASE)


def voice_passes(case, driver):
    pred = driver(
        goal=GATE.goal, scene=GATE_SCENE, this_turn=case.this_turn, room=case.room
    )
    beat = pred.next_scene
    return bool(SECOND_PERSON.search(beat)) and not PLAYER_IN_THIRD.search(beat)


def evaluate_voice(driver, runs):
    print(f"\n{'=' * 70}\n  Gate — driver voice   [all-of-{runs}]\n{'=' * 70}")
    passed = 0
    for case in VOICE_CASES:
        oks = [voice_passes(case, driver) for _ in range(runs)]
        all_ok = all(oks)
        passed += all_ok
        print(
            f"  {mark(all_ok)} {case.note[:50]:<50} want 'you'-voice  {sum(oks)}/{runs}"
        )
    ok = passed == len(VOICE_CASES)
    print(f"\n  {mark(ok)} voice: {passed}/{len(VOICE_CASES)} passed all {runs} runs")
    return ok


def outcome_passes(case, referee):
    pred = referee(
        goal=GATE.goal,
        situation=GATE_SCENE,
        this_turn=case.this_turn,
        room=case.room,
        player_so_far=case.player_so_far,
        final_turn=case.final_turn,
    )
    return engine.norm_label(pred.outcome) in case.expect


def evaluate_outcomes(referee, runs):
    print(f"\n{'=' * 70}\n  Gate — referee outcome   [all-of-{runs}]\n{'=' * 70}")
    passed = 0
    for case in OUTCOME_CASES:
        oks = [outcome_passes(case, referee) for _ in range(runs)]
        all_ok = all(oks)
        passed += all_ok
        want = "/".join(sorted(case.expect))
        print(
            f"  {mark(all_ok)} {case.note[:50]:<50} want {want:<14} {sum(oks)}/{runs}"
        )
    ok = passed == len(OUTCOME_CASES)
    print(
        f"\n  {mark(ok)} outcome: {passed}/{len(OUTCOME_CASES)} passed all {runs} runs"
    )
    return ok


def shift_passes(scen, case, actor, comparator):
    """Real character turn, then diff its before/after stance toward the player."""
    char = next(c for c in scen.characters if c.name.lower() == case.char.lower())
    keys = dispositions.row_keys(scen)
    prev = dispositions.merge_row({}, case.disposition or char.disposition, keys)
    turn = actor(
        persona=char.persona,
        disposition=dispositions.render_row(char.name, prev, keys),
        scene=case.scene or scen.intro,
        since_you_spoke=case.since or f"PLAYER: {case.line}",
    )
    new = dispositions.merge_row(prev, turn.updated_dispositions, keys)
    verdict = comparator(
        previous_disposition=prev["Player"],
        next_disposition=new["Player"],
    )
    return engine.norm_label(verdict.shift) == case.expect


def evaluate_suite(scen, actor, comparator, runs):
    print(
        f"\n{'=' * 70}\n  {scen.title} — disposition  (id: {scen.id})   [all-of-{runs}]\n{'=' * 70}"
    )
    items = SHIFT_CASES.get(scen.id, [])
    passed = 0
    for case in items:
        oks = [shift_passes(scen, case, actor, comparator) for _ in range(runs)]
        all_ok = all(oks)
        passed += all_ok
        note = case.note or case.line
        print(
            f"  {mark(all_ok)} [{case.char:<8}] {note[:42]:<42} want {case.expect:<8} {sum(oks)}/{runs}"
        )
    ok = passed == len(items)
    print(f"\n  {mark(ok)} disposition: {passed}/{len(items)} passed all {runs} runs")
    return ok


def main():
    args = sys.argv[1:]
    runs = 1
    if "--strict" in args:
        args.remove("--strict")
        runs = 3
    lm = engine.make_lm(0.2, cache=False)

    registry = {s.id: s for s in EVAL_FIXTURES}
    only = args[0] if args else None
    scenarios = [registry[only]] if only else list(registry.values())
    print(f"  mode: all-of-{runs}, cache off")

    comparator = dspy.Predict(DispositionShift)  # scene-agnostic, no stage_rules
    results = {}
    for scen in scenarios:
        if scen.id not in SHIFT_CASES:
            continue
        with dspy.context(lm=lm):
            actor = dspy.Predict(engine.character_signature(scen))
            results[f"{scen.id}/disposition"] = evaluate_suite(
                scen, actor, comparator, runs
            )

    if not only or only == "gate":
        with dspy.context(lm=lm):
            referee = dspy.Predict(Referee.with_instructions(GATE.director_rules))
            results["gate/outcome"] = evaluate_outcomes(referee, runs)
            driver = dspy.Predict(
                SituationDriver.with_instructions(GATE.director_rules)
            )
            results["gate/voice"] = evaluate_voice(driver, runs)

    print(f"\n{'=' * 70}\n  SUMMARY")
    for key, ok in results.items():
        print(f"  {mark(ok)} {key}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
