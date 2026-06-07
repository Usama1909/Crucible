"""
Crucible — Spawner
Watches context, decides when to spawn new candidates.
Reads memory before spawning so the next generation learns from the dead.
"""
from typing import List, Dict, Any
from crucible.core.vocabulary import Candidate, CandidateStatus
from crucible.core.ledger import Ledger
from crucible.core.memory import MemoryStore
from crucible.adapters.base import BaseAdapter


class Spawner:
    def __init__(self,
                 ledger: Ledger,
                 memory: MemoryStore,
                 max_population: int = 50,
                 min_active_per_adapter: int = 3):
        self.ledger             = ledger
        self.memory             = memory
        self.max_population     = max_population
        self.min_active_per_adapter = min_active_per_adapter

    def spawn_if_needed(self,
                        adapter: BaseAdapter,
                        active_candidates: List[Candidate]) -> List[Candidate]:
        adapter_active = [c for c in active_candidates
                          if c.adapter == adapter.name
                          and c.status not in (CandidateStatus.RETIRED, CandidateStatus.DORMANT)]

        if len(adapter_active) >= self.min_active_per_adapter:
            return []

        if len(active_candidates) >= self.max_population:
            return []

        context = adapter.context()
        new_candidates = adapter.spawn(context)

        survivors = []
        for c in new_candidates:
            hints = self.memory.spawn_hints(c.dna, adapter.name)
            if hints["death_count"] >= 3 and hints["budget_multiplier"] < 0.5:
                continue
            c.budget = hints["budget_multiplier"] * 0.1
            if hints["warnings"]:
                c.spawn_reason = (c.spawn_reason or "") + \
                    f" | warned by {hints['death_count']} past deaths"
            survivors.append(c)

        room = self.max_population - len(active_candidates)
        survivors = survivors[:room]

        for c in survivors:
            self.ledger.save_candidate(c)

        return survivors