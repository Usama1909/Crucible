# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Crucible** is a domain-agnostic evolutionary engine that answers one question: *real edge or lucky edge?* Candidates are spawned, evaluated by a statistical gate (the Honesty Gate), cycled through a lifecycle, allocated budget proportional to their proven edge, and eventually retired. Death certificates are written to memory so the next generation learns from the dead.

The engine is domain-blind — it never mentions finance, trading, or A/B testing. Adapters plug in the domain-specific logic.

## Running Tests

Tests are plain Python scripts, not pytest — run them directly:

```bash
python3 tests/test_engine.py
python3 tests/test_lifecycle.py
python3 tests/test_gate.py
python3 tests/test_spawner.py
python3 tests/test_reaper.py
python3 tests/test_allocator.py
python3 tests/test_momentum_adapter.py
```

Each script prints `N passed, 0 failed.` on success. No test framework is installed; each file uses its own `check(desc, condition)` helper. Tests use a `MockLedger` — no database required.

## Installation

```bash
pip install -e .
```

Dependencies: `psycopg2-binary`, `numpy`, `scipy`, `pandas`, `pyyaml`.

## Database

The engine's `Ledger` requires PostgreSQL. Schema is in [migrations/001_initial_schema.sql](migrations/001_initial_schema.sql). Tables: `candidates`, `outcomes`, `verdicts`, `memory`, `allocations`. Pass a DSN string when constructing `Ledger`.

## Architecture

### Core vocabulary (`crucible/core/vocabulary.py`)
Four domain-blind nouns used everywhere:
- `Candidate` — an agent being tested. Has `dna` (dict), `adapter` (plugin name), `status`, and `budget`.
- `Outcome` — one result. `result_value` is **already net of cost**; never subtract cost again.
- `VerdictRecord` — the gate's ruling on a candidate.
- `Memory` — death certificate written when a candidate retires.

`CandidateStatus` lifecycle: `EMBRYO → PROVING → PROVEN → DEGRADED → RETIRED`. Any state can go `DORMANT` (context mismatch) and wake back.

### Engine loop (`crucible/core/engine.py`)
`Engine.run_cycle()` wires all components: for each candidate, get outcomes → evaluate via gate → transition via lifecycle → allocate budgets → write death certificates for retirements. The engine itself never knows the domain.

### Honesty Gate (`crucible/gate/gate.py`)
Sequential checks for real edge:
1. Enough outcomes (`min_outcomes=30`)
2. Split into train/judge (chronological by default, or use `is_sealed` flag)
3. t-test: `mean > 0` and `p < 0.05`
4. Deflated Sharpe Ratio (DSR) — corrects for multiple comparisons across `n_candidates`. DSR < 0.50 → REJECTED, 0.50–0.95 → UNPROVEN, ≥ 0.95 → candidate passes to stability check
5. Stability: edge must be positive in at least 2 of 3 sub-periods

Stats impl in [crucible/gate/stats.py](crucible/gate/stats.py): Bailey & Lopez de Prado DSR formula.

### Lifecycle state machine (`crucible/core/lifecycle.py`)
`LifecycleEngine.next_status()` drives every transition. Key rules:
- EMBRYO waits until `n_outcomes >= 30`, then moves to PROVING
- DEGRADED gets `max_degraded_strikes=3` chances to recover before RETIRED
- DORMANT stores its pre-dormant status and restores it on wake; if was PROVEN, wakes to DEGRADED for a quick re-check

### Allocator (`crucible/core/allocator.py`)
Budget split: PROVEN agents share performance pool weighted by `mean_return × DSR`; DEGRADED agents share a flat `degraded_fraction=0.25` pool; EMBRYO/PROVING share `exploration_reserve=0.10`. Correlated agents (same `correlation_group` in DNA) share one budget slot. Total always ≤ 1.0.

### Memory (`crucible/core/memory.py`)
`write_death_certificate()` called on retirement. `MemoryStore.spawn_hints()` returns `budget_multiplier` (reduced if similar DNA failed before) and `warnings`. `dna_signature()` hashes only structural keys (`strategy`, `timeframe`, `adapter`) so variants of the same strategy share memory.

### Spawner & Reaper (`crucible/core/spawner.py`, `crucible/core/reaper.py`)
`Spawner.spawn_if_needed()` calls `adapter.spawn()` and filters new candidates through memory hints — if a DNA has died ≥3 times with low multiplier, it's blocked. `Reaper.reap()` writes death certificates for RETIRED candidates and tracks which IDs have already been reaped (idempotent).

### Adapters (`crucible/adapters/`)
Domain plugins. Subclass `BaseAdapter` and implement:
- `spawn(context)` — generate `Candidate` list
- `act(candidate, context)` — take action, return action dict
- `measure(candidate, action, reality)` — return `Outcome` with `result_value` **net of cost**
- `context()` — return current world state
- `is_time_ordered()` — tells the gate whether to use chronological splits
- `applies_to(candidate, context)` — optional; drives DORMANT transitions

`MomentumAdapter` is the reference implementation. DNA keys: `strategy`, `timeframe`, `lookback`, `threshold`, `regime`.

## Key Invariants

- `Outcome.result_value` is always net of cost. Adapters own the cost model. Never subtract cost in the gate or engine.
- DSR requires `n_candidates` to be the total population size being tested, not just active candidates — this drives the multiple-comparisons correction.
- The gate's `judge` set is held out from the training set. The split is chronological unless `is_sealed=True` outcomes are present (then sealed = judge).
- Budget fractions must sum ≤ 1.0; the allocator asserts this.
- `Ledger.save_candidate()` must be called before `append_outcome()` — the outcome FK references candidates.

## Probe Scripts

Scripts in `crucible/` (e.g. `probe_trending.py`, `probe_choppy.py`) are standalone tools for exploring gate behavior on synthetic data. Run directly with `python3 crucible/probe_trending.py`. They're not tests — they print a table of verdicts across seeds.
