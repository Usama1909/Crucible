"""
Crucible Shadow Service — observes ARIA, judges strategy cells.
Now SELF-CALIBRATING: each cycle it measures per-regime noise from ARIA's
outcome history, derives gate strictness (bounded + smoothed), feeds it into
the decision layer, and logs the calibration so you can watch it adapt.

Writes:
  crucible_verdicts     original DSR honesty-gate verdict
  crucible_decisions    graded action (regime-aware, self-calibrated)
  crucible_calibration  the strictness chosen per regime, per cycle (audit log)
"""
import time, json, logging, psycopg2
from collections import defaultdict
from crucible.adapters.aria import AriaCellAdapter, ARIA_DB
from crucible.gate.gate import HonestyGate
from crucible.gate.decision import decide
from crucible.gate import calibration as calib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SHADOW] %(message)s")
log = logging.getLogger()
CYCLE_SECONDS = 900

# strictness values persist across cycles (for the smoothing/EMA)
_STRICTNESS_STATE = {}


def aria_kills_cell(dna, kills):
    pref, suff = f"{dna['symbol']}_", f"_{dna['direction']}"
    return any(k.startswith(pref) and k.endswith(suff) for k in kills)


def regime_history(cur):
    """Pull pnl_pct grouped by regime for calibration."""
    cur.execute("""SELECT regime_at_entry, pnl_pct FROM closed_trades
                   WHERE regime_at_entry IS NOT NULL AND pnl_pct IS NOT NULL""")
    by = defaultdict(list)
    for reg, p in cur.fetchall():
        by[reg].append(float(p))
    return by


def write_verdict(cur, cand, vrec, aria_kill):
    neg = vrec.verdict.value == "REJECTED"
    cur.execute("""INSERT INTO crucible_verdicts
        (cell, symbol, direction, regime, verdict, confidence,
         evidence_count, stats, status, agrees_with_kill_list)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [cand.name, cand.dna["symbol"], cand.dna["direction"],
         cand.dna.get("regime"), vrec.verdict.value, vrec.confidence,
         vrec.evidence_count, json.dumps(vrec.stats, default=str),
         cand.status.value, neg == aria_kill])


def write_decision(cur, cand, d):
    cur.execute("""INSERT INTO crucible_decisions
        (cell, symbol, direction, action, confidence, health, trend,
         evidence_count, reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [cand.name, cand.dna["symbol"], cand.dna["direction"],
         d.action, d.confidence, d.health, d.trend, d.n, d.reason])

def write_research_experiment(cur, cand, d):
    """Persist each decision as a research experiment (grows the research graph)."""
    import json as _json
    sym = cand.dna["symbol"]; direction = cand.dna["direction"]
    market = "crypto" if sym in ("BTC","ETH") else "equities"
    features = ["price","regime","sentiment","fear_greed"]
    extra = {"symbol": sym, "direction": direction}
    outcome = "WIN" if (d.trend or 0) > 0 else "LOSS"
    # upsert-ish: one experiment per (symbol,direction), update its latest verdict
    cur.execute("""SELECT id FROM research_experiments
                   WHERE extra->>'symbol'=%s AND extra->>'direction'=%s
                   AND family='momentum' LIMIT 1""", [sym, direction])
    row = cur.fetchone()
    if row:
        cur.execute("""UPDATE research_experiments
            SET verdict=%s, outcome=%s, confidence=%s, evidence_count=%s,
                reason=%s, created_at=now()
            WHERE id=%s""",
            [d.action, outcome, d.confidence, d.n, d.reason, row[0]])
    else:
        cur.execute("""INSERT INTO research_experiments
            (family,domain,market,features,extra,verdict,outcome,confidence,evidence_count,reason)
            VALUES ('momentum','trading',%s,%s,%s,%s,%s,%s,%s,%s)""",
            [market, _json.dumps(features), _json.dumps(extra),
             d.action, outcome, d.confidence, d.n, d.reason])


def write_calibration(cur, strictness, hist):
    import numpy as np
    for regime, s in strictness.items():
        vals = hist.get(regime, [])
        n = len(vals)
        m = float(np.mean(vals)) if vals else None
        sd = float(np.std(vals)) if vals else None
        cur.execute("""INSERT INTO crucible_calibration
            (regime, strictness, sample_n, mean_pnl, std_pnl)
            VALUES (%s,%s,%s,%s,%s)""", [regime, s, n, m, sd])


def heartbeat(cur, n):
    cur.execute("""INSERT INTO crucible_heartbeat (id, last_cycle, cells_evaluated)
                   VALUES (1, NOW(), %s)
                   ON CONFLICT (id) DO UPDATE
                   SET last_cycle=NOW(), cells_evaluated=EXCLUDED.cells_evaluated""", [n])


def main():
    global _STRICTNESS_STATE
    adapter = AriaCellAdapter()
    gate = HonestyGate()
    log.info("Crucible shadow service starting (self-calibrating, cycle=%ss)", CYCLE_SECONDS)
    while True:
        try:
            kills = set(adapter.current_kill_list())
            cands = adapter.load_candidates(min_trades=1)
            ctx = adapter.context()
            current_regime = ctx.get("regime", "NORMAL")
            conn = psycopg2.connect(**ARIA_DB)
            try:
                cur = conn.cursor()

                # 1. SELF-CALIBRATE: measure regime noise -> strictness (smoothed)
                hist = regime_history(cur)
                _STRICTNESS_STATE = calib.calibrate(hist, _STRICTNESS_STATE)
                write_calibration(cur, _STRICTNESS_STATE, hist)
                strict_for_now = _STRICTNESS_STATE.get(current_regime, 1.0)

                v_counts, a_counts, divergences = {}, {}, 0
                for c in cands:
                    outs = adapter.outcomes_for(c)
                    rets = [o.result_value for o in outs]

                    vrec = gate.evaluate(c.id, outs, n_candidates=len(cands))
                    aria_kill = aria_kills_cell(c.dna, kills)
                    write_verdict(cur, c, vrec, aria_kill)
                    v_counts[vrec.verdict.value] = v_counts.get(vrec.verdict.value, 0) + 1
                    if (vrec.verdict.value == "REJECTED") != aria_kill:
                        divergences += 1

                    # decision now uses the LIVE self-calibrated regime
                    d = decide(rets, regime=current_regime)
                    write_decision(cur, c, d)
                    write_research_experiment(cur, c, d)
                    a_counts[d.action] = a_counts.get(d.action, 0) + 1

                heartbeat(cur, len(cands))
                conn.commit()
                log.info("Cycle done. regime=%s strictness=%.3f cells=%s decisions=%s div=%s",
                         current_regime, strict_for_now, len(cands), a_counts, divergences)
            finally:
                conn.close()
        except Exception as e:
            log.error("cycle failed: %s", e)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
