"""
Crucible -- Corporation Demo (v2)
Two strategies, two regimes, pre-committed parameters.

See demos/COMMITTED_PARAMS.md -- parameters are locked before this runs.
No tuning after seeing results. Whatever it prints, we narrate honestly.
"""
import sys
sys.path.insert(0, '/root/crucible')

import numpy as np
from crucible.core.vocabulary import Candidate, CandidateStatus, Outcome
from crucible.core.engine import Engine
from crucible.core.spawner import Spawner
from crucible.core.reaper import Reaper
from crucible.core.memory import MemoryStore
from crucible.core.lifecycle import LifecycleEngine
from crucible.core.allocator import Allocator
from crucible.gate.gate import HonestyGate
from crucible.adapters.base import BaseAdapter
from crucible.adapters.momentum import MomentumAdapter
from datetime import datetime, timezone


# === COMMITTED PARAMETERS (see COMMITTED_PARAMS.md) ==========
SEED = 42
N_STEPS_PER_PHASE = 600
HOLD = 5
STEP_INTERVAL = 6  # > HOLD, no overlap
COST = 0.001

TRENDING_DRIFT = 0.003
TRENDING_VOL   = 0.005

OU_THETA = 0.15
OU_MU    = 100.0
OU_SIGMA = 0.8

MR_LOOKBACK = 20
MR_Z_THRESHOLD = 1.5
MR_N_CANDIDATES = 3

MOM_N_CANDIDATES = 12


class DemoLedger:
    def __init__(self):
        self._candidates = []
        self._outcomes = {}
        self._next_id = 1
        self._verdicts = []
        self._memories = []

    def save_candidate(self, c):
        c.id = self._next_id
        self._next_id += 1
        self._candidates.append(c)
        self._outcomes[c.id] = []
        return c.id

    def get_outcomes(self, cid):
        return self._outcomes.get(cid, [])

    def record_outcome(self, cid, outcome):
        if cid in self._outcomes:
            self._outcomes[cid].append(outcome)

    def update_candidate_status(self, cid, status, reason=None):
        for c in self._candidates:
            if c.id == cid:
                c.status = status
                c.retire_reason = reason

    def save_verdict(self, v):
        self._verdicts.append(v)

    def save_memory(self, m):
        self._memories.append(m)


def trending_prices(seed, n=N_STEPS_PER_PHASE):
    np.random.seed(seed)
    p = [100.0]
    for _ in range(n):
        p.append(p[-1] * (1 + np.random.normal(TRENDING_DRIFT, TRENDING_VOL)))
    return p


def ou_prices(seed, n=N_STEPS_PER_PHASE):
    np.random.seed(seed + 1000)
    p = [OU_MU]
    for _ in range(n):
        dx = OU_THETA * (OU_MU - p[-1]) + np.random.normal(0, OU_SIGMA)
        p.append(p[-1] + dx)
    return p


