"""Test: lifecycle state machine transitions"""
from crucible.core.vocabulary import (
    Candidate, CandidateStatus, Verdict, VerdictRecord
)
from crucible.core.lifecycle import LifecycleEngine
from datetime import datetime, timezone


def make_candidate(status):
    c = Candidate(name="test", adapter="test", dna={}, id=1)
    c.status = status
    return c


def make_verdict(verdict, evidence=50, confidence=0.9):
    return VerdictRecord(
        candidate_id=1, verdict=verdict,
        confidence=confidence, stats={}, evidence_count=evidence
    )


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_lifecycle():
    engine = LifecycleEngine(min_outcomes=30, max_degraded_strikes=3)

    c = make_candidate(CandidateStatus.RETIRED)
    s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=False)
    check("RETIRED stays RETIRED", s == CandidateStatus.RETIRED)

    c = make_candidate(CandidateStatus.EMBRYO)
    s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN, evidence=10))
    check("EMBRYO stays with insufficient evidence", s == CandidateStatus.EMBRYO)

    c = make_candidate(CandidateStatus.EMBRYO)
    s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN, evidence=50))
    check("EMBRYO -> PROVING with enough evidence", s == CandidateStatus.PROVING)

    c = make_candidate(CandidateStatus.PROVING)
    s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN))
    check("PROVING -> PROVEN", s == CandidateStatus.PROVEN)

    c = make_candidate(CandidateStatus.PROVING)
    s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED))
    check("PROVING -> RETIRED on rejection", s == CandidateStatus.RETIRED)

    c = make_candidate(CandidateStatus.PROVEN)
    s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), weak_streak=1)
    check("PROVEN -> DEGRADED on hard rejection", s == CandidateStatus.DEGRADED)

    c = make_candidate(CandidateStatus.PROVEN)
    s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN), weak_streak=1)
    check("PROVEN -> DEGRADED on soft decay", s == CandidateStatus.DEGRADED)

    c = make_candidate(CandidateStatus.DEGRADED)
    s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), degraded_strikes=1)
    check("DEGRADED stays below strike limit", s == CandidateStatus.DEGRADED)

    c = make_candidate(CandidateStatus.DEGRADED)
    s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), degraded_strikes=2)
    check("DEGRADED -> RETIRED at max strikes", s == CandidateStatus.RETIRED)

    c = make_candidate(CandidateStatus.DEGRADED)
    s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), proven_streak=1)
    check("DEGRADED -> PROVEN on recovery", s == CandidateStatus.PROVEN)

    c = make_candidate(CandidateStatus.PROVEN)
    s, r = engine.next_status(c, make_verdict(Verdict.UNPROVEN), weak_streak=0)
    check("PROVEN holds on first weak verdict", s == CandidateStatus.PROVEN)

    c = make_candidate(CandidateStatus.DEGRADED)
    s, r = engine.next_status(c, make_verdict(Verdict.PROVEN), proven_streak=0)
    check("DEGRADED holds on first proven verdict", s == CandidateStatus.DEGRADED)

    c = make_candidate(CandidateStatus.PROVEN)
    s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=False)
    check("PROVEN -> DORMANT on context mismatch", s == CandidateStatus.DORMANT)

    c = make_candidate(CandidateStatus.DORMANT)
    s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=True,
                              pre_dormant_status=CandidateStatus.PROVEN)
    check("DORMANT -> DEGRADED when was PROVEN", s == CandidateStatus.DEGRADED)

    c = make_candidate(CandidateStatus.DORMANT)
    s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN), context_match=True,
                              pre_dormant_status=CandidateStatus.PROVING)
    check("DORMANT -> PROVING when was PROVING", s == CandidateStatus.PROVING)
