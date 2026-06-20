"""Test: Spawner spawns when needed, respects population limits, reads memory."""
from crucible.core.vocabulary import Candidate, CandidateStatus, Memory
from crucible.core.spawner import Spawner
from crucible.core.memory import MemoryStore, dna_signature
from crucible.adapters.momentum import MomentumAdapter


class MockLedger:
    def __init__(self):
        self._candidates = []
        self._next_id = 1
    def save_candidate(self, c):
        c.id = self._next_id
        self._next_id += 1
        self._candidates.append(c)
        return c.id


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_spawner():
    ledger = MockLedger()
    memory = MemoryStore()
    spawner = Spawner(ledger, memory, max_population=50, min_active_per_adapter=3)
    adapter = MomentumAdapter(lookback_options=[5, 20], threshold_options=[0.01])
    adapter.update_state("NORMAL", [100.0] * 50)

    new_candidates = spawner.spawn_if_needed(adapter, active_candidates=[])
    check("spawns when 0 active", len(new_candidates) > 0)

    existing = [Candidate(name=f"a_{i}", adapter="momentum", dna={}, id=i)
                for i in range(5)]
    for c in existing:
        c.status = CandidateStatus.PROVING
    new_candidates2 = spawner.spawn_if_needed(adapter, active_candidates=existing)
    check("doesn't spawn when enough active", len(new_candidates2) == 0)

    spawner_capped = Spawner(ledger, memory, max_population=2, min_active_per_adapter=10)
    existing2 = [Candidate(name=f"b_{i}", adapter="momentum", dna={}, id=i+100)
                 for i in range(2)]
    for c in existing2:
        c.status = CandidateStatus.PROVING
    new_capped = spawner_capped.spawn_if_needed(adapter, active_candidates=existing2)
    check("respects max_population", len(new_capped) == 0)

    memory_with_deaths = MemoryStore()
    dna = {"strategy": "momentum", "timeframe": "INTRADAY", "regime": "NORMAL", "adapter": "momentum"}
    for _ in range(3):
        memory_with_deaths.record(Memory(
            dna_signature=dna_signature(dna),
            adapter="momentum",
            what_worked="",
            what_failed="repeatedly failed",
            final_stats={},
            sample_size=200,
            confidence=0.4
        ))
    ledger2 = MockLedger()
    spawner_with_mem = Spawner(ledger2, memory_with_deaths,
                               max_population=50, min_active_per_adapter=3)
    new_with_mem = spawner_with_mem.spawn_if_needed(adapter, active_candidates=[])
    check("memory-penalized filtered out", len(new_with_mem) < 2)