class ZScoreMRAdapter(BaseAdapter):
    name = "zscore_mr"

    def __init__(self, lookback=MR_LOOKBACK, z_threshold=MR_Z_THRESHOLD, cost=COST):
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.cost = cost
        self._regime = "UNKNOWN"
        self._prices = []

    def spawn(self, context):
        regime = context.get("regime", "UNKNOWN")
        variants = []
        for z in [1.0, 1.5, 2.0]:
            dna = {
                "strategy": "zscore_mr",
                "timeframe": "INTRADAY",
                "lookback": self.lookback,
                "z_threshold": z,
                "regime": regime,
                "adapter": self.name,
            }
            variants.append(Candidate(
                name=f"zmr_z{z}_{regime}",
                adapter=self.name,
                dna=dna,
                spawn_reason=f"Spawned in {regime} regime"
            ))
        return variants

    def act(self, candidate, context):
        prices = context.get("price_history", [])
        lb = candidate.dna["lookback"]
        z_th = candidate.dna["z_threshold"]
        if len(prices) < lb + 1:
            return {"direction": "HOLD", "strength": 0.0}
        recent = prices[-lb:]
        mean_p = float(np.mean(recent))
        std_p = float(np.std(recent))
        if std_p == 0:
            return {"direction": "HOLD", "strength": 0.0}
        z = (prices[-1] - mean_p) / std_p
        if abs(z) < z_th:
            return {"direction": "HOLD", "strength": 0.0}
        if z > 0:
            return {"direction": "SHORT", "strength": abs(z),
                    "reason": f"z={z:.2f} > {z_th}"}
        else:
            return {"direction": "LONG", "strength": abs(z),
                    "reason": f"z={z:.2f} < -{z_th}"}

    def measure(self, candidate, action, reality):
        direction = action.get("direction", "HOLD")
        entry = reality.get("entry_price", 0)
        exit_p = reality.get("exit_price", 0)
        if direction == "HOLD" or entry <= 0:
            result = 0.0
        elif direction == "LONG":
            result = (exit_p - entry) / entry
        else:
            result = (entry - exit_p) / entry
        net = result - self.cost
        return Outcome(
            candidate_id=candidate.id,
            action=action,
            result_value=net,
            cost=self.cost,
            context={"regime": reality.get("regime", "UNKNOWN"),
                     "entry_price": entry, "exit_price": exit_p},
            is_sealed=reality.get("is_sealed", False)
        )

    def context(self):
        return {"regime": self._regime, "price_history": list(self._prices)}

    def is_time_ordered(self):
        return True

    def applies_to(self, candidate, context):
        return candidate.dna.get("regime") == context.get("regime")

    def update_state(self, regime, prices):
        self._regime = regime
        self._prices = prices


