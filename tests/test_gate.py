"""Test: does the crowd correction actually bite?"""
import numpy as np
from crucible.core.vocabulary import Outcome, Verdict
from crucible.gate.gate import HonestyGate
from datetime import datetime, timezone


def make_outcomes(returns, sealed=False):
    return [Outcome(
        candidate_id=1,
        action={'direction': 'LONG'},
        result_value=r,
        cost=0.001,
        context={},
        is_sealed=sealed,
        ts=datetime.now(timezone.utc)
    ) for r in returns]


def test_gate():
    gate = HonestyGate(min_outcomes=30, proven_threshold=0.95, reject_threshold=0.50)

    np.random.seed(1)
    returns = np.random.normal(0.004, 0.02, 200).tolist()
    outcomes = make_outcomes(returns)
    few = gate.evaluate(1, outcomes, n_candidates=1)
    many = gate.evaluate(1, outcomes, n_candidates=5000)
    assert few.stats.get('dsr', 0) > many.stats.get('dsr', 0), \
        "crowd correction not biting — DSRs are equal!"

    np.random.seed(7)
    pop = [np.random.normal(0.0, 0.02, 200) for _ in range(300)]
    best = max(pop, key=lambda r: r.mean() / (r.std() + 1e-9))
    res = gate.evaluate(1, make_outcomes(best.tolist()), n_candidates=300)
    assert res.verdict in [Verdict.REJECTED, Verdict.UNPROVEN], \
        "lucky winner passed the gate!"
