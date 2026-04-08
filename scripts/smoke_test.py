# TheSNMC RustDB smoke test
from __future__ import annotations

import json
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8080"
API_KEY = "devkey"


def request(path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, str]:
    data = None
    headers = {"X-API-Key": API_KEY}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def main() -> None:
    with urllib.request.urlopen(f"{BASE}/healthz", timeout=8) as resp:
        if resp.status != 200:
            raise SystemExit("healthz failed")

    status, body = request(
        "/rot/policies",
        method="PUT",
        payload={
            "name": "smoke_policy",
            "policy": {
                "record_type": "log",
                "stage_one_after_sec": 3,
                "stage_two_after_sec": 6,
                "delete_after_sec": 9,
            },
        },
    )
    if status != 200:
        raise SystemExit(f"policy upsert failed: {status} {body}")
    policy_id = json.loads(body)["policy_id"]

    status, body = request(
        "/objects",
        method="POST",
        payload={"record_type": "log", "payload": "smoke payload", "policy_id": policy_id},
    )
    if status != 201:
        raise SystemExit(f"object create failed: {status} {body}")
    object_id = json.loads(body)["object_id"]

    status, body = request("/rot/run", method="POST")
    if status != 200:
        raise SystemExit(f"tick failed: {status} {body}")

    status, body = request(f"/rot/state/{object_id}")
    if status != 200:
        raise SystemExit(f"state failed: {status} {body}")
    state = json.loads(body)
    if state["current_stage"] < 1:
        raise SystemExit(f"unexpected stage: {state['current_stage']}")

    print("SMOKE TEST PASS")
    print(json.dumps({"object_id": object_id, "current_stage": state["current_stage"]}, indent=2))


if __name__ == "__main__":
    main()
