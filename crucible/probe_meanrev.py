import sys
sys.path.insert(0, '/root/crucible')
import numpy as np
from crucible.gate.gate import HonestyGate
from crucible.core.vocabulary import Outcome
from datetime import datetime, timezone

def probe_meanrev(seed, regime, n_steps=400, step_size=3):
    """Mean-reversion: trade against extreme moves, expecting reversal."""
    np.random.seed(seed)
    drift = 0.003 if regime == 'TRENDING' else 0.0
    vol   = 0.005 if regime == 'TRENDING' else 0.015
    prices = [100.0]
    for i in range(n_steps):
        ret = np.random.normal(drift, vol)
        prices.append(prices[-1] * (1 + ret))
    
    # Mean-reversion: look at recent move, trade OPPOSITE direction
    lookback = 10
    threshold = 0.015   # higher threshold — wait for extremes
    cost = 0.001
    returns = []
    
    for step in range(lookback+1, n_steps, step_size):
        recent = prices[step-lookback:step]
        move = (recent[-1] - recent[0]) / recent[0]
        if abs(move) < threshold:
            continue
        entry = prices[step]
        exit_p = prices[min(step+5, len(prices)-1)]
        # OPPOSITE of momentum: if price went up, bet it reverses (SHORT)
        r = (entry - exit_p)/entry if move > 0 else (exit_p - entry)/entry
        returns.append(r - cost)
    
    if len(returns) < 30:
        return {'seed': seed, 'regime': regime, 'n': len(returns), 'verdict': 'TOO_FEW'}
    
    outcomes = [Outcome(candidate_id=1, action={}, result_value=r, cost=cost,
                       context={}, is_sealed=False,
                       ts=datetime.now(timezone.utc)) for r in returns]
    
    gate = HonestyGate(min_outcomes=30)
    verdict = gate.evaluate(candidate_id=1, outcomes=outcomes, n_candidates=12)
    
    return {
        'seed': seed,
        'regime': regime,
        'n': len(returns),
        'sharpe': np.mean(returns)/np.std(returns) if np.std(returns) > 0 else 0,
        'win_rate': sum(1 for r in returns if r > 0)/len(returns),
        'verdict': verdict.verdict.value if hasattr(verdict.verdict, 'value') else str(verdict.verdict),
        'dsr': verdict.stats.get('dsr', None)
    }

for regime in ['TRENDING', 'CHOPPY']:
    print(f"\nMEAN-REVERSION in {regime}")
    print(f"{'Seed':<6}{'N':<6}{'Sharpe':<10}{'WinRate':<10}{'DSR':<10}{'Verdict':<12}")
    print("-" * 60)
    for seed in [42, 7, 13, 99, 123, 2026]:
        r = probe_meanrev(seed, regime)
        if r.get('verdict') == 'TOO_FEW':
            print(f"{r['seed']:<6}{r['n']:<6}TOO_FEW")
            continue
        dsr_str = f"{r['dsr']:.3f}" if r.get('dsr') is not None else "n/a"
        print(f"{r['seed']:<6}{r['n']:<6}{r['sharpe']:.3f}     {r['win_rate']:.1%}      {dsr_str:<10}{r['verdict']:<12}")