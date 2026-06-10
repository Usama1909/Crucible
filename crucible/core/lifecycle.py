"""
Crucible — Agent Lifecycle State Machine
EMBRYO → PROVING → PROVEN → DEGRADED → RETIRED
Any state → DORMANT (context mismatch, can wake back to previous status)
Gate drives every transition.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from crucible.core.vocabulary import (
    Candidate, CandidateStatus, Verdict, VerdictRecord
)

MIN_OUTCOMES_TO_EVALUATE = 30
MAX_DEGRADED_STRIKES = 3


class LifecycleEngine:

    def __init__(self,
                 min_outcomes: int = MIN_OUTCOMES_TO_EVALUATE,
                 max_degraded_strikes: int = MAX_DEGRADED_STRIKES,
                 demote_strikes: int = 2,
                 promote_confirmations: int = 2):
        self.min_outcomes         = min_outcomes
        self.max_degraded_strikes = max_degraded_strikes
        self.demote_strikes = demote_strikes
        self.promote_confirmations = promote_confirmations

    def next_status(self,
                    candidate: Candidate,
                    verdict: VerdictRecord,
                    recent_verdict: Optional[VerdictRecord] = None,
                    context_match: bool = True,
                    degraded_strikes: int = 0,
                    weak_streak: int = 0,
                    proven_streak: int = 0,
                    pre_dormant_status: Optional[CandidateStatus] = None
                    ) -> Tuple[CandidateStatus, str]:

        current = candidate.status

        # 1. RETIRED is terminal — check this first, before anything else
        if current == CandidateStatus.RETIRED:
            return CandidateStatus.RETIRED, "already retired"

        # 2. Context mismatch → DORMANT (store current status to restore later)
        if not context_match and current != CandidateStatus.DORMANT:
            return CandidateStatus.DORMANT, f"context mismatch — paused from {current.value}"

        # 3. Wake dormant → restore previous status, not PROVING
        if current == CandidateStatus.DORMANT and context_match:
            restore = pre_dormant_status or CandidateStatus.PROVING
            # If was PROVEN, go to DEGRADED for quick re-check
            if restore == CandidateStatus.PROVEN:
                return CandidateStatus.DEGRADED, "woke from dormant — quick re-check"
            return restore, f"context returned — restored to {restore.value}"

        v = verdict.verdict

        # 4. EMBRYO — waiting for enough evidence
        if current == CandidateStatus.EMBRYO:
            if verdict.evidence_count >= self.min_outcomes:
                return CandidateStatus.PROVING, "enough evidence to start proving"
            return CandidateStatus.EMBRYO, "gathering evidence"

        # 5. PROVING — gate hasn't confirmed yet
        if current == CandidateStatus.PROVING:
            if v == Verdict.PROVEN:
                return CandidateStatus.PROVEN, "gate confirmed real edge"
            if v == Verdict.REJECTED:
                return CandidateStatus.RETIRED, "gate rejected — no real edge"
            return CandidateStatus.PROVING, "still proving"

        # 6. PROVEN — demote only after consecutive weak verdicts (hysteresis)
        if current == CandidateStatus.PROVEN:
            weak_now = v in [Verdict.REJECTED, Verdict.UNPROVEN]
            if weak_now and (weak_streak + 1) >= self.demote_strikes:
                return CandidateStatus.DEGRADED, f"edge decayed: {weak_streak + 1} consecutive weak verdicts"
            if weak_now:
                return CandidateStatus.PROVEN, f"weak verdict {weak_streak + 1}/{self.demote_strikes} - holding"
            return CandidateStatus.PROVEN, "edge holding"

        # 7. DEGRADED — promote after consecutive PROVEN; retire after strikes
        if current == CandidateStatus.DEGRADED:
            if v == Verdict.PROVEN:
                if (proven_streak + 1) >= self.promote_confirmations:
                    return CandidateStatus.PROVEN, f"edge recovered: {proven_streak + 1} consecutive proven verdicts"
                return CandidateStatus.DEGRADED, f"recovering {proven_streak + 1}/{self.promote_confirmations}"
            new_strikes = degraded_strikes + 1
            if new_strikes >= self.max_degraded_strikes:
                return CandidateStatus.RETIRED, f"retired after {new_strikes} degraded strikes"
            return CandidateStatus.DEGRADED, f"still degraded (strike {new_strikes}/{self.max_degraded_strikes})"

        return current, "no transition"

    def should_evaluate(self, n_outcomes: int) -> bool:
        return n_outcomes >= self.min_outcomes

    def death_certificate(self,
                           candidate: Candidate,
                           verdict: VerdictRecord,
                           reason: str) -> Dict[str, Any]:
        return {
            "dna":            candidate.dna,
            "adapter":        candidate.adapter,
            "retire_reason":  reason,
            "final_verdict":  verdict.verdict.value,
            "final_stats":    verdict.stats,
            "evidence_count": verdict.evidence_count,
            "confidence":     verdict.confidence,
            "born_at":        candidate.born_at.isoformat(),
            "retired_at":     datetime.now(timezone.utc).isoformat(),
        }