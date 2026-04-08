"""TheSNMC RustDB PostgreSQL backend."""

from __future__ import annotations

import time
from typing import Any, Optional

from decaydb.engine import DecayEngine

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rot_policy (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    record_type TEXT NOT NULL,
    stage_one_after_sec INTEGER NOT NULL,
    stage_two_after_sec INTEGER NOT NULL,
    delete_after_sec INTEGER NOT NULL,
    min_retention_sec INTEGER NOT NULL DEFAULT 0,
    grace_delete_sec INTEGER NOT NULL DEFAULT 0,
    irreversible INTEGER NOT NULL DEFAULT 0,
    legal_hold_default INTEGER NOT NULL DEFAULT 0,
    access_cooldown_sec INTEGER NOT NULL DEFAULT 0,
    weighted_scan_factor DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    purge_after_sec INTEGER NOT NULL DEFAULT 30,
    restore_window_sec INTEGER NOT NULL DEFAULT 120,
    UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS object_data (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    record_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rot_state (
    object_id BIGINT PRIMARY KEY REFERENCES object_data(id),
    policy_id BIGINT NOT NULL REFERENCES rot_policy(id),
    last_access_at INTEGER NOT NULL,
    current_stage INTEGER NOT NULL DEFAULT 0,
    next_decay_at INTEGER NOT NULL,
    fidelity_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    legal_hold INTEGER NOT NULL DEFAULT 0,
    do_not_decay INTEGER NOT NULL DEFAULT 0,
    restore_available INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rot_artifact (
    id BIGSERIAL PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES object_data(id),
    stage INTEGER NOT NULL,
    artifact_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rot_audit_log (
    id BIGSERIAL PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES object_data(id),
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rot_metrics (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    recorded_at INTEGER NOT NULL
);
"""


def bootstrap_postgres(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(PG_SCHEMA_SQL)
    conn.commit()


class PostgresDecayEngine(DecayEngine):
    """Keeps same API as DecayEngine, but uses PG locking for candidate selection."""

    def decay_tick(
        self, tenant_id: str, now: Optional[int] = None, limit: int = 50, shadow_mode: bool = False
    ) -> int:
        now = now or int(time.time())
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.object_id, s.policy_id, s.current_stage, s.last_access_at, s.version, s.legal_hold,
                       s.do_not_decay, d.record_type, d.payload, d.created_at
                FROM rot_state s
                JOIN object_data d ON d.id = s.object_id
                WHERE d.deleted = 0 AND s.next_decay_at <= %s AND d.tenant_id = %s
                ORDER BY s.next_decay_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (now, tenant_id, limit),
            )
            rows = cur.fetchall()

        changed = 0
        for row in rows:
            if self._apply_next_stage(tenant_id, row, now, shadow_mode=shadow_mode):
                changed += 1
        self._metric(tenant_id, "decay_tick_changed", float(changed), now)
        self.conn.commit()
        return changed

