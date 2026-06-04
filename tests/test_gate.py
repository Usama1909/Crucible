"""
Test: does the crowd correction actually bite?
The differentiator test — same evidence, different n_candidates.
"""
import sys
sys.path.insert(0, '/root/crucible')

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

gate = HonestyGate(min_outcomes=30, proven_threshold=0.95, reject_threshold=0.50)

# Test 1 — crowd correction bites
# Same evidence, few vs many candidates tried
np.random.seed(1)
returns = np.random.normal(0.004, 0.02, 200).tolist()
outcomes = make_outcomes(returns)

few  = gate.evaluate(1, outcomes, n_candidates=1)
many = gate.evaluate(1, outcomes, n_candidates=5000)

print(f"Few  trials: {few.verdict.value}  DSR={few.stats.get('dsr', 'N/A'):.3f}")
print(f"Many trials: {many.verdict.value} DSR={many.stats.get('dsr', 'N/A'):.3f}")

assert few.stats.get('dsr', 0) > many.stats.get('dsr', 0), \
    "FAIL: crowd correction not biting — DSRs are equal!"
print("PASS: crowd correction confirmed working\n")

# Test 2 — lucky winner from population gets killed
np.random.seed(7)
pop = [np.random.normal(0.0, 0.02, 200) for _ in range(300)]
best = max(pop, key=lambda r: r.mean() / (r.std() + 1e-9))
res = gate.evaluate(1, make_outcomes(best.tolist()), n_candidates=300)
print(f"Lucky winner: {res.verdict.value} DSR={res.stats.get('dsr', 'N/A')}")
assert res.verdict in [Verdict.REJECTED, Verdict.UNPROVEN], \
    "FAIL: lucky winner passed the gate!"
print("PASS: lucky winner correctly killed\n")

print("All tests passed.")