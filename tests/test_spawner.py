"""
Test: Spawner spawns when needed, respects population limits, reads memory.
"""
import sys
sys.path.insert(0, '/root/crucible')

from crucible.core.vocabulary import Candidate, CandidateStatus, Memory
from crucible.core.spawner import Spawner
from crucible.core.memory import MemoryStore, dna_signature
from crucible.adapters.momentum import MomentumAdapter

passed = 0
failed = 0

def check(desc, condition):
    global passed, failed
    if condition:
        print(f"PASS: {desc}")
        passed += 1
    else:
        print(f"FAIL: {desc}")
        failed += 1


class MockLedger:
    def __init__(self):
        self._candidates = []
        self._next_id = 1
    def save_candidate(self, c):
        c.id = self._next_id
        self._next_id += 1
        self._candidates.append(c)
        return c.id


# Test 1 — spawns when adapter has no active candidates
ledger = MockLedger()
memory = MemoryStore()
spawner = Spawner(ledger, memory, max_population=50, min_active_per_adapter=3)
adapter = MomentumAdapter(lookback_options=[5, 20], threshold_options=[0.01])
adapter.update_state("NORMAL", [100.0] * 50)

new_candidates = spawner.spawn_if_needed(adapter, active_candidates=[])
check("spawns when adapter has 0 active candidates", len(new_candidates) > 0)

# Test 2 — doesn't spawn when adapter has enough active
existing = [Candidate(name=f"a_{i}", adapter="momentum", dna={}, id=i)
            for i in range(5)]
for c in existing:
    c.status = CandidateStatus.PROVING
new_candidates2 = spawner.spawn_if_needed(adapter, active_candidates=existing)
check("doesn't spawn when adapter has min_active candidates",
      len(new_candidates2) == 0)

# Test 3 — respects max_population
spawner_capped = Spawner(ledger, memory, max_population=2, min_active_per_adapter=10)
existing2 = [Candidate(name=f"b_{i}", adapter="momentum", dna={}, id=i+100)
             for i in range(2)]
for c in existing2:
    c.status = CandidateStatus.PROVING
new_capped = spawner_capped.spawn_if_needed(adapter, active_candidates=existing2)
check("respects max_population cap", len(new_capped) == 0)

# Test 4 — reads memory hints
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
check("memory-penalized candidates filtered out",
      len(new_with_mem) < 2)

print(f"\n{passed} passed, {failed} failed.")