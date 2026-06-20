"""Test: allocator budget distribution"""
from crucible.core.vocabulary import Candidate, CandidateStatus, Verdict, VerdictRecord
from crucible.core.allocator import Allocator
from datetime import datetime, timezone


def make_candidate(id, status, dna=None):
    c = Candidate(name=f"agent_{id}", adapter="test", dna=dna or {})
    c.id = id
    c.status = status
    return c


def make_verdict(id, mean_ret=0.01, dsr=0.97):
    return VerdictRecord(
        candidate_id=id, verdict=Verdict.PROVEN,
        confidence=dsr,
        stats={"judge_mean": mean_ret, "dsr": dsr},
        evidence_count=100
    )


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_allocator():
    alloc = Allocator(exploration_reserve=0.10, degraded_fraction=0.25)

    exploring = [make_candidate(1, CandidateStatus.EMBRYO)]
    result = alloc.allocate(exploring, {})
    check("cold start sums to 1.0", abs(sum(result.values()) - 1.0) < 0.001)
    check("cold start all goes to exploration", abs(result[1] - 1.0) < 0.001)

    proven = [make_candidate(2, CandidateStatus.PROVEN)]
    exploring = [make_candidate(3, CandidateStatus.EMBRYO)]
    verdicts = {2: make_verdict(2)}
    result = alloc.allocate(proven + exploring, verdicts)
    total = sum(result.values())
    check("proven+exploring sums to 1.0", abs(total - 1.0) < 0.001)
    check("proven gets 0.90", abs(result[2] - 0.90) < 0.001)
    check("exploring gets 0.10", abs(result[3] - 0.10) < 0.001)

    proven = [make_candidate(4, CandidateStatus.PROVEN)]
    degraded = [make_candidate(5, CandidateStatus.DEGRADED)]
    exploring = [make_candidate(6, CandidateStatus.EMBRYO)]
    verdicts = {4: make_verdict(4), 5: make_verdict(5)}
    result = alloc.allocate(proven + degraded + exploring, verdicts)
    total = sum(result.values())
    check("proven+degraded+exploring sums to 1.0", abs(total - 1.0) < 0.001)
    check("no budget overflow", total <= 1.0001)

    a1 = make_candidate(7, CandidateStatus.PROVEN, dna={"correlation_group": "grp1"})
    a2 = make_candidate(8, CandidateStatus.PROVEN, dna={"correlation_group": "grp1"})
    a3 = make_candidate(11, CandidateStatus.EMBRYO)
    verdicts = {7: make_verdict(7), 8: make_verdict(8)}
    result = alloc.allocate([a1, a2, a3], verdicts)
    check("correlated agents share budget equally", abs(result[7] - result[8]) < 0.001)
    check("correlated total = 0.90", abs(result[7] + result[8] - 0.90) < 0.001)

    a_strong = make_candidate(9, CandidateStatus.PROVEN)
    a_weak = make_candidate(10, CandidateStatus.PROVEN)
    verdicts = {9: make_verdict(9, mean_ret=0.05, dsr=0.98),
                10: make_verdict(10, mean_ret=0.01, dsr=0.96)}
    result = alloc.allocate([a_strong, a_weak], verdicts)
    check("stronger edge gets more budget", result[9] > result[10])
