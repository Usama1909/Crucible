"""
Final probe — pre-committed parameters, non-overlapping windows.
No iterating until PROVEN. Run once, accept the verdict.

COMMITTED PARAMETERS (chosen for realism, not for outcome):

  Trending regime: drift=0.003, vol=0.005  (Sharpe ~1.0 is plausible for
                   a trending equity with low cost)
  OU regime:       theta=0.15, mu=100, sigma=0.8  (faster than rates spreads,
                   slower than HF microstructure — pair-trade-like)
  Hold length:     5 steps
  Step interval:   6  (>= hold length, so windows DO NOT overlap)
  Series length:   1200 steps (enough for ~150 non-overlapping trades)
  Seeds:           42, 7, 13, 99, 123, 2026
"""
import sys
sys.path.insert(0, '/root/crucible')
import numpy as np
from crucible.gate.gate import HonestyGate
from crucible.core.vocabulary import Outcome
from datetime import datetime, timezone

# ── Pre-committed parameters ──────────────────────────────
HOLD = 5
STEP = 6   # >= HOLD: no overlap
N_STEPS = 1200
COST = 0.001
SEEDS = [42, 7, 13, 99, 123, 2026]
GATE_MIN_OUTCOMES = 30
N_CANDIDATES = 12   # multiple-testing context


def trending_prices(seed, drift=0.003, vol=0.005, n=N_STEPS):
    np.random.seed(seed)
    p = [100.0]
    for _ in range(n):
        p.append(p[-1] * (1 + np.random.normal(drift, vol)))
    return p


def ou_prices(seed, theta=0.15, mu=100.0, sigma=0.8, n=N_STEPS):
    np.random.seed(seed)
    p = [mu]
    for _ in range(n):
        dx = theta * (mu - p[-1]) + np.random.normal(0, sigma)
        p.append(p[-1] + dx)
    return p


def run_momentum(prices, lookback=10, threshold=0.005):
    """Pure momentum. Non-overlapping windows."""
    returns = []
    for step in range(lookback+1, len(prices)-HOLD, STEP):
        recent = prices[step-lookback:step]
        m = (recent[-1] - recent[0]) / recent[0]
        if abs(m) < threshold:
            continue
        entry = prices[step]
        exit_p = prices[step+HOLD]
        r = (exit_p - entry)/entry if m > 0 else (entry - exit_p)/entry
        returns.append(r - COST)
    return returns


def run_zscore_mr(prices, lookback=20, z_threshold=1.5):
    """Z-score mean-reversion. Non-overlapping windows."""
    returns = []
    for step in range(lookback+1, len(prices)-HOLD, STEP):
        recent = prices[step-lookback:step]
        mean_p = np.mean(recent)
        std_p = np.std(recent)
        if std_p == 0:
            continue
        z = (prices[step] - mean_p) / std_p
        if abs(z) < z_threshold:
            continue
        entry = prices[step]
        exit_p = prices[step+HOLD]
        r = (entry - exit_p)/entry if z > 0 else (exit_p - entry)/entry
        returns.append(r - COST)
    return returns


def adjudicate(returns, seed):
    """Run gate and report stats."""
    if len(returns) < GATE_MIN_OUTCOMES:
        return {'seed': seed, 'n': len(returns), 'verdict': 'TOO_FEW',
                'sharpe': None, 'win_rate': None, 'dsr': None,
                'autocorr_lag1': None}
    
    outcomes = [Outcome(candidate_id=1, action={}, result_value=r, cost=COST,
                       context={}, is_sealed=False,
                       ts=datetime.now(timezone.utc)) for r in returns]
    gate = HonestyGate(min_outcomes=GATE_MIN_OUTCOMES)
    verdict = gate.evaluate(candidate_id=1, outcomes=outcomes, n_candidates=N_CANDIDATES)
    
    # Effective-N check: lag-1 autocorrelation of returns
    arr = np.array(returns)
    if len(arr) > 1 and np.std(arr) > 0:
        ac1 = np.corrcoef(arr[:-1], arr[1:])[0, 1]
    else:
        ac1 = 0.0
    
    return {
        'seed': seed,
        'n': len(returns),
        'sharpe': float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0.0,
        'win_rate': float(sum(1 for r in arr if r > 0) / len(arr)),
        'verdict': verdict.verdict.value if hasattr(verdict.verdict, 'value') else str(verdict.verdict),
        'dsr': verdict.stats.get('dsr', None),
        'autocorr_lag1': float(ac1)
    }


def print_table(title, results):
    print(f"\n{title}")
    print(f"{'Seed':<6}{'N':<5}{'Sharpe':<9}{'WinRate':<10}{'AC(1)':<9}{'DSR':<9}{'Verdict':<12}")
    print("-" * 65)
    for r in results:
        if r.get('verdict') == 'TOO_FEW':
            print(f"{r['seed']:<6}{r['n']:<5}TOO_FEW")
            continue
        dsr = f"{r['dsr']:.3f}" if r.get('dsr') is not None else "n/a"
        ac = f"{r['autocorr_lag1']:+.3f}"
        print(f"{r['seed']:<6}{r['n']:<5}{r['sharpe']:+.3f}   {r['win_rate']:.1%}     {ac:<9}{dsr:<9}{r['verdict']:<12}")


def summary(results):
    """How many PROVEN across seeds, mean Sharpe, mean autocorr."""
    proven = sum(1 for r in results if r.get('verdict') == 'PROVEN')
    valid = [r for r in results if r.get('verdict') not in (None, 'TOO_FEW')]
    if valid:
        mean_sharpe = np.mean([r['sharpe'] for r in valid])
        mean_ac = np.mean([r['autocorr_lag1'] for r in valid])
        print(f"  Summary: {proven}/{len(results)} PROVEN | "
              f"mean Sharpe {mean_sharpe:+.3f} | mean AC(1) {mean_ac:+.3f}")


# ── Four matchups, pre-committed strategy × regime ────────
matchups = [
    ("MOMENTUM in TRENDING (expected: PROVEN)",   trending_prices, run_momentum),
    ("MOMENTUM in OU (expected: REJECTED)",        ou_prices,       run_momentum),
    ("MEAN-REV in TRENDING (expected: REJECTED)",  trending_prices, run_zscore_mr),
    ("MEAN-REV in OU (expected: PROVEN)",          ou_prices,       run_zscore_mr),
]

print("=" * 70)
print("PRE-COMMITTED PROBE — running once, accepting verdict")
print(f"Hold={HOLD} Step={STEP} (no overlap), N_steps={N_STEPS}, Cost={COST}")
print("=" * 70)

for title, price_fn, strategy_fn in matchups:
    results = []
    for seed in SEEDS:
        prices = price_fn(seed)
        returns = strategy_fn(prices)
        results.append(adjudicate(returns, seed))
    print_table(title, results)
    summary(results)