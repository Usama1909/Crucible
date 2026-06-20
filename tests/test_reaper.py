"""Test: Reaper writes death certificates for retired candidates only."""
from crucible.core.vocabulary import Candidate, CandidateStatus, VerdictRecord
from crucible.core.reaper import Reaper
from crucible.core.memory import MemoryStore


class MockLedger:
    def __init__(self):
        self._memories = []
    def save_memory(self, mem):
        self._memories.append(mem)


def make_candidate(id, status, retire_reason=None):
    c = Candidate(name=f"agent_{id}", adapter="test",
                  dna={"strategy": "momentum", "regime": "NORMAL"}, id=id)
    c.status = status
    c.retire_reason = retire_reason
    return c


def make_verdict(candidate_id, sample_size=200):
    return VerdictRecord(
        candidate_id=candidate_id,
        verdict='REJECTED',
        confidence=0.05,
        stats={'dsr': 0.2, 'mean_return': -0.001},
        evidence_count=sample_size,
    )


def check(desc, condition):
    assert condition, f"FAIL: {desc}"


def test_reaper():
    ledger = MockLedger()
    memory = MemoryStore()
    reaper = Reaper(ledger, memory)
    retired = make_candidate(1, CandidateStatus.RETIRED, "rejected by gate")
    verdicts = {1: make_verdict(1)}
    report = reaper.reap([retired], verdicts)
    check("retired candidate reaped", len(report['reaped']) == 1)
    check("death cert in memory", len(memory._store) == 1)
    check("death cert in ledger", len(ledger._memories) == 1)

    ledger2 = MockLedger()
    memory2 = MemoryStore()
    reaper2 = Reaper(ledger2, memory2)
    proven = make_candidate(2, CandidateStatus.PROVEN)
    proving = make_candidate(3, CandidateStatus.PROVING)
    report2 = reaper2.reap([proven, proving], {2: make_verdict(2), 3: make_verdict(3)})
    check("doesn't reap PROVEN", len(report2['reaped']) == 0)
    check("no certs for active agents", len(memory2._store) == 0)

    ledger3 = MockLedger()
    memory3 = MemoryStore()
    reaper3 = Reaper(ledger3, memory3)
    dead = make_candidate(4, CandidateStatus.RETIRED, "too lucky")
    report3a = reaper3.reap([dead], {4: make_verdict(4)})
    report3b = reaper3.reap([dead], {4: make_verdict(4)})
    check("first reap writes cert", len(report3a['reaped']) == 1)
    check("second reap skips", len(report3b['reaped']) == 0)
    check("only one cert total", len(memory3._store) == 1)
    check("already_reaped True", reaper3.already_reaped(4) == True)

    ledger4 = MockLedger()
    memory4 = MemoryStore()
    reaper4 = Reaper(ledger4, memory4)
    dead_no_verdict = make_candidate(5, CandidateStatus.RETIRED)
    report4 = reaper4.reap([dead_no_verdict], verdicts={})
    check("retired without verdict doesn't crash", len(report4['errors']) == 0)
    check("retired without verdict skipped", 5 in report4['skipped'])

    ledger5 = MockLedger()
    memory5 = MemoryStore()
    reaper5 = Reaper(ledger5, memory5)
    batch = [
        make_candidate(10, CandidateStatus.RETIRED, "lucky"),
        make_candidate(11, CandidateStatus.PROVEN),
        make_candidate(12, CandidateStatus.RETIRED, "drift"),
        make_candidate(13, CandidateStatus.EMBRYO),
    ]
    verdicts_batch = {10: make_verdict(10), 12: make_verdict(12)}
    report5 = reaper5.reap(batch, verdicts_batch)
    check("mixed batch reaps exactly 2", len(report5['reaped']) == 2)
    check("mixed batch leaves 2 alive", len(memory5._store) == 2)
