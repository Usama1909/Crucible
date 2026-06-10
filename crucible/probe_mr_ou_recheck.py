"""
Re-check MR-OU with the actual number of strategy configs tried.
The previous run used n_candidates=12, which corrects for 11 trials we never made.
"""
import sys
sys.path.insert(0, '/root/crucible')
import numpy as np
from crucible.gate.gate import HonestyGate
from crucible.core.vocabulary import Outcome
from datetime import datetime, timezone

HOLD = 5
STEP = 6
N_STEPS = 1200
COST = 0.001
SEEDS = [42, 7, 13, 99, 123, 2026]


def ou_prices(seed, theta=0.15, mu=100.0, sigma=0.8, n=N_STEPS):
    np.random.seed(seed)
    p = [mu]
    for _ in range(n):
        dx = theta * (mu - p[-1]) + np.random.normal(0, sigma)
        p.append(p[-1] + dx)
    return p


def run_zscore_mr(prices, lookback=20, z_threshold=1.5):
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


def adjudicate(returns, seed, n_candidates):
    if len(returns) < 30:
        return {'seed': seed, 'n': len(returns), 'verdict': 'TOO_FEW',
                'sharpe': None, 'dsr': None}
    outcomes = [Outcome(candidate_id=1, action={}, result_value=r, cost=COST,
                       context={}, is_sealed=False,
                       ts=datetime.now(timezone.utc)) for r in returns]
    gate = HonestyGate(min_outcomes=30)
    verdict = gate.evaluate(candidate_id=1, outcomes=outcomes, n_candidates=n_candidates)
    arr = np.array(returns)
    return {
        'seed': seed,
        'n': len(returns),
        'sharpe': float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0.0,
        'win_rate': float(sum(1 for r in arr if r > 0) / len(arr)),
        'verdict': verdict.verdict.value if hasattr(verdict.verdict, 'value') else str(verdict.verdict),
        'dsr': verdict.stats.get('dsr', None)
    }


# We tried one MR strategy. Compare 1 vs 12 vs honest "few thresholds tried"
for n_cand in [1, 3, 12]:
    print(f"\nMR in OU with n_candidates={n_cand}")
    print(f"{'Seed':<6}{'N':<5}{'Sharpe':<9}{'WinRate':<10}{'DSR':<9}{'Verdict':<12}")
    print("-" * 60)
    proven = 0
    for seed in SEEDS:
        prices = ou_prices(seed)
        returns = run_zscore_mr(prices)
        r = adjudicate(returns, seed, n_cand)
        if r.get('verdict') == 'TOO_FEW':
            print(f"{r['seed']:<6}{r['n']:<5}TOO_FEW")
            continue
        dsr = f"{r['dsr']:.3f}" if r.get('dsr') is not None else "n/a"
        print(f"{r['seed']:<6}{r['n']:<5}{r['sharpe']:+.3f}   {r['win_rate']:.1%}     {dsr:<9}{r['verdict']:<12}")
        if r['verdict'] == 'PROVEN':
            proven += 1
    print(f"  {proven}/6 PROVEN with n_candidates={n_cand}")