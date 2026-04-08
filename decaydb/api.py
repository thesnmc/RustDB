"""TheSNMC RustDB HTTP API surface."""

from __future__ import annotations

import json
import os
import base64
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from decaydb.engine import DecayEngine
from decaydb.storage import save_binary


class DecayApiHandler(BaseHTTPRequestHandler):
    @staticmethod
    def _infer_record_type(filename: str, mime_type: str | None) -> str:
        lowered = filename.lower()
        mime = (mime_type or "").lower()
        if mime.startswith("image/") or lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return "image_file"
        if lowered.endswith((".csv", ".xlsx", ".xls", ".xlsm")):
            return "spreadsheet_file"
        if lowered.endswith(".pdf"):
            return "pdf_file"
        if lowered.endswith((".doc", ".docx", ".ppt", ".pptx")):
            return "document_file"
        if mime.startswith("text/") or lowered.endswith((".txt", ".md", ".log", ".csv", ".json")):
            return "text_file"
        return "binary_file"
    engine: DecayEngine
    api_keys: dict[str, str]

    def _tenant_from_auth(self) -> str | None:
        key = self.headers.get("X-API-Key")
        if not key:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            key = (
                query.get("api_key")
                or query.get("apiKey")
                or query.get("x_api_key")
                or query.get("x-api-key")
                or [None]
            )[0]
        if not key:
            return None
        return self.api_keys.get(str(key).strip())

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        tenant_id = self._tenant_from_auth()
        if not tenant_id:
            self._json(401, {"error": "unauthorized"})
            return
        if parsed.path != "/rot/policies":
            self._json(404, {"error": "not_found"})
            return
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        name = data["name"]
        policy_id = self.engine.upsert_policy(tenant_id=tenant_id, name=name, payload=data["policy"])
        self._json(200, {"policy_id": policy_id})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json(200, {"ok": True})
            return
        if parsed.path == "/admin":
            html = Path(__file__).with_name("admin.html").read_text(encoding="utf-8")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        tenant_id = self._tenant_from_auth()
        if not tenant_id:
            self._json(401, {"error": "unauthorized"})
            return
        if parsed.path == "/rot/policies":
            self._json(200, {"policies": self.engine.list_policies(tenant_id)})
            return
        if parsed.path == "/objects":
            rows = self.engine.list_objects(tenant_id)
            self._json(
                200,
                {
                    "objects": [
                        {
                            "id": int(r["id"]),
                            "record_type": r["record_type"],
                            "filename": Path(str(r["payload"])).name if str(r["payload"]).find("/") >= 0 or str(r["payload"]).find("\\") >= 0 else "",
                            "original_filename": r["original_filename"] if "original_filename" in r.keys() else "",
                            "current_size_bytes": (Path(str(r["payload"])).stat().st_size if Path(str(r["payload"])).exists() and Path(str(r["payload"])).is_file() else len(str(r["payload"]))),
                            "deleted": bool(r["deleted"]),
                            "current_stage": int(r["current_stage"]),
                            "fidelity_score": float(r["fidelity_score"]),
                            "legal_hold": bool(r["legal_hold"]),
                            "do_not_decay": bool(r["do_not_decay"]),
                        }
                        for r in rows
                    ]
                },
            )
            return
        if parsed.path.startswith("/objects/"):
            if parsed.path.endswith("/file"):
                object_id = int(parsed.path.split("/")[-2])
                row = self.engine.conn.execute(
                    """
                    SELECT d.payload, d.deleted
                    FROM object_data d
                    WHERE d.id = ? AND d.tenant_id = ?
                    """,
                    (object_id, tenant_id),
                ).fetchone()
                if not row:
                    self._json(404, {"error": "not_found"})
                    return
                if int(row["deleted"]) == 1:
                    self._json(400, {"error": "object_deleted"})
                    return
                payload = str(row["payload"])
                path = Path(payload)
                if not path.exists() or not path.is_file():
                    # Non-file payloads (e.g. log/text rows) are returned as plain text preview.
                    data = payload.encode("utf-8", errors="ignore")
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", 'inline; filename="payload.txt"')
                    self.end_headers()
                    self.wfile.write(data)
                    return
                suffix = path.suffix.lower()
                content_type = "application/octet-stream"
                if suffix in {".jpg", ".jpeg"}:
                    content_type = "image/jpeg"
                elif suffix == ".png":
                    content_type = "image/png"
                elif suffix == ".webp":
                    content_type = "image/webp"
                elif suffix == ".gif":
                    content_type = "image/gif"
                elif suffix in {".txt", ".log", ".md", ".json", ".csv"}:
                    content_type = "text/plain; charset=utf-8"
                data = path.read_bytes()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
                self.end_headers()
                self.wfile.write(data)
                return
            object_id = int(parsed.path.rsplit("/", 1)[1])
            query = parse_qs(parsed.query)
            weight = float(query.get("weight", ["1.0"])[0])
            row = self.engine.get_object(tenant_id, object_id, access_weight=weight)
            if not row:
                self._json(404, {"error": "not_found"})
                return
            self._json(
                200,
                {
                    "id": int(row["id"]),
                    "record_type": row["record_type"],
                    "payload": row["payload"],
                    "deleted": bool(row["deleted"]),
                },
            )
            return
        if parsed.path.startswith("/rot/state/"):
            object_id = int(parsed.path.rsplit("/", 1)[1])
            state = self.engine.get_state(tenant_id, object_id)
            if not state:
                self._json(404, {"error": "not_found"})
                return
            self._json(200, state)
            return
        if parsed.path == "/rot/metrics":
            self._json(200, self.engine.metrics_summary(tenant_id))
            return
        if parsed.path == "/metrics":
            summary = self.engine.metrics_summary(tenant_id)
            lines = [f"decay_metric_{k} {v}" for k, v in summary.items()]
            body = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        tenant_id = self._tenant_from_auth()
        if not tenant_id:
            self._json(401, {"error": "unauthorized"})
            return
        if route == "/objects":
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid_json"})
                return
            object_id = self.engine.create_object(
                tenant_id=tenant_id,
                record_type=data["record_type"],
                payload=data["payload"],
                policy_id=int(data["policy_id"]),
            )
            self._json(201, {"object_id": object_id})
            return
        if route == "/ingest":
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                policy_id = int(data["policy_id"])
            except (json.JSONDecodeError, KeyError, ValueError):
                self._json(400, {"error": "invalid_ingest_payload"})
                return

            if data.get("content_base64") and data.get("filename"):
                try:
                    raw = base64.b64decode(data["content_base64"], validate=True)
                except (ValueError, binascii.Error):
                    self._json(400, {"error": "invalid_base64"})
                    return
                filename = data["filename"]
                mime_type = data.get("mime_type")
                stored_path = save_binary(filename, raw)
                record_type = self._infer_record_type(filename, mime_type)
                object_id = self.engine.create_object(
                    tenant_id=tenant_id,
                    record_type=record_type,
                    payload=stored_path,
                    policy_id=policy_id,
                    original_filename=filename,
                )
                self._json(201, {"object_id": object_id, "record_type": record_type, "stored_path": stored_path})
                return

            text = str(data.get("text", "")).strip()
            if not text:
                self._json(400, {"error": "empty_text_or_missing_file"})
                return
            object_id = self.engine.create_object(
                tenant_id=tenant_id,
                record_type="log",
                payload=text,
                policy_id=policy_id,
            )
            self._json(201, {"object_id": object_id, "record_type": "log"})
            return
        if route == "/upload":
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                filename = data["filename"]
                content_base64 = data["content_base64"]
                raw = base64.b64decode(content_base64, validate=True)
                mime_type = data.get("mime_type")
                policy_id = int(data["policy_id"])
            except (json.JSONDecodeError, KeyError, ValueError, binascii.Error):
                self._json(400, {"error": "invalid_upload_payload"})
                return
            stored_path = save_binary(filename, raw)
            record_type = self._infer_record_type(filename, mime_type)
            object_id = self.engine.create_object(
                tenant_id=tenant_id,
                record_type=record_type,
                payload=stored_path,
                policy_id=policy_id,
                original_filename=filename,
            )
            self._json(201, {"object_id": object_id, "record_type": record_type, "stored_path": stored_path})
            return
        if route == "/rot/run":
            changed = self.engine.decay_tick(tenant_id=tenant_id)
            self._json(200, {"changed": changed})
            return
        if route.startswith("/rot/restore/"):
            object_id = int(route.rsplit("/", 1)[1])
            ok = self.engine.restore_object(tenant_id, object_id)
            self._json(200, {"restored": ok})
            return
        if route.startswith("/rot/control/"):
            object_id = int(route.rsplit("/", 1)[1])
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid_json"})
                return
            ok = self.engine.set_object_controls(
                tenant_id=tenant_id,
                object_id=object_id,
                legal_hold=data.get("legal_hold"),
                do_not_decay=data.get("do_not_decay"),
            )
            self._json(200, {"updated": ok})
            return
        if route.startswith("/objects/") and route.endswith("/delete"):
            object_id = int(route.split("/")[-2])
            ok = self.engine.force_delete_object(tenant_id, object_id)
            self._json(200, {"deleted": ok})
            return
        if route.startswith("/objects/") and route.endswith("/rename"):
            object_id = int(route.split("/")[-2])
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                new_name = str(data["new_name"])
            except (json.JSONDecodeError, KeyError, ValueError):
                self._json(400, {"error": "invalid_rename_payload"})
                return
            ok = self.engine.rename_object_file(tenant_id, object_id, new_name)
            self._json(200, {"renamed": ok})
            return
        self._json(404, {"error": "not_found"})


def make_server(host: str, port: int, engine: DecayEngine) -> ThreadingHTTPServer:
    raw = os.getenv("RUSTDB_API_KEYS", os.getenv("DECAYDB_API_KEYS", "devkey:default"))
    mapping: dict[str, str] = {}
    for part in raw.split(","):
        key, tenant = part.split(":", 1)
        mapping[key.strip()] = tenant.strip()
    handler = type("BoundDecayApiHandler", (DecayApiHandler,), {"engine": engine, "api_keys": mapping})
    return ThreadingHTTPServer((host, port), handler)

