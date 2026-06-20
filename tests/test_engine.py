"""Test: engine loop connects all components"""
import numpy as np
from datetime import datetime, timezone
from crucible.core.vocabulary import (
    Candidate, CandidateStatus, Outcome, Verdict
)
from crucible.core.lifecycle import LifecycleEngine
from crucible.core.allocator import Allocator
from crucible.core.memory import MemoryStore
from crucible.gate.gate import HonestyGate
from crucible.core.engine import Engine


class MockLedger:
    def __init__(self, outcomes_per_candidate):
        self._outcomes = outcomes_per_candidate
        self._statuses = {}
        self._verdicts = []
        self._memories = []

    def get_outcomes(self, candidate_id):
        return self._outcomes.get(candidate_id, [])

    def update_candidate_status(self, candidate_id, status, reason=None):
        self._statuses[candidate_id] = status

    def save_verdict(self, verdict):
        self._verdicts.append(verdict)

    def save_memory(self, memory):
        self._memories.append(memory)


def make_candidate(id, status=CandidateStatus.PROVING):
    c = Candidate(name=f"agent_{id}", adapter="test",
                  dna={"strategy": "momentum"}, id=id)
    c.status = status
    return c


def make_outcomes(returns, candidate_id, sealed=False):
    return [Outcome(
        candidate_id=candidate_id,
        action={'dir': 'LONG'},
        result_value=r,
        cost=0.001,
        context={},
        is_sealed=sealed,
        ts=datetime.now(timezone.utc)
    ) for r in returns]


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_engine():
    np.random.seed(42)
    real_returns = np.random.normal(0.01, 0.02, 200).tolist()

    good_agent = make_candidate(1)
    ledger = MockLedger({1: make_outcomes(real_returns, 1)})
    engine = Engine(ledger=ledger, gate=HonestyGate(min_outcomes=30))
    report = engine.run_cycle([good_agent], n_candidates_total=1)
    check("real edge agent evaluated", report['evaluated'] == 1)
    check("real edge agent -> PROVEN",
          any(t['to'] == 'PROVEN' for t in report['transitions']))

    np.random.seed(7)
    pop = [np.random.normal(0.0, 0.02, 200) for _ in range(300)]
    best = max(pop, key=lambda r: r.mean() / (r.std() + 1e-9))
    lucky_agent = make_candidate(2)
    ledger2 = MockLedger({2: make_outcomes(best.tolist(), 2)})
    engine2 = Engine(ledger=ledger2, gate=HonestyGate(min_outcomes=30))
    report2 = engine2.run_cycle([lucky_agent], n_candidates_total=300)
    check("lucky agent evaluated", report2['evaluated'] == 1)
    check("lucky agent RETIRED",
          any(t['to'] == 'RETIRED' for t in report2['transitions']))
    check("death certificate written", len(engine2.memory._store) == 1)

    embryo = make_candidate(3, CandidateStatus.EMBRYO)
    ledger3 = MockLedger({3: make_outcomes([0.01]*10, 3)})
    engine3 = Engine(ledger=ledger3)
    report3 = engine3.run_cycle([embryo], n_candidates_total=1)
    check("embryo not evaluated", report3['evaluated'] == 0)
    check("embryo has no transitions", len(report3['transitions']) == 0)

    proven = make_candidate(4, CandidateStatus.PROVEN)
    exploring = make_candidate(5, CandidateStatus.EMBRYO)
    ledger4 = MockLedger({
        4: make_outcomes(real_returns, 4),
        5: make_outcomes([0.01]*10, 5)
    })
    engine4 = Engine(ledger=ledger4, gate=HonestyGate(min_outcomes=30))
    report4 = engine4.run_cycle([proven, exploring], n_candidates_total=5)
    check("allocations produced", len(report4['allocations']) > 0)
