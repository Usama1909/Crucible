"""Crucible Ledger — optional Postgres persistence.

psycopg2 is imported lazily, so the core engine, gate, and decision layer all
work with ZERO database dependencies. You only need psycopg2 if you actually
use the Ledger to persist to Postgres:

    pip install psycopg2-binary
"""
from contextlib import contextmanager
from crucible.core.vocabulary import (
    Candidate, Outcome, VerdictRecord, Memory, CandidateStatus
)


def _psy():
    """Lazy import of psycopg2.extras (Json, RealDictCursor)."""
    try:
        import psycopg2.extras
        return psycopg2.extras
    except ImportError as e:
        raise ImportError(
            "Ledger requires psycopg2. Install with: pip install psycopg2-binary"
        ) from e


class Ledger:
    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 10):
        try:
            from psycopg2.pool import ThreadedConnectionPool
        except ImportError as e:
            raise ImportError(
                "Ledger requires psycopg2. Install with: pip install psycopg2-binary"
            ) from e
        self._pool = ThreadedConnectionPool(minconn, maxconn, dsn)

    @contextmanager
    def _conn(self):
        conn = self._pool.getconn()
        try:
            with conn:
                yield conn
        finally:
            self._pool.putconn(conn)

    def save_candidate(self, c: Candidate) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO candidates
                    (name, adapter, dna, status, budget, spawn_reason, born_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (c.name, c.adapter,
                      _psy().Json(c.dna),
                      c.status.value, c.budget,
                      c.spawn_reason, c.born_at))
                c.id = cur.fetchone()[0]
        return c.id

    def append_outcome(self, o: Outcome) -> int:
        assert o.candidate_id is not None, "Save candidate before outcome"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO outcomes
                    (candidate_id, action, result_value, cost, context, is_sealed, ts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (o.candidate_id,
                      _psy().Json(o.action),
                      o.result_value, o.cost,
                      _psy().Json(o.context),
                      o.is_sealed, o.ts))
                o.id = cur.fetchone()[0]
        return o.id

    def get_outcomes(self, candidate_id: int, sealed_only: bool = False):
        with self._conn() as conn:
            with conn.cursor(cursor_factory=_psy().RealDictCursor) as cur:
                q = "SELECT * FROM outcomes WHERE candidate_id=%s"
                if sealed_only:
                    q += " AND is_sealed=TRUE"
                q += " ORDER BY ts ASC"
                cur.execute(q, (candidate_id,))
                rows = cur.fetchall()
        return [Outcome(
            candidate_id=r["candidate_id"],
            action=r["action"],
            result_value=float(r["result_value"]),
            cost=float(r["cost"]),
            context=r["context"],
            is_sealed=r["is_sealed"],
            id=r["id"], ts=r["ts"]
        ) for r in rows]

    def update_candidate_status(self, candidate_id: int, status: CandidateStatus, reason: str = None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status == CandidateStatus.RETIRED:
                    cur.execute("UPDATE candidates SET status=%s, retire_reason=%s, retired_at=now() WHERE id=%s",
                        (status.value, reason, candidate_id))
                else:
                    cur.execute("UPDATE candidates SET status=%s WHERE id=%s",
                        (status.value, candidate_id))

    def save_verdict(self, v: VerdictRecord) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO verdicts
                    (candidate_id, verdict, confidence, stats, evidence_count, evaluated_at)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """, (v.candidate_id, v.verdict.value, v.confidence,
                      _psy().Json(v.stats), v.evidence_count, v.evaluated_at))
                v.id = cur.fetchone()[0]
        return v.id

    def save_memory(self, m: Memory) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO memory
                    (dna_signature, adapter, what_worked, what_failed,
                     final_stats, sample_size, confidence, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (m.dna_signature, m.adapter, m.what_worked, m.what_failed,
                      _psy().Json(m.final_stats),
                      m.sample_size, m.confidence, m.created_at))
                m.id = cur.fetchone()[0]
        return m.id
