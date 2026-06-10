"""
Crucible — Engine Loop
The corporation heartbeat. Connects all components.
Runs every cycle: evaluate → transition → allocate → reap → spawn.
Domain-agnostic. Adapters plug in strategies.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from crucible.core.vocabulary import (
    Candidate, CandidateStatus, Verdict, VerdictRecord
)
from crucible.core.ledger import Ledger
from crucible.core.lifecycle import LifecycleEngine
from crucible.core.allocator import Allocator
from crucible.core.memory import MemoryStore, write_death_certificate
from crucible.gate.gate import HonestyGate


class Engine:
    def __init__(self,
                 ledger: Ledger,
                 gate: HonestyGate = None,
                 lifecycle: LifecycleEngine = None,
                 allocator: Allocator = None,
                 memory: MemoryStore = None,
                 max_population: int = 50,
                 min_outcomes_to_evaluate: int = 30):
        self.ledger    = ledger
        self.gate      = gate or HonestyGate()
        self.lifecycle = lifecycle or LifecycleEngine()
        self.allocator = allocator or Allocator()
        self.memory    = memory or MemoryStore()
        self.max_population = max_population
        self.min_outcomes   = min_outcomes_to_evaluate
        self._degraded_strikes: Dict[int, int] = {}
        self._weak_streaks: Dict[int, int] = {}
        self._proven_streaks: Dict[int, int] = {}
        self._pre_dormant: Dict[int, CandidateStatus] = {}

    def run_cycle(self,
                  candidates: List[Candidate],
                  n_candidates_total: int = None) -> Dict[str, Any]:
        if n_candidates_total is None:
            n_candidates_total = max(1, len(candidates))

        report = {
            'total': len(candidates),
            'evaluated': 0,
            'transitions': [],
            'retired': [],
            'allocations': {},
            'errors': [],
        }

        verdicts: Dict[int, VerdictRecord] = {}

        for candidate in candidates:
            if candidate.id is None:
                continue
            try:
                outcomes = self.ledger.get_outcomes(candidate.id)
                if not self.lifecycle.should_evaluate(len(outcomes)):
                    continue

                verdict = self.gate.evaluate(
                    candidate_id=candidate.id,
                    outcomes=outcomes,
                    n_candidates=n_candidates_total
                )
                verdicts[candidate.id] = verdict
                report['evaluated'] += 1

                recent_verdict = None
                if len(outcomes) >= 20:
                    recent_verdict = self.gate.evaluate(
                        candidate_id=candidate.id,
                        outcomes=outcomes[-20:],
                        n_candidates=n_candidates_total
                    )

                strikes = self._degraded_strikes.get(candidate.id, 0)
                weak = self._weak_streaks.get(candidate.id, 0)
                prov = self._proven_streaks.get(candidate.id, 0)
                pre_dormant = self._pre_dormant.get(candidate.id)
                new_status, reason = self.lifecycle.next_status(
                    candidate=candidate,
                    verdict=verdict,
                    recent_verdict=recent_verdict,
                    context_match=True,
                    degraded_strikes=strikes,
                    weak_streak=weak,
                    proven_streak=prov,
                    pre_dormant_status=pre_dormant
                )

                # streak/strike bookkeeping — every evaluation, not just transitions
                weak_now = verdict.verdict in (Verdict.REJECTED, Verdict.UNPROVEN)
                if new_status == CandidateStatus.PROVEN:
                    self._weak_streaks[candidate.id] = weak + 1 if weak_now else 0
                else:
                    self._weak_streaks.pop(candidate.id, None)
                if new_status == CandidateStatus.DEGRADED:
                    if verdict.verdict == Verdict.PROVEN:
                        self._proven_streaks[candidate.id] = prov + 1
                    else:
                        self._proven_streaks[candidate.id] = 0
                        self._degraded_strikes[candidate.id] = strikes + 1
                else:
                    self._proven_streaks.pop(candidate.id, None)
                    self._degraded_strikes.pop(candidate.id, None)
                if new_status != candidate.status:
                    report['transitions'].append({
                        'candidate_id': candidate.id,
                        'name': candidate.name,
                        'from': candidate.status.value,
                        'to': new_status.value,
                        'reason': reason
                    })

                    if new_status == CandidateStatus.DORMANT:
                        self._pre_dormant[candidate.id] = candidate.status
                    elif candidate.status == CandidateStatus.DORMANT:
                        self._pre_dormant.pop(candidate.id, None)


                    self.ledger.update_candidate_status(candidate.id, new_status, reason)
                    self.ledger.save_verdict(verdict)
                    candidate.status = new_status

                    if new_status == CandidateStatus.RETIRED:
                        cert = write_death_certificate(
                            candidate=candidate,
                            verdict=verdict,
                            reason=reason
                        )
                        self.memory.record(cert)
                        self.ledger.save_memory(cert)
                        report['retired'].append({
                            'id': candidate.id,
                            'name': candidate.name,
                            'reason': reason,
                            'dsr': verdict.stats.get('dsr', 0),
                            'evidence': verdict.evidence_count
                        })

            except Exception as e:
                report['errors'].append({
                    'candidate_id': candidate.id,
                    'error': str(e)
                })

        active = [c for c in candidates
                  if c.status not in (CandidateStatus.RETIRED, CandidateStatus.DORMANT)]
        if active:
            report['allocations'] = self.allocator.allocate(active, verdicts)

        return report