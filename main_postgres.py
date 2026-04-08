# TheSNMC RustDB PostgreSQL API entrypoint
from __future__ import annotations

import os

from decaydb.api import make_server
from decaydb.postgres import PostgresDecayEngine, bootstrap_postgres


def main() -> None:
    tenant_id = os.getenv("RUSTDB_TENANT", os.getenv("DECAYDB_TENANT", "default"))
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install psycopg first: pip install psycopg[binary]") from exc

    dsn = os.getenv("RUSTDB_PG_DSN", os.getenv("DECAYDB_PG_DSN", "postgresql://postgres:postgres@localhost:5432/rustdb"))
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    bootstrap_postgres(conn)
    engine = PostgresDecayEngine(conn)

    policy_id = engine.upsert_policy(
        tenant_id=tenant_id,
        name="pg_log_policy",
        payload={
            "record_type": "log",
            "stage_one_after_sec": 30,
            "stage_two_after_sec": 60,
            "delete_after_sec": 120,
            "min_retention_sec": 10,
            "grace_delete_sec": 30,
            "irreversible": False,
            "legal_hold_default": False,
            "access_cooldown_sec": 2,
            "weighted_scan_factor": 0.5,
        },
    )
    print(f"policy ready id={policy_id}")

    server = make_server("127.0.0.1", 8081, engine)
    print("Postgres API available at http://127.0.0.1:8081")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        conn.close()


if __name__ == "__main__":
    main()

