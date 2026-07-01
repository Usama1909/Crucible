"""Backfill research_experiments + relations from real closed_trades."""
import psycopg2, json, itertools
from genome import ResearchGenome, similarity

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def market_of(sym):
    return "crypto" if sym in ("BTC","ETH") else "equities"

def family_of(direction):
    return "momentum"

def main():
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("""
        SELECT symbol, direction, regime_at_entry,
               COUNT(*) AS n,
               SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END) AS wins,
               ROUND(AVG(pnl_usd)::numeric,4) AS avg_pnl,
               ROUND(SUM(pnl_usd)::numeric,2) AS total_pnl
        FROM closed_trades
        WHERE symbol IS NOT NULL AND direction IS NOT NULL
        GROUP BY symbol, direction, regime_at_entry
    """)
    cells = cur.fetchall()
    print(f"found {len(cells)} strategy-cells to persist")

    inserted = []
    for sym, direction, regime, n, wins, avg_pnl, total_pnl in cells:
        wr = (wins/n*100) if n else 0
        outcome = "WIN" if (avg_pnl or 0) > 0 else "LOSS"
        # pull Crucible's REAL latest verdict for this symbol+direction
        cur.execute("""SELECT action, confidence, reason FROM crucible_decisions
                       WHERE symbol=%s AND direction=%s ORDER BY cycle_ts DESC LIMIT 1""",
                    (sym, direction))
        cru = cur.fetchone()
        if cru:
            verdict, cru_conf, cru_reason = cru[0], cru[1], cru[2]
        else:
            verdict, cru_conf, cru_reason = "WATCH", None, "no Crucible decision yet"
        g = ResearchGenome(family=family_of(direction), domain="trading",
                           market=market_of(sym), regime=regime,
                           features=["price","regime","sentiment","fear_greed"],
                           extra={"symbol":sym,"direction":direction})
        cur.execute("""INSERT INTO research_experiments
              (family,domain,market,regime,features,extra,verdict,outcome,confidence,evidence_count,reason)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
              (g.family,g.domain,g.market,g.regime,json.dumps(g.features),json.dumps(g.extra),
               verdict,outcome,round(float(cru_conf),3) if cru_conf is not None else round(min(n/50,1.0),3),n,
               (cru_reason or "") + f" | {sym} {direction} {regime}: {n} trades {wr:.1f}% WR"))
        inserted.append((cur.fetchone()[0], g))

    rel_count = 0
    for (id_a, g_a), (id_b, g_b) in itertools.combinations(inserted, 2):
        sim = similarity(g_a, g_b)
        if sim >= 0.5:
            cur.execute("INSERT INTO research_relations (experiment_id,related_id,relation_type,similarity) VALUES (%s,%s,'similar',%s)",(id_a,id_b,sim))
            cur.execute("INSERT INTO research_relations (experiment_id,related_id,relation_type,similarity) VALUES (%s,%s,'similar',%s)",(id_b,id_a,sim))
            rel_count += 2

    conn.commit()
    print(f"inserted {len(inserted)} experiments, {rel_count} relations")
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
