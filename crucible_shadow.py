"""
Crucible Shadow Service — observes ARIA, judges strategy cells.
Writes BOTH:
  crucible_verdicts   — original DSR honesty-gate verdict (history + divergence)
  crucible_decisions  — graded "breathing" decision (LEAVE/WATCH/LEAN_AWAY/RETIRE)
Read-only against trading tables. Zero authority.
"""
import time, json, logging, psycopg2
from crucible.adapters.aria import AriaCellAdapter, ARIA_DB
from crucible.gate.gate import HonestyGate
from crucible.gate.decision import decide

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SHADOW] %(message)s")
log = logging.getLogger()
CYCLE_SECONDS = 900  # 15 min


def kill_key(dna):
    # ARIA's kill list keys are symbol_regime_direction. With symbol x direction
    # cells there's no regime, so we match on symbol+direction prefix instead.
    return f"{dna['symbol']}_{dna['direction']}"


def aria_kills_cell(dna, kills):
    # True if ARIA's kill list contains any entry for this symbol+direction.
    pref = f"{dna['symbol']}_"
    suff = f"_{dna['direction']}"
    return any(k.startswith(pref) and k.endswith(suff) for k in kills)


def write_verdict(cur, cand, vrec, aria_kill):
    crucible_negative = vrec.verdict.value == "REJECTED"
    cur.execute("""INSERT INTO crucible_verdicts
        (cell, symbol, direction, regime, verdict, confidence,
         evidence_count, stats, status, agrees_with_kill_list)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [cand.name, cand.dna["symbol"], cand.dna["direction"],
         cand.dna.get("regime"), vrec.verdict.value, vrec.confidence,
         vrec.evidence_count, json.dumps(vrec.stats, default=str),
         cand.status.value, crucible_negative == aria_kill])


def write_decision(cur, cand, d):
    cur.execute("""INSERT INTO crucible_decisions
        (cell, symbol, direction, action, confidence, health, trend,
         evidence_count, reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [cand.name, cand.dna["symbol"], cand.dna["direction"],
         d.action, d.confidence, d.health, d.trend, d.n, d.reason])


def heartbeat(cur, n):
    cur.execute("""INSERT INTO crucible_heartbeat (id, last_cycle, cells_evaluated)
                   VALUES (1, NOW(), %s)
                   ON CONFLICT (id) DO UPDATE
                   SET last_cycle=NOW(), cells_evaluated=EXCLUDED.cells_evaluated""", [n])


def main():
    adapter = AriaCellAdapter()           # symbol x direction (default)
    gate    = HonestyGate()
    log.info("Crucible shadow service starting (cycle=%ss)", CYCLE_SECONDS)
    while True:
        try:
            kills = set(adapter.current_kill_list())
            cands = adapter.load_candidates(min_trades=1)
            conn = psycopg2.connect(**ARIA_DB)
            try:
                cur = conn.cursor()
                v_counts, a_counts = {}, {}
                divergences = 0
                for c in cands:
                    outs = adapter.outcomes_for(c)
                    rets = [o.result_value for o in outs]

                    # 1. original honesty-gate verdict (history + divergence)
                    vrec = gate.evaluate(c.id, outs, n_candidates=len(cands))
                    aria_kill = aria_kills_cell(c.dna, kills)
                    write_verdict(cur, c, vrec, aria_kill)
                    v_counts[vrec.verdict.value] = v_counts.get(vrec.verdict.value, 0) + 1
                    crucible_neg = vrec.verdict.value == "REJECTED"
                    if crucible_neg != aria_kill:
                        divergences += 1

                    # 2. breathing decision (always actionable)
                    d = decide(rets)
                    write_decision(cur, c, d)
                    a_counts[d.action] = a_counts.get(d.action, 0) + 1

                heartbeat(cur, len(cands))
                conn.commit()
                log.info("Cycle done. cells=%s verdicts=%s decisions=%s divergences=%s",
                         len(cands), v_counts, a_counts, divergences)
            finally:
                conn.close()
        except Exception as e:
            log.error("cycle failed: %s", e)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
