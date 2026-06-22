# Crucible

**Tells you which candidates are real, which are overfit, and which to retire — and why.**

Crucible is a governance engine for populations of candidates — trading
strategies, prompts, model variants, A/B tests, anything that produces
measurable outcomes. It judges each one for *real edge vs. luck*, grades it,
decides what to do with it, and explains the call.

[![tests](https://github.com/Usama1909/Crucible/actions/workflows/test.yml/badge.svg)](https://github.com/Usama1909/Crucible/actions/workflows/test.yml)

---

## Why

You have 100 backtests, or 20 live strategies, or 50 prompt variants. Which have
a real edge? Which are overfit to noise? Which are quietly decaying? Crucible
answers that continuously, with a reason for every verdict — instead of a
spreadsheet and a gut call.

It has run live, in shadow mode, governing capital allocation on a real
multi-asset trading system — judging that system's strategies every 15 minutes.

---

## How it works

Each candidate has a stream of **outcomes** (e.g. per-trade returns). Two layers
run over them:

1. **Honesty gate** — corrects for luck-of-many-tries using the Deflated Sharpe
   Ratio (Bailey & López de Prado, 2014). Only blesses an edge that survives the
   correction.

2. **Decision layer** — a graded, always-actionable read. Confidence grows with
   evidence; a positive mean only counts as edge if it's *statistically
   significant*, so a lucky streak can't fake a winner. Robust to outliers
   (trimmed mean).

Every candidate ends each cycle with one decision:

| Decision    | Meaning                                  |
|-------------|------------------------------------------|
| `LEAVE`     | proven edge — keep backing it            |
| `WATCH`     | not enough signal yet — keep running     |
| `LEAN_AWAY` | weak / declining — reduce exposure       |
| `RETIRE`    | sustained, evidence-backed failure — cut |

### Self-calibrating strictness

Crucible doesn't use hand-tuned thresholds. It **measures the noise in each
regime** (or context) from observed outcomes and derives how strict the gate
should be — stricter where edges are unreliable, looser where they're clean.
The calibration is bounded and smoothed, so it adapts over time without
overreacting to a single bad week.

---

## Install

```bash
git clone https://github.com/Usama1909/Crucible.git
cd crucible
pip install -e .
```

## Use it (CLI)

```bash
crucible scan demos/sample_strategies.csv
```

```
  CANDIDATE          DECISION   CONF  HEALTH     N
  --------------------------------------------------
  momentum_v1        watch      0.37    0.89    10
  noise_v3           watch      0.30    0.54     8
  breakout_v2        reduce     0.37    0.12    10
```

```bash
crucible explain demos/sample_strategies.csv breakout_v2
```

CSV is just `candidate,return` — one row per outcome. Point it at your own data.

## Use it (library)

```python
from crucible.gate.decision import decide

returns = [0.012, -0.004, 0.021, 0.008, -0.011, 0.017]
d = decide(returns, regime="NORMAL")
print(d.action, d.confidence, d.reason)
```

## Plug in your domain

Subclass `BaseAdapter` (see `crucible/adapters/base.py`). Trading, prompt-tuning,
hyperparameter search, A/B testing — the core engine never knows which domain
it's in. `crucible/adapters/momentum.py` is a worked example;
`demos/demo_nontrading.py` judges A/B landing-page variants with zero trading
code.

---

## What's novel

The individual pieces — Deflated Sharpe Ratio, strategy lifecycle, retire-on-decay —
exist in the literature. Crucible's contribution is the **integration**: spawn →
prove → allocate → retire as a reusable, domain-agnostic engine, with
**self-calibrating strictness** and **explanations for every decision**, proven
live on a real system.

---

## Tests

```bash
pytest -q
```

## License

Apache-2.0
