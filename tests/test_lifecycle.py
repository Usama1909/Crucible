"""
Test: lifecycle state machine transitions
"""
import sys
sys.path.insert(0, '/root/crucible')

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

engine = LifecycleEngine(min_outcomes=30, max_degraded_strikes=3)
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

# RETIRED is terminal
c = make_candidate(CandidateStatus.RETIRED)
s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=False)
check("RETIRED stays RETIRED even with context_match=False", s == CandidateStatus.RETIRED)

# EMBRYO waits for evidence
c = make_candidate(CandidateStatus.EMBRYO)
s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN, evidence=10))
check("EMBRYO stays EMBRYO with insufficient evidence", s == CandidateStatus.EMBRYO)

# EMBRYO graduates with enough evidence
c = make_candidate(CandidateStatus.EMBRYO)
s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN, evidence=50))
check("EMBRYO → PROVING with enough evidence", s == CandidateStatus.PROVING)

# PROVING → PROVEN
c = make_candidate(CandidateStatus.PROVING)
s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN))
check("PROVING → PROVEN on gate confirmation", s == CandidateStatus.PROVEN)

# PROVING → RETIRED on rejection
c = make_candidate(CandidateStatus.PROVING)
s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED))
check("PROVING → RETIRED on rejection", s == CandidateStatus.RETIRED)

# PROVEN → DEGRADED on hard rejection
c = make_candidate(CandidateStatus.PROVEN)
s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), weak_streak=1)
check("PROVEN → DEGRADED on hard rejection (2nd weak)", s == CandidateStatus.DEGRADED)

# PROVEN → DEGRADED on soft decay (UNPROVEN)
c = make_candidate(CandidateStatus.PROVEN)
s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN), weak_streak=1)
check("PROVEN → DEGRADED on soft decay (2nd weak)", s == CandidateStatus.DEGRADED)

# DEGRADED stays DEGRADED below strike limit
c = make_candidate(CandidateStatus.DEGRADED)
s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), degraded_strikes=1)
check("DEGRADED stays DEGRADED below strike limit", s == CandidateStatus.DEGRADED)

# DEGRADED → RETIRED at strike limit
c = make_candidate(CandidateStatus.DEGRADED)
s, _ = engine.next_status(c, make_verdict(Verdict.REJECTED), degraded_strikes=2)
check("DEGRADED → RETIRED at max strikes", s == CandidateStatus.RETIRED)

# DEGRADED → PROVEN on recovery
c = make_candidate(CandidateStatus.DEGRADED)
s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), proven_streak=1)
check("DEGRADED → PROVEN on recovery (2nd proven)", s == CandidateStatus.PROVEN)


# HYSTERESIS: PROVEN holds on FIRST weak verdict
c = make_candidate(CandidateStatus.PROVEN)
s, r = engine.next_status(c, make_verdict(Verdict.UNPROVEN), weak_streak=0)
check("PROVEN holds on first weak verdict", s == CandidateStatus.PROVEN)

# HYSTERESIS: DEGRADED holds on FIRST proven verdict
c = make_candidate(CandidateStatus.DEGRADED)
s, r = engine.next_status(c, make_verdict(Verdict.PROVEN), proven_streak=0)
check("DEGRADED holds on first proven verdict", s == CandidateStatus.DEGRADED)

# PROVEN → DORMANT on context mismatch
c = make_candidate(CandidateStatus.PROVEN)
s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=False)
check("PROVEN → DORMANT on context mismatch", s == CandidateStatus.DORMANT)

# DORMANT wakes to DEGRADED (was PROVEN)
c = make_candidate(CandidateStatus.DORMANT)
s, _ = engine.next_status(c, make_verdict(Verdict.PROVEN), context_match=True,
                            pre_dormant_status=CandidateStatus.PROVEN)
check("DORMANT → DEGRADED when was PROVEN", s == CandidateStatus.DEGRADED)

# DORMANT wakes to PROVING (was PROVING)
c = make_candidate(CandidateStatus.DORMANT)
s, _ = engine.next_status(c, make_verdict(Verdict.UNPROVEN), context_match=True,
                            pre_dormant_status=CandidateStatus.PROVING)
check("DORMANT → PROVING when was PROVING", s == CandidateStatus.PROVING)

print(f"\n{passed} passed, {failed} failed.")