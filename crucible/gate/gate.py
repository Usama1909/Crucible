"""
Crucible — Honesty Gate
Answers one question: real edge or lucky edge?
"""
from typing import List
from crucible.core.vocabulary import Outcome, Verdict, VerdictRecord
from crucible.gate.stats import (
    sharpe_ratio, deflated_sharpe_ratio,
    t_test_mean, stability_score
)
from crucible.gate.splitter import chronological_split, random_split


class HonestyGate:
    def __init__(self,
                 min_outcomes: int = 30,
                 judge_pct: float = 0.3,
                 proven_threshold: float = 0.95,
                 reject_threshold: float = 0.50,
                 p_value_threshold: float = 0.05,
                 min_stability_splits: int = 2,
                 time_ordered: bool = True):
        self.min_outcomes          = min_outcomes
        self.judge_pct             = judge_pct
        self.proven_threshold      = proven_threshold
        self.reject_threshold      = reject_threshold
        self.p_value_threshold     = p_value_threshold
        self.min_stability_splits  = min_stability_splits
        self.time_ordered          = time_ordered

    def evaluate(self,
                 candidate_id: int,
                 outcomes: List[Outcome],
                 n_candidates: int,
                 min_outcomes: int = None) -> VerdictRecord:
        stats = {}
        required = min_outcomes if min_outcomes is not None else self.min_outcomes

        # Check 1 — enough evidence
        if len(outcomes) < required:
            stats['reason'] = f'insufficient evidence: {len(outcomes)} < {required}'
            stats['min_outcomes_required'] = required
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.UNPROVEN,
                confidence=0.0,
                stats=stats,
                evidence_count=len(outcomes)
            )

        # Check 2 — use is_sealed flag if available, else split
        sealed = [o for o in outcomes if o.is_sealed]
        if sealed:
            judge = sealed
            train = [o for o in outcomes if not o.is_sealed]
        else:
            if self.time_ordered:
                train, judge = chronological_split(outcomes, self.judge_pct)
            else:
                train, judge = random_split(outcomes, self.judge_pct)

        if len(judge) < 5:
            stats['reason'] = 'judge set too small'
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.UNPROVEN,
                confidence=0.0,
                stats=stats,
                evidence_count=len(outcomes)
            )

        judge_returns = [o.result_value for o in judge]
        stats['judge_n'] = len(judge_returns)
        stats['judge_mean'] = float(sum(judge_returns) / len(judge_returns))

        # Check 3 — edge after cost (t-test, mean > 0, p < threshold)
        mean_ret, p_val = t_test_mean(judge_returns)
        stats['t_test_mean'] = mean_ret
        stats['t_test_p'] = p_val

        if mean_ret <= 0 or p_val >= self.p_value_threshold:
            stats['reason'] = f'no positive edge: mean={mean_ret:.4f} p={p_val:.4f}'
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.REJECTED,
                confidence=0.0,
                stats=stats,
                evidence_count=len(outcomes)
            )

        # Check 4 — luck of crowd correction (DSR) — three bands
        sr = sharpe_ratio(judge_returns)
        dsr = deflated_sharpe_ratio(sr, n_candidates, len(judge_returns))
        stats['sharpe'] = sr
        stats['dsr'] = dsr
        stats['n_candidates'] = n_candidates

        if dsr < self.reject_threshold:
            stats['reason'] = f'DSR {dsr:.3f} below reject threshold {self.reject_threshold}'
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.REJECTED,
                confidence=dsr,
                stats=stats,
                evidence_count=len(outcomes)
            )

        if dsr < self.proven_threshold:
            stats['reason'] = f'DSR {dsr:.3f} still proving (need {self.proven_threshold})'
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.UNPROVEN,
                confidence=dsr,
                stats=stats,
                evidence_count=len(outcomes)
            )

        # Check 5 — stability across sub-periods
        stable = stability_score(judge_returns,
                                  min_positive=self.min_stability_splits)
        stats['stable'] = stable

        if not stable:
            stats['reason'] = 'edge not stable across sub-periods'
            return VerdictRecord(
                candidate_id=candidate_id,
                verdict=Verdict.REJECTED,
                confidence=dsr,
                stats=stats,
                evidence_count=len(outcomes)
            )

        stats['reason'] = 'passed all checks'
        return VerdictRecord(
            candidate_id=candidate_id,
            verdict=Verdict.PROVEN,
            confidence=dsr,
            stats=stats,
            evidence_count=len(outcomes)
        )