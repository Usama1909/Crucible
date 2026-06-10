"""
Crucible — Memory
Death certificates written when agents retire.
New agents read relevant memories before first action.
Lessons tagged with sample size — weak evidence is a hint, not gospel.
"""
import json
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from crucible.core.vocabulary import Candidate, Memory, VerdictRecord


def dna_signature(dna: Dict[str, Any],
                  keys: tuple = ("strategy", "timeframe", "adapter")) -> str:
    """Hash only structural DNA keys — variants of same strategy share memory."""
    structural = {k: dna[k] for k in keys if k in dna}
    serialized = json.dumps(structural, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def write_death_certificate(candidate: Candidate,
                             verdict: VerdictRecord,
                             reason: str,
                             what_worked: str = "",
                             what_failed: str = "") -> Memory:
    """Called when an agent retires. Returns Memory ready to save."""
    sig = dna_signature(candidate.dna)
    return Memory(
        dna_signature=sig,
        adapter=candidate.adapter,
        what_worked=what_worked or _infer_worked(verdict),
        what_failed=what_failed or reason,
        final_stats=verdict.stats,
        sample_size=verdict.evidence_count,
        confidence=verdict.confidence,
        context={"regime": candidate.dna.get("regime")},
    )


def _infer_worked(verdict: VerdictRecord) -> str:
    """Auto-derive what_worked from verdict stats."""
    sr = verdict.stats.get('sharpe', None)
    dsr = verdict.stats.get('dsr', None)
    if sr is not None and dsr is not None:
        return f"Sharpe={sr:.3f} DSR={dsr:.3f} on {verdict.evidence_count} outcomes"
    return f"Ran for {verdict.evidence_count} outcomes"


class MemoryStore:

    def __init__(self):
        self._store: List[Memory] = []

    def record(self, memory: Memory):
        """Store a death certificate."""
        self._store.append(memory)

    def recall(self,
               dna: Dict[str, Any],
               adapter: str,
               min_sample: int = 10) -> List[Memory]:
        """Retrieve relevant memories by structural DNA match."""
        sig = dna_signature(dna)
        return [m for m in self._store
                if m.dna_signature == sig
                and m.adapter == adapter
                and m.sample_size >= min_sample]

    def spawn_hints(self, dna: Dict[str, Any], adapter: str) -> Dict[str, Any]:
        """
        What a new agent should know before first action.
        Returns: budget_multiplier, warnings, hypothesis, death_count.
        """
        memories = self.recall(dna, adapter)
        if not memories:
            return {"budget_multiplier": 1.0, "warnings": [], "hypothesis": None, "death_count": 0}

        # Evidence-weighted penalty — more outcomes behind deaths = stronger penalty
        fail_evidence = sum(min(m.sample_size, 200) for m in memories)
        budget_multiplier = max(0.3, 1.0 - fail_evidence / 1000.0)

        warnings = [m.what_failed for m in memories if m.what_failed]
        worked = [m.what_worked for m in memories if m.what_worked]

        return {
            "budget_multiplier": budget_multiplier,
            "warnings": warnings,
            "hypothesis": worked[-1] if worked else None,
            "death_count": len(memories),
        }

    def summarize(self, dna: Dict[str, Any], adapter: str) -> Optional[str]:
        """One-line summary of what past agents with this DNA learned."""
        memories = self.recall(dna, adapter)
        if not memories:
            return None
        lines = []
        for m in memories:
            tag = f"(n={m.sample_size}, conf={m.confidence:.2f})"
            if m.what_failed:
                lines.append(f"Failed: {m.what_failed} {tag}")
            if m.what_worked:
                lines.append(f"Worked: {m.what_worked} {tag}")
        return "\n".join(lines)