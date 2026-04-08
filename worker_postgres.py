# TheSNMC RustDB background worker entrypoint
from __future__ import annotations

import os
import time

from decaydb.postgres import PostgresDecayEngine, bootstrap_postgres
from decaydb.scheduler import DecayScheduler


def main() -> None:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install psycopg first: pip install psycopg[binary]") from exc

    dsn = os.getenv("RUSTDB_PG_DSN", os.getenv("DECAYDB_PG_DSN", "postgresql://postgres:postgres@localhost:5432/rustdb"))
    shadow_mode = os.getenv("RUSTDB_SHADOW_MODE", os.getenv("DECAYDB_SHADOW_MODE", "0")) == "1"
    interval = float(os.getenv("RUSTDB_TICK_INTERVAL_SEC", os.getenv("DECAYDB_TICK_INTERVAL_SEC", "1.0")))
    tenant_id = os.getenv("RUSTDB_TENANT", os.getenv("DECAYDB_TENANT", "default"))
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    bootstrap_postgres(conn)
    engine = PostgresDecayEngine(conn)
    scheduler = DecayScheduler(engine, tenant_id=tenant_id, interval_sec=interval, shadow_mode=shadow_mode)
    scheduler.start()
    print(f"worker started shadow_mode={shadow_mode} interval={interval}")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        conn.close()


if __name__ == "__main__":
    main()

