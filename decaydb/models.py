"""TheSNMC RustDB SQLite schema bootstrap for decaying records."""

from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rot_policy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    weighted_scan_factor REAL NOT NULL DEFAULT 0.25,
    purge_after_sec INTEGER NOT NULL DEFAULT 30,
    restore_window_sec INTEGER NOT NULL DEFAULT 120,
    UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS object_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    record_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    original_payload TEXT NOT NULL DEFAULT '',
    keep_original_restore INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rot_state (
    object_id INTEGER PRIMARY KEY,
    policy_id INTEGER NOT NULL,
    last_access_at INTEGER NOT NULL,
    current_stage INTEGER NOT NULL DEFAULT 0,
    next_decay_at INTEGER NOT NULL,
    fidelity_score REAL NOT NULL DEFAULT 1.0,
    legal_hold INTEGER NOT NULL DEFAULT 0,
    do_not_decay INTEGER NOT NULL DEFAULT 0,
    restore_available INTEGER NOT NULL DEFAULT 0,
    deleted_at INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (object_id) REFERENCES object_data(id),
    FOREIGN KEY (policy_id) REFERENCES rot_policy(id)
);

CREATE TABLE IF NOT EXISTS rot_artifact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    stage INTEGER NOT NULL,
    artifact_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (object_id) REFERENCES object_data(id)
);

CREATE TABLE IF NOT EXISTS rot_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (object_id) REFERENCES object_data(id)
);

CREATE TABLE IF NOT EXISTS rot_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at INTEGER NOT NULL
);
"""


def bootstrap(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    # Lightweight compatibility migrations for existing local DB files.
    policy_cols = {row[1] for row in conn.execute("PRAGMA table_info(rot_policy)").fetchall()}
    if "purge_after_sec" not in policy_cols:
        conn.execute("ALTER TABLE rot_policy ADD COLUMN purge_after_sec INTEGER NOT NULL DEFAULT 30")
    if "restore_window_sec" not in policy_cols:
        conn.execute("ALTER TABLE rot_policy ADD COLUMN restore_window_sec INTEGER NOT NULL DEFAULT 120")
    state_cols = {row[1] for row in conn.execute("PRAGMA table_info(rot_state)").fetchall()}
    if "deleted_at" not in state_cols:
        conn.execute("ALTER TABLE rot_state ADD COLUMN deleted_at INTEGER NOT NULL DEFAULT 0")
    object_cols = {row[1] for row in conn.execute("PRAGMA table_info(object_data)").fetchall()}
    if "original_filename" not in object_cols:
        conn.execute("ALTER TABLE object_data ADD COLUMN original_filename TEXT NOT NULL DEFAULT ''")
    if "original_payload" not in object_cols:
        conn.execute("ALTER TABLE object_data ADD COLUMN original_payload TEXT NOT NULL DEFAULT ''")
    if "keep_original_restore" not in object_cols:
        conn.execute("ALTER TABLE object_data ADD COLUMN keep_original_restore INTEGER NOT NULL DEFAULT 0")
    conn.commit()

