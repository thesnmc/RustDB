# TheSNMC RustDB local demo entrypoint
from __future__ import annotations

import sqlite3
import time

from decaydb.api import make_server
from decaydb.engine import DecayEngine
from decaydb.models import bootstrap
from decaydb.scheduler import DecayScheduler


def print_state(engine: DecayEngine, label: str) -> None:
    tenant_id = "default"
    print(f"\n=== {label} ===")
    for row in engine.list_objects(tenant_id):
        print(
            f"id={row['id']} type={row['record_type']} stage={row['current_stage']} "
            f"deleted={row['deleted']} fidelity={row['fidelity_score']} payload={row['payload']}"
        )


def main() -> None:
    tenant_id = "default"
    # Demo uses a background scheduler thread; allow this connection cross-thread.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    bootstrap(conn)
    engine = DecayEngine(conn)

    log_policy = engine.add_policy(
        tenant_id=tenant_id,
        name="aggressive_log",
        record_type="log",
        stage_one_after_sec=3,
        stage_two_after_sec=6,
        delete_after_sec=9,
        min_retention_sec=1,
        grace_delete_sec=2,
        irreversible=False,
        legal_hold_default=False,
        access_cooldown_sec=1,
        weighted_scan_factor=0.5,
    )
    image_policy = engine.add_policy(
        tenant_id=tenant_id,
        name="aggressive_image",
        record_type="image",
        stage_one_after_sec=3,
        stage_two_after_sec=6,
        delete_after_sec=9,
        min_retention_sec=1,
        grace_delete_sec=2,
        irreversible=False,
        legal_hold_default=False,
        access_cooldown_sec=1,
        weighted_scan_factor=0.5,
    )

    log_id = engine.create_object(
        tenant_id,
        "log",
        "user clicked dashboard then opened billing then exported month end statement with metadata fields",
        log_policy,
    )
    image_id = engine.create_object(tenant_id, "image", "hero_banner_4k.png", image_policy)

    print_state(engine, "initial")
    time.sleep(4)
    engine.decay_tick(tenant_id)
    print_state(engine, "after first decay tick")

    # Access one row to refresh it and prevent further decay.
    refreshed = engine.get_object(tenant_id, log_id, access_weight=1.0)
    print(f"\nrefreshed id={refreshed['id']} payload={refreshed['payload']}")

    time.sleep(3)
    engine.decay_tick(tenant_id)
    print_state(engine, "after second decay tick")

    time.sleep(4)
    engine.decay_tick(tenant_id)
    print_state(engine, "after third decay tick")

    print("\n=== audit log ===")
    for row in engine.audit_log():
        print(
            f"object={row['object_id']} action={row['action']} at={row['created_at']} detail={row['detail']}"
        )

    print("\n=== metrics ===")
    print(engine.metrics_summary(tenant_id))
    print("\n=== policy dsl sample ===")
    print(engine.export_policy_dsl(tenant_id, log_policy))

    scheduler = DecayScheduler(engine, tenant_id=tenant_id, interval_sec=0.5, shadow_mode=True)
    scheduler.start()
    time.sleep(1.2)
    scheduler.stop()

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
        server.server_close()

    # Keep variable used in demo.
    _ = image_id


if __name__ == "__main__":
    main()

