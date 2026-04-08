# TheSNMC RustDB local demo entrypoint
from __future__ import annotations

import sqlite3

from decaydb.api import make_server
from decaydb.engine import DecayEngine
from decaydb.models import bootstrap
from decaydb.scheduler import DecayScheduler


def main() -> None:
    tenant_id = "default"
    # Local app database persists across restarts so existing objects remain visible.
    conn = sqlite3.connect("decay.db", check_same_thread=False)
    bootstrap(conn)
    engine = DecayEngine(conn)

    # Keep lifecycle moving in background without auto-seeding demo rows.
    scheduler = DecayScheduler(engine, tenant_id=tenant_id, interval_sec=3.0, shadow_mode=False)
    scheduler.start()

    server = make_server("127.0.0.1", 8080, engine)
    print("\nAPI available at http://127.0.0.1:8080")
    print("Endpoints: PUT /rot/policies, GET /objects/:id, POST /rot/run, GET /rot/state/:id, POST /rot/restore/:id")
    print("Admin UI: http://127.0.0.1:8080/admin")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()

