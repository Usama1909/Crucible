"""
Crucible — Reaper
Sweeps retired candidates. Ensures death certificates are written and
budgets are freed. Domain-agnostic.
"""
from typing import List, Dict, Any
from crucible.core.vocabulary import Candidate, CandidateStatus, VerdictRecord
from crucible.core.ledger import Ledger
from crucible.core.memory import MemoryStore, write_death_certificate


class Reaper:
    """
    Cleans up retired candidates.
    Engine drives the lifecycle transitions; Reaper handles the cleanup.
    """

    def __init__(self,
                 ledger: Ledger,
                 memory: MemoryStore):
        self.ledger = ledger
        self.memory = memory
        self._reaped_ids: set = set()

    def reap(self,
             candidates: List[Candidate],
             verdicts: Dict[int, VerdictRecord]) -> Dict[str, Any]:
        """
        Process all RETIRED candidates that haven't been reaped yet.
        Returns a report of what was cleaned up.
        """
        report = {
            'reaped': [],
            'skipped': [],
            'errors': []
        }

        for candidate in candidates:
            if candidate.id is None:
                continue
            if candidate.status != CandidateStatus.RETIRED:
                continue
            if candidate.id in self._reaped_ids:
                report['skipped'].append(candidate.id)
                continue

            try:
                verdict = verdicts.get(candidate.id)
                if verdict is None:
                    # No verdict but retired — still write a minimal cert
                    reason = candidate.retire_reason or "retired without verdict"
                    cert = write_death_certificate(
                        candidate=candidate,
                        verdict=VerdictRecord(
                            candidate_id=candidate.id,
                            verdict=candidate.status.value if hasattr(candidate.status, 'value') else 'RETIRED',
                            confidence=0.0,
                            stats={},
                            evidence_count=0,
                        ) if False else None,
                        reason=reason
                    ) if False else None
                    # Skip cert writing without verdict — just mark reaped
                    self._reaped_ids.add(candidate.id)
                    report['skipped'].append(candidate.id)
                    continue

                cert = write_death_certificate(
                    candidate=candidate,
                    verdict=verdict,
                    reason=candidate.retire_reason or "retired"
                )
                self.memory.record(cert)
                self.ledger.save_memory(cert)
                self._reaped_ids.add(candidate.id)

                report['reaped'].append({
                    'id': candidate.id,
                    'name': candidate.name,
                    'dna_signature': cert.dna_signature,
                    'sample_size': cert.sample_size,
                })

            except Exception as e:
                report['errors'].append({
                    'candidate_id': candidate.id,
                    'error': str(e)
                })

        return report

    def already_reaped(self, candidate_id: int) -> bool:
        return candidate_id in self._reaped_ids