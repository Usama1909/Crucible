"""
Crucible — Allocator
Splits budget across agents based on proven edge.
Rules:
- Only PROVEN agents get performance budget
- DEGRADED agents share a flat pool (degraded_fraction of total)
- EMBRYO/PROVING share exploration reserve
- Correlated agents (same correlation_group in DNA) share one slot
- Total allocations always sum to <= 1.0
- Cold start: no PROVEN → exploration gets performance share too
"""
from typing import List, Dict
from crucible.core.vocabulary import Candidate, CandidateStatus, VerdictRecord


class Allocator:

    def __init__(self,
                 exploration_reserve: float = 0.10,
                 degraded_fraction: float = 0.25):
        self.exploration_reserve = exploration_reserve
        self.degraded_fraction   = degraded_fraction

    def allocate(self,
                 agents: List[Candidate],
                 verdicts: Dict[int, VerdictRecord]) -> Dict[int, float]:
        """
        Returns {agent_id: budget_fraction}. Fractions sum to <= 1.0.
        """
        proven    = [a for a in agents if a.status == CandidateStatus.PROVEN and a.id in verdicts]
        degraded  = [a for a in agents if a.status == CandidateStatus.DEGRADED and a.id in verdicts]
        exploring = [a for a in agents if a.status in (CandidateStatus.EMBRYO, CandidateStatus.PROVING)]

        # Carve pools off the top so they never overflow
        deg_pool     = self.degraded_fraction   if degraded  else 0.0
        explore_pool = self.exploration_reserve if exploring else 0.0

        if proven:
            perf_budget = max(0.0, 1.0 - deg_pool - explore_pool)
        else:
            # Cold start — fold performance budget into exploration
            perf_budget  = 0.0
            explore_pool = 1.0 - deg_pool

        allocations: Dict[int, float] = {}

        # PROVEN — performance budget weighted by mean_return * DSR
        if proven and perf_budget > 0:
            allocations.update(self._allocate_proven(proven, verdicts, perf_budget))

        # DEGRADED — equal share of degraded pool
        if degraded and deg_pool > 0:
            per = deg_pool / len(degraded)
            for a in degraded:
                allocations[a.id] = per

        # EXPLORING — equal share of exploration pool
        if exploring and explore_pool > 0:
            per = explore_pool / len(exploring)
            for a in exploring:
                allocations[a.id] = per

        # Guard: never exceed 1.0
        assert sum(allocations.values()) <= 1.0001, \
            f"Budget overflow: {sum(allocations.values()):.4f}"

        return allocations

    def _allocate_proven(self,
                          proven: List[Candidate],
                          verdicts: Dict[int, VerdictRecord],
                          budget: float) -> Dict[int, float]:
        """Weight by mean_return * DSR. Correlated agents share one slot."""
        groups: Dict[str, List[Candidate]] = {}
        for a in proven:
            group = a.dna.get("correlation_group", str(a.id))
            groups.setdefault(group, []).append(a)

        group_weights: Dict[str, float] = {}
        for group, members in groups.items():
            best = max(members, key=lambda a: self._agent_weight(a, verdicts))
            group_weights[group] = self._agent_weight(best, verdicts)

        total_weight = sum(group_weights.values())

        result = {}
        for group, members in groups.items():
            if total_weight > 0:
                group_budget = budget * (group_weights[group] / total_weight)
            else:
                group_budget = budget / len(groups)
            share = group_budget / len(members)
            for a in members:
                result[a.id] = share
        return result

    def _agent_weight(self, agent: Candidate,
                       verdicts: Dict[int, VerdictRecord]) -> float:
        """Weight = mean_return * DSR. Returns 0.0 if non-positive."""
        v = verdicts.get(agent.id)
        if not v:
            return 0.0
        dsr = v.confidence
        mean_ret = v.stats.get('judge_mean', None)
        if mean_ret is not None and mean_ret > 0:
            return mean_ret * dsr
        return 0.0