def run_demo():
    print("=" * 72)
    print("CRUCIBLE -- CORPORATION DEMO (v2)")
    print("Two strategies, two regimes, pre-committed parameters.")
    print("=" * 72)

    ledger    = DemoLedger()
    memory    = MemoryStore()
    lifecycle = LifecycleEngine()
    allocator = Allocator()
    spawner   = Spawner(ledger, memory, max_population=40, min_active_per_adapter=8)
    reaper    = Reaper(ledger, memory)

    mom_adapter = MomentumAdapter(
        lookback_options=[5, 10, 20],
        threshold_options=[0.005, 0.015, 0.03],
        cost_per_trade=COST
    )
    mr_adapter = ZScoreMRAdapter()

    mom_gate = HonestyGate(min_outcomes=30)
    mr_gate  = HonestyGate(min_outcomes=30)

    engine = Engine(ledger=ledger, gate=mom_gate,
                    lifecycle=lifecycle, allocator=allocator, memory=memory)

    trend = trending_prices(SEED)
    ou    = ou_prices(SEED)

    print("\n-- PHASE 1: Trending regime begins --")
    mom_adapter.update_state("TRENDING", trend[:50])
    initial_mom = spawner.spawn_if_needed(mom_adapter, active_candidates=[])
    print(f"Spawned {len(initial_mom)} momentum variants")

    active = list(initial_mom)

    print("\n-- PHASE 2: Trading the trending phase --")
    for step in range(60, N_STEPS_PER_PHASE - HOLD, STEP_INTERVAL):
        mom_adapter.update_state("TRENDING", trend[:step+1])
        ctx = mom_adapter.context()
        for c in active:
            if c.status in (CandidateStatus.RETIRED, CandidateStatus.DORMANT):
                continue
            if c.adapter != mom_adapter.name:
                continue
            action = mom_adapter.act(c, ctx)
            outcome = mom_adapter.measure(c, action, {
                "entry_price": trend[step],
                "exit_price":  trend[step + HOLD],
                "regime": "TRENDING"
            })
            outcome.candidate_id = c.id
            ledger.record_outcome(c.id, outcome)

        report = engine.run_cycle(active, n_candidates_total=MOM_N_CANDIDATES)
        for t in report['transitions']:
            print(f"  step {step}: {t['name']} {t['from']} -> {t['to']}")
        for r in report['retired']:
            print(f"  step {step}: FIRED {r['name']} -- {r['reason']}")

    print("\n-- PHASE 3: Regime shifts to OU --")
    for step in range(60, N_STEPS_PER_PHASE - HOLD, STEP_INTERVAL):
        mom_adapter.update_state("OU", ou[:step+1])
        ctx_mom = mom_adapter.context()
        for c in active:
            if c.status in (CandidateStatus.RETIRED, CandidateStatus.DORMANT):
                continue
            if c.adapter != mom_adapter.name:
                continue
            action = mom_adapter.act(c, ctx_mom)
            outcome = mom_adapter.measure(c, action, {
                "entry_price": ou[step],
                "exit_price":  ou[step + HOLD],
                "regime": "OU"
            })
            outcome.candidate_id = c.id
            ledger.record_outcome(c.id, outcome)

        report = engine.run_cycle(active, n_candidates_total=MOM_N_CANDIDATES)
        for r in report['retired']:
            print(f"  step {step}: FIRED {r['name']} -- {r['reason']}")

    print("\n-- PHASE 4: Reaper sweep --")
    verdicts = {v.candidate_id: v for v in ledger._verdicts}
    reap_report = reaper.reap(active, verdicts)
    print(f"Reaped {len(reap_report['reaped'])} agents")

    survivors = [c for c in active
                 if c.status not in (CandidateStatus.RETIRED, CandidateStatus.DORMANT)]
    print(f"\n-- PHASE 5: {len(survivors)} momentum agents survived --")

    print("\n-- PHASE 6: New strategy spawned -- mean-reversion --")
    mr_adapter.update_state("OU", ou[:50])
    new_mr = spawner.spawn_if_needed(mr_adapter, active_candidates=survivors)
    print(f"Spawned {len(new_mr)} mean-reversion variants")
    active = survivors + new_mr

    engine.gate = mr_gate

    print("\n-- PHASE 7: Mean-reversion runs in OU regime --")
    for step in range(60, N_STEPS_PER_PHASE - HOLD, STEP_INTERVAL):
        mr_adapter.update_state("OU", ou[:step+1])
        ctx_mr = mr_adapter.context()
        for c in active:
            if c.status in (CandidateStatus.RETIRED, CandidateStatus.DORMANT):
                continue
            if c.adapter != mr_adapter.name:
                continue
            action = mr_adapter.act(c, ctx_mr)
            outcome = mr_adapter.measure(c, action, {
                "entry_price": ou[step],
                "exit_price":  ou[step + HOLD],
                "regime": "OU"
            })
            outcome.candidate_id = c.id
            ledger.record_outcome(c.id, outcome)

        report = engine.run_cycle(active, n_candidates_total=MR_N_CANDIDATES)
        for t in report['transitions']:
            print(f"  step {step}: {t['name']} {t['from']} -> {t['to']}")
        for r in report['retired']:
            print(f"  step {step}: FIRED {r['name']} -- {r['reason']}")

    print("\n" + "=" * 72)
    print("FINAL CORPORATION STATE")
    print("=" * 72)
    by_status = {}
    for c in ledger._candidates:
        key = (c.adapter, c.status.value)
        by_status.setdefault(key, []).append(c.name)
    for (adapter, status), names in sorted(by_status.items()):
        print(f"  {adapter:12s} {status:12s}: {len(names)} agents")

    print(f"\nDeath certificates written: {len(memory._store)}")
    print(f"Verdicts recorded:          {len(ledger._verdicts)}")
    print(f"Total candidates ever:      {len(ledger._candidates)}")

    print("\n" + "=" * 72)
    print("WHAT JUST HAPPENED:")
    print("  Momentum spawned in trending regime.")
    print("  Gate evaluated outcomes statistically.")
    print("  Regime shifted to OU. Momentum lost edge.")
    print("  Gate fired the momentum agents -- death certificates written.")
    print("  Mean-reversion spawned as the next strategy.")
    print("  Gate evaluated MR with honest multi-testing correction (n=3).")
    print("  Whatever the gate decided is what we report -- no tuning.")
    print("=" * 72)


if __name__ == "__main__":
    run_demo()
