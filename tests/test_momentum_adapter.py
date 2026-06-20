"""Test: MomentumAdapter spawns, acts, measures correctly."""
import numpy as np
from crucible.core.vocabulary import CandidateStatus
from crucible.adapters.momentum import MomentumAdapter


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_momentum_adapter():
    adapter = MomentumAdapter(
        lookback_options=[5, 20],
        threshold_options=[0.01, 0.02]
    )
    context = {"regime": "NORMAL"}
    candidates = adapter.spawn(context)
    check("spawn produces 4 variants", len(candidates) == 4)
    check("all candidates momentum",
          all(c.dna["strategy"] == "momentum" for c in candidates))
    check("all start EMBRYO",
          all(c.status == CandidateStatus.EMBRYO for c in candidates))

    trending_up = [100.0 + i*0.5 for i in range(30)]
    adapter.update_state("NORMAL", trending_up)
    context_up = adapter.context()
    candidate = candidates[0]
    action = adapter.act(candidate, context_up)
    check("upward trend -> LONG", action["direction"] == "LONG")

    trending_down = [100.0 - i*0.5 for i in range(30)]
    adapter.update_state("NORMAL", trending_down)
    context_dn = adapter.context()
    action_dn = adapter.act(candidate, context_dn)
    check("downward trend -> SHORT", action_dn["direction"] == "SHORT")

    flat = [100.0 + np.random.uniform(-0.1, 0.1) for _ in range(30)]
    adapter.update_state("NORMAL", flat)
    context_flat = adapter.context()
    action_flat = adapter.act(candidate, context_flat)
    check("flat market -> HOLD", action_flat["direction"] == "HOLD")

    candidate.id = 1
    reality_long_win = {"entry_price": 100.0, "exit_price": 110.0, "regime": "NORMAL"}
    outcome = adapter.measure(candidate, {"direction": "LONG"}, reality_long_win)
    expected = 0.10 - 0.001
    check("LONG win nets correct value", abs(outcome.result_value - expected) < 0.0001)

    reality_short_win = {"entry_price": 100.0, "exit_price": 90.0, "regime": "NORMAL"}
    outcome_short = adapter.measure(candidate, {"direction": "SHORT"}, reality_short_win)
    expected_short = 0.10 - 0.001
    check("SHORT win nets correct value", abs(outcome_short.result_value - expected_short) < 0.0001)

    reality_hold = {"entry_price": 100.0, "exit_price": 100.0, "regime": "NORMAL"}
    outcome_hold = adapter.measure(candidate, {"direction": "HOLD"}, reality_hold)
    check("HOLD zero P&L", outcome_hold.result_value == 0.0 - 0.001)

    crisis_candidate = adapter.spawn({"regime": "CRISIS"})[0]
    normal_context = {"regime": "NORMAL"}
    crisis_context = {"regime": "CRISIS"}
    check("crisis candidate not in NORMAL",
          adapter.applies_to(crisis_candidate, normal_context) == False)
    check("crisis candidate in CRISIS",
          adapter.applies_to(crisis_candidate, crisis_context) == True)
    check("momentum time-ordered", adapter.is_time_ordered() == True)
