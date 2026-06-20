"""
Crucible — ARIA Adapter
Candidate = strategy cell, defined by configurable grouping columns.
Outcome   = closed trade in that cell (result = pnl_pct).
Context   = ARIA's current meta_regime. Read-only against aria_db.
"""
import os
import json
import zlib
import psycopg2
from typing import Dict, Any, List
from dotenv import load_dotenv
from crucible.core.vocabulary import Candidate, CandidateStatus, Outcome

load_dotenv("/root/.env")
ARIA_DB = {"host": os.getenv("ARIA_DB_HOST", "localhost"), "port": 5432,
           "dbname": "aria_db", "user": "postgres",
           "password": os.getenv("ARIA_DB_PASSWORD", "")}

# Maps logical grouping keys -> actual DB columns. Add here to support new keys.
_COL_MAP = {"symbol": "symbol", "direction": "direction", "regime": "regime_at_entry"}


def _cell_id(name: str) -> int:
    return zlib.crc32(name.encode())


class AriaCellAdapter:
    name = "aria_cells"

    def __init__(self, group_by=("symbol", "direction"), min_trades: int = 1):
        # group_by defines what a "strategy cell" is. Default symbol x direction
        # (coarser, more data per cell). Pass ("symbol","direction","regime")
        # for fine-grained once enough trades exist.
        bad = [k for k in group_by if k not in _COL_MAP]
        if bad:
            raise ValueError(f"unknown group_by keys: {bad}; valid: {list(_COL_MAP)}")
        self.group_by = list(group_by)
        self.min_trades = min_trades
        self._cols = [_COL_MAP[k] for k in self.group_by]

    def _db(self):
        return psycopg2.connect(**ARIA_DB)

    def load_candidates(self, min_trades: int = None) -> List[Candidate]:
        mt = self.min_trades if min_trades is None else min_trades
        cols = ", ".join(self._cols)
        not_null = " AND ".join(f"{c} IS NOT NULL" for c in self._cols)
        conn = self._db()
        try:
            cur = conn.cursor()
            cur.execute(f"""SELECT {cols}, COUNT(*) FROM closed_trades
                            WHERE {not_null}
                            GROUP BY {cols} HAVING COUNT(*) >= %s""", [mt])
            out = []
            for row in cur.fetchall():
                vals = row[:-1]
                dna = {k: v for k, v in zip(self.group_by, vals)}
                cname = "_".join(str(v) for v in vals)
                out.append(Candidate(
                    name=cname, adapter=self.name, id=_cell_id(cname),
                    dna=dna, status=CandidateStatus.EMBRYO,
                    spawn_reason="bootstrapped from closed_trades history"))
            return out
        finally:
            conn.close()

    def outcomes_for(self, candidate: Candidate) -> List[Outcome]:
        d = candidate.dna
        where = " AND ".join(f"{_COL_MAP[k]}=%s" for k in self.group_by)
        params = [d[k] for k in self.group_by]
        conn = self._db()
        try:
            cur = conn.cursor()
            cur.execute(f"""SELECT pnl_pct, exit_time FROM closed_trades
                            WHERE {where} ORDER BY exit_time ASC""", params)
            return [Outcome(candidate_id=candidate.id,
                            action=dict(d), result_value=float(p), cost=0.0,
                            context=dict(d), ts=t)
                    for p, t in cur.fetchall() if p is not None]
        finally:
            conn.close()

    def context(self) -> Dict[str, Any]:
        conn = self._db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM aria_config WHERE key='meta_regime' LIMIT 1")
            row = cur.fetchone()
            return {"regime": row[0].strip() if row else "UNKNOWN"}
        finally:
            conn.close()

    def applies_to(self, candidate: Candidate, ctx: Dict[str, Any]) -> bool:
        # If this cell isn't regime-specific, it always applies.
        if "regime" not in candidate.dna:
            return True
        return candidate.dna.get("regime") == ctx.get("regime")

    def current_kill_list(self) -> List[str]:
        conn = self._db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM aria_config WHERE key='signal_feedback' LIMIT 1")
            row = cur.fetchone()
            if not row:
                return []
            return [k.get("key") for k in json.loads(row[0]).get("KILL", [])]
        finally:
            conn.close()
