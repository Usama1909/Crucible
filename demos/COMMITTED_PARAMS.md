# Corporation Demo — Pre-Committed Parameters

Date committed: 2026-06-07
Committed by:   Usama Fateh Ali

These parameters are locked BEFORE the demo runs. Any tuning after running
the demo is forbidden. If the result is unsatisfying, the narration changes,
not the parameters.

This discipline exists because Crucible's whole pitch is that the gate
catches "I tuned until it said PROVEN." We have to walk the talk on our
own demo or the README has nothing to stand on.

## Price Series

### Trending Regime
- drift:   0.003 per step
- vol:     0.005 per step (Gaussian)
- n_steps: 600
- rationale: realistic equity-like trend with low noise — Sharpe ~1.0 plausible

### OU Regime (mean-reverting)
- theta:   0.15 (pull strength)
- mu:      100.0 (equilibrium)
- sigma:   0.8 (noise)
- n_steps: 600
- rationale: faster than rates spreads, slower than HF microstructure —
             pair-trade-residual-like

## Execution

- hold_steps:    5 (how long each trade is held)
- step_interval: 6 (when next trade can fire — > hold, so NO overlap)
- cost_per_trade: 0.001

## Strategies

### Momentum
- lookback:        10
- threshold:       0.005 (5 bps move required to fire)
- variants tested: 12 (4 lookbacks x 3 thresholds in the adapter)
- n_candidates for gate: 12

### Z-score Mean Reversion
- lookback:        20
- z_threshold:     1.5 (1.5 std from rolling mean required to fire)
- variants tested: 3 (one z-threshold setting tested across multiple seeds —
                     we count this as 3 candidates for the multi-testing
                     correction, the same way the momentum adapter counts
                     its lookback x threshold combos)
- n_candidates for gate: 3

## Gate

- min_outcomes: 30
- per-strategy n_candidates as committed above

## Seed
- demo run seed: 42
- (we know from prior probes the result is similar across {42, 7, 13, 99, 123, 2026})

## Expected outcomes from prior probes

| Strategy   | Regime    | Probe verdict (6 seeds) |
| ---------- | --------- | ----------------------- |
| Momentum   | Trending  | 6/6 PROVEN              |
| Momentum   | OU        | 0/6 PROVEN (REJECTED)   |
| Mean-Rev   | Trending  | 0/6 PROVEN (REJECTED)   |
| Mean-Rev   | OU (n=3)  | 2/6 PROVEN              |

The demo may show different numbers because it runs ONE seed and the demo
runs a full corporation loop (not isolated probes). Whatever it prints, we
narrate honestly.
