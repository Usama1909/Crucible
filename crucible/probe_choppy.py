import sys
sys.path.insert(0, '/root/crucible')
import numpy as np
from crucible.gate.gate import HonestyGate
from crucible.core.vocabulary import Outcome
from datetime import datetime, timezone

def probe_choppy_momentum(seed, drift=0.0, vol=0.015, n_steps=400, step_size=3):
    """Momentum in choppy market — should fail honestly."""
    np.random.seed(seed)
    prices = [100.0]
    for i in range(n_steps):
        ret = np.random.normal(drift, vol)
        prices.append(prices[-1] * (1 + ret))
    
    lookback = 10
    threshold = 0.005
    cost = 0.001
    returns = []
    
    for step in range(lookback+1, n_steps, step_size):
        recent = prices[step-lookback:step]
        momentum = (recent[-1] - recent[0]) / recent[0]
        if abs(momentum) < threshold:
            continue
        entry = prices[step]
        exit_p = prices[min(step+5, len(prices)-1)]
        r = (exit_p - entry)/entry if momentum > 0 else (entry - exit_p)/entry
        returns.append(r - cost)
    
    if len(returns) < 30:
        return {'seed': seed, 'n': len(returns), 'verdict': 'TOO_FEW'}
    
    outcomes = [Outcome(candidate_id=1, action={}, result_value=r, cost=cost,
                       context={}, is_sealed=False,
                       ts=datetime.now(timezone.utc)) for r in returns]
    
    gate = HonestyGate(min_outcomes=30)
    verdict = gate.evaluate(candidate_id=1, outcomes=outcomes, n_candidates=12)
    
    return {
        'seed': seed,
        'n': len(returns),
        'sharpe': np.mean(returns)/np.std(returns) if np.std(returns) > 0 else 0,
        'win_rate': sum(1 for r in returns if r > 0)/len(returns),
        'verdict': verdict.verdict.value if hasattr(verdict.verdict, 'value') else str(verdict.verdict),
        'dsr': verdict.stats.get('dsr', None)
    }

print("MOMENTUM IN CHOPPY (should fail)")
print(f"{'Seed':<6}{'N':<6}{'Sharpe':<10}{'WinRate':<10}{'DSR':<10}{'Verdict':<12}")
print("-" * 60)
for seed in [42, 7, 13, 99, 123, 2026]:
    r = probe_choppy_momentum(seed)
    if r.get('verdict') == 'TOO_FEW':
        print(f"{r['seed']:<6}{r['n']:<6}{'TOO_FEW':<40}")
        continue
    dsr_str = f"{r['dsr']:.3f}" if r.get('dsr') is not None else "n/a"
    print(f"{r['seed']:<6}{r['n']:<6}{r['sharpe']:.3f}     {r['win_rate']:.1%}      {dsr_str:<10}{r['verdict']:<12}")