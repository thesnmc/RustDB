"""TheSNMC RustDB core decay engine: tenant-scoped lifecycle and controls."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from decaydb.transforms import (
    compress_binary_file,
    compress_image_file_aggressive,
    compress_image_file,
    compress_image_marker,
    metadata_only_file,
    summarize_document_file,
    summarize_log,
    summarize_spreadsheet_file,
    summarize_text_file,
)


class DecayEngine:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def add_policy(
        self,
        tenant_id: str,
        name: str,
        record_type: str,
        stage_one_after_sec: int,
        stage_two_after_sec: int,
        delete_after_sec: int,
        min_retention_sec: int = 0,
        grace_delete_sec: int = 0,
        irreversible: bool = False,
        legal_hold_default: bool = False,
        access_cooldown_sec: int = 0,
        weighted_scan_factor: float = 0.25,
        purge_after_sec: int = 30,
        restore_window_sec: int = 120,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO rot_policy (
                tenant_id, name, record_type, stage_one_after_sec, stage_two_after_sec, delete_after_sec,
                min_retention_sec, grace_delete_sec, irreversible, legal_hold_default,
                access_cooldown_sec, weighted_scan_factor, purge_after_sec, restore_window_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                name,
                record_type,
                stage_one_after_sec,
                stage_two_after_sec,
                delete_after_sec,
                min_retention_sec,
                grace_delete_sec,
                int(irreversible),
                int(legal_hold_default),
                access_cooldown_sec,
                weighted_scan_factor,
                purge_after_sec,
                restore_window_sec,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def upsert_policy(self, tenant_id: str, name: str, payload: dict) -> int:
        existing = self.conn.execute(
            "SELECT id FROM rot_policy WHERE tenant_id = ? AND name = ?",
            (tenant_id, name),
        ).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE rot_policy
                SET record_type = ?, stage_one_after_sec = ?, stage_two_after_sec = ?,
                    delete_after_sec = ?, min_retention_sec = ?, grace_delete_sec = ?,
                    irreversible = ?, legal_hold_default = ?, access_cooldown_sec = ?, weighted_scan_factor = ?,
                    purge_after_sec = ?, restore_window_sec = ?
                WHERE id = ?
                """,
                (
                    payload["record_type"],
                    payload["stage_one_after_sec"],
                    payload["stage_two_after_sec"],
                    payload["delete_after_sec"],
                    payload.get("min_retention_sec", 0),
                    payload.get("grace_delete_sec", 0),
                    int(payload.get("irreversible", False)),
                    int(payload.get("legal_hold_default", False)),
                    payload.get("access_cooldown_sec", 0),
                    payload.get("weighted_scan_factor", 0.25),
                    payload.get("purge_after_sec", 30),
                    payload.get("restore_window_sec", 120),
                    int(existing["id"]),
                ),
            )
            self.conn.commit()
            return int(existing["id"])
        return self.add_policy(tenant_id=tenant_id, name=name, **payload)

    def create_object(
        self,
        tenant_id: str,
        record_type: str,
        payload: str,
        policy_id: int,
        now: Optional[int] = None,
        original_filename: str = "",
    ) -> int:
        now = now or int(time.time())
        cur = self.conn.execute(
            """
            INSERT INTO object_data (tenant_id, record_type, payload, original_filename, deleted, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (tenant_id, record_type, payload, original_filename, now),
        )
        object_id = int(cur.lastrowid)

        policy = self.conn.execute(
            "SELECT * FROM rot_policy WHERE id = ? AND tenant_id = ?",
            (policy_id, tenant_id),
        ).fetchone()
        if not policy:
            raise ValueError(f"Policy not found: {policy_id}")

        next_decay_at = now + int(policy["stage_one_after_sec"])
        self.conn.execute(
            """
            INSERT INTO rot_state (
                object_id, policy_id, last_access_at, current_stage, next_decay_at, fidelity_score,
                legal_hold, do_not_decay, restore_available, deleted_at, version
            ) VALUES (?, ?, ?, 0, ?, 1.0, ?, 0, 1, 0, 1)
            """,
            (object_id, policy_id, now, next_decay_at, int(policy["legal_hold_default"])),
        )
        self._save_artifact(object_id, 0, "origin", payload, now)
        self._audit(object_id, "create", f"stage=0 next_decay_at={next_decay_at}", now)
        self.conn.commit()
        return object_id

    def get_object(self, tenant_id: str, object_id: int, now: Optional[int] = None, access_weight: float = 1.0):
        now = now or int(time.time())
        row = self.conn.execute(
            """
            SELECT d.id, d.record_type, d.payload, d.deleted, s.current_stage, s.policy_id
            FROM object_data d
            JOIN rot_state s ON s.object_id = d.id
            WHERE d.id = ? AND d.tenant_id = ?
            """,
            (object_id, tenant_id),
        ).fetchone()
        if not row or row["deleted"] == 1:
            return None

        self._refresh_access(tenant_id, object_id, int(row["policy_id"]), now, access_weight=access_weight)
        self.conn.commit()
        return self.conn.execute(
            "SELECT id, record_type, payload, deleted FROM object_data WHERE id = ?",
            (object_id,),
        ).fetchone()

    def decay_tick(
        self, tenant_id: str, now: Optional[int] = None, limit: int = 50, shadow_mode: bool = False
    ) -> int:
        now = now or int(time.time())
        candidates = self.conn.execute(
            """
            SELECT s.object_id, s.policy_id, s.current_stage, s.last_access_at, s.version, s.legal_hold,
                   s.do_not_decay, d.record_type, d.payload, d.created_at
            FROM rot_state s
            JOIN object_data d ON d.id = s.object_id
            WHERE s.next_decay_at <= ? AND d.tenant_id = ?
            ORDER BY s.next_decay_at ASC
            LIMIT ?
            """,
            (now, tenant_id, limit),
        ).fetchall()

        changed = 0
        for row in candidates:
            if self._apply_next_stage(tenant_id, row, now, shadow_mode=shadow_mode):
                changed += 1
        self._metric(tenant_id, "decay_tick_changed", float(changed), now)
        self.conn.commit()
        return changed

    def list_objects(self, tenant_id: str):
        return self.conn.execute(
            """
            SELECT d.id, d.record_type, d.payload, d.deleted, s.current_stage, s.fidelity_score, s.next_decay_at,
                   s.legal_hold, s.do_not_decay
            FROM object_data d
            JOIN rot_state s ON s.object_id = d.id
            WHERE d.tenant_id = ?
            ORDER BY d.id
            """,
            (tenant_id,),
        ).fetchall()

    def list_policies(self, tenant_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM rot_policy WHERE tenant_id = ? ORDER BY id", (tenant_id,)).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]

    def audit_log(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT object_id, action, detail, created_at FROM rot_audit_log ORDER BY id"
        ).fetchall()

    def get_state(self, tenant_id: str, object_id: int) -> Optional[dict]:
        row = self.conn.execute(
            """
            SELECT d.id, d.record_type, d.deleted, s.current_stage, s.next_decay_at, s.fidelity_score,
                   s.last_access_at, s.legal_hold, s.do_not_decay, s.restore_available
            FROM object_data d
            JOIN rot_state s ON s.object_id = d.id
            WHERE d.id = ? AND d.tenant_id = ?
            """,
            (object_id, tenant_id),
        ).fetchone()
        if not row:
            return None
        audit = self.conn.execute(
            "SELECT action, detail, created_at FROM rot_audit_log WHERE object_id = ? ORDER BY id DESC LIMIT 10",
            (object_id,),
        ).fetchall()
        return {
            "object_id": int(row["id"]),
            "record_type": row["record_type"],
            "deleted": bool(row["deleted"]),
            "current_stage": int(row["current_stage"]),
            "next_decay_at": int(row["next_decay_at"]),
            "fidelity_score": float(row["fidelity_score"]),
            "last_access_at": int(row["last_access_at"]),
            "legal_hold": bool(row["legal_hold"]),
            "do_not_decay": bool(row["do_not_decay"]),
            "restore_available": bool(row["restore_available"]),
            "recent_audit": [
                {"action": a["action"], "detail": a["detail"], "created_at": int(a["created_at"])} for a in audit
            ],
        }

    def restore_object(self, tenant_id: str, object_id: int, now: Optional[int] = None) -> bool:
        now = now or int(time.time())
        state = self.conn.execute(
            """
            SELECT s.policy_id, s.deleted_at, d.deleted
            FROM rot_state s JOIN object_data d ON d.id = s.object_id
            WHERE s.object_id = ? AND d.tenant_id = ?
            """,
            (object_id, tenant_id),
        ).fetchone()
        if not state:
            return False
        policy = self.conn.execute("SELECT * FROM rot_policy WHERE id = ?", (state["policy_id"],)).fetchone()
        deleted_at = int(state["deleted_at"] or 0)
        window = int(policy["restore_window_sec"])
        within_full_window = deleted_at == 0 or (now - deleted_at) <= window

        full_artifact = None
        if within_full_window:
            full_artifact = self.conn.execute(
                """
                SELECT content FROM rot_artifact
                WHERE object_id = ? AND stage = 0
                ORDER BY id DESC
                LIMIT 1
                """,
                (object_id,),
            ).fetchone()

        if full_artifact:
            self.conn.execute(
                "UPDATE object_data SET payload = ?, deleted = 0 WHERE id = ? AND tenant_id = ?",
                (full_artifact["content"], object_id, tenant_id),
            )
            self._refresh_access(tenant_id, object_id, int(state["policy_id"]), now, access_weight=1.0)
            self._audit(object_id, "restore", "restored_full_quality_within_window", now)
            self.conn.commit()
            return True

        degraded = self.conn.execute(
            """
            SELECT content, stage FROM rot_artifact
            WHERE object_id = ? AND stage IN (1,2,3)
            ORDER BY id DESC
            LIMIT 1
            """,
            (object_id,),
        ).fetchone()
        if not degraded:
            return False
        self.conn.execute(
            "UPDATE object_data SET payload = ?, deleted = 0 WHERE id = ? AND tenant_id = ?",
            (degraded["content"], object_id, tenant_id),
        )
        next_decay_at = now + int(policy["stage_two_after_sec"])
        self.conn.execute(
            """
            UPDATE rot_state
            SET last_access_at = ?, current_stage = 1, next_decay_at = ?, fidelity_score = 0.5, deleted_at = 0,
                version = version + 1
            WHERE object_id = ?
            """,
            (now, next_decay_at, object_id),
        )
        self._audit(object_id, "restore", "restored_degraded_after_window", now)
        self.conn.commit()
        return True

    def set_object_controls(
        self,
        tenant_id: str,
        object_id: int,
        legal_hold: Optional[bool] = None,
        do_not_decay: Optional[bool] = None,
    ) -> bool:
        row = self.conn.execute(
            """
            SELECT s.object_id FROM rot_state s
            JOIN object_data d ON d.id = s.object_id
            WHERE s.object_id = ? AND d.tenant_id = ?
            """,
            (object_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        updates: list[str] = []
        params: list[object] = []
        if legal_hold is not None:
            updates.append("legal_hold = ?")
            params.append(int(legal_hold))
        if do_not_decay is not None:
            updates.append("do_not_decay = ?")
            params.append(int(do_not_decay))
        if not updates:
            return True
        params.append(object_id)
        self.conn.execute(f"UPDATE rot_state SET {', '.join(updates)} WHERE object_id = ?", tuple(params))
        self.conn.commit()
        return True

    def force_delete_object(self, tenant_id: str, object_id: int, now: Optional[int] = None) -> bool:
        now = now or int(time.time())
        row = self.conn.execute(
            """
            SELECT s.object_id, s.policy_id, s.version, d.payload
            FROM rot_state s JOIN object_data d ON d.id = s.object_id
            WHERE s.object_id = ? AND d.tenant_id = ?
            """,
            (object_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        policy = self.conn.execute("SELECT * FROM rot_policy WHERE id = ?", (row["policy_id"],)).fetchone()
        purge_at = now + int(policy["purge_after_sec"])
        self.conn.execute(
            """
            UPDATE rot_state
            SET current_stage = 3, deleted_at = ?, next_decay_at = ?, fidelity_score = 0.0, version = version + 1
            WHERE object_id = ? AND version = ?
            """,
            (now, purge_at, object_id, int(row["version"])),
        )
        self._save_artifact(object_id, 3, "pre_delete", str(row["payload"]), now)
        self.conn.execute("UPDATE object_data SET deleted = 1, payload = '[deleted]' WHERE id = ?", (object_id,))
        self._audit(object_id, "delete", "forced_delete", now)
        self.conn.commit()
        return True

    def rename_object_file(self, tenant_id: str, object_id: int, new_name: str) -> bool:
        row = self.conn.execute(
            "SELECT payload, deleted FROM object_data WHERE id = ? AND tenant_id = ?",
            (object_id, tenant_id),
        ).fetchone()
        if not row or int(row["deleted"]) == 1:
            return False
        payload = str(row["payload"])
        src = Path(payload)
        if not src.exists() or not src.is_file():
            return False
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in new_name.strip())
        if not safe:
            return False
        dst = src.with_name(safe)
        src.rename(dst)
        self.conn.execute("UPDATE object_data SET payload = ? WHERE id = ?", (str(dst), object_id))
        self._audit(object_id, "rename_file", f"new_name={safe}", int(time.time()))
        self.conn.commit()
        return True

    def _refresh_access(self, tenant_id: str, object_id: int, policy_id: int, now: int, access_weight: float) -> None:
        policy = self.conn.execute("SELECT * FROM rot_policy WHERE id = ?", (policy_id,)).fetchone()
        state = self.conn.execute("SELECT last_access_at FROM rot_state WHERE object_id = ?", (object_id,)).fetchone()
        if state and now - int(state["last_access_at"]) < int(policy["access_cooldown_sec"]):
            self._audit(object_id, "access_ignored", "cooldown_active", now)
            return
        effective_weight = max(0.0, min(access_weight, 1.0))
        if effective_weight < 1.0:
            effective_weight *= float(policy["weighted_scan_factor"])
        extension = int(int(policy["stage_one_after_sec"]) * effective_weight)
        if extension <= 0:
            extension = 1
        next_decay_at = now + extension
        self.conn.execute(
            """
            UPDATE rot_state
            SET last_access_at = ?, next_decay_at = ?, current_stage = 0, fidelity_score = 1.0, version = version + 1
            WHERE object_id = ?
            """,
            (now, next_decay_at, object_id),
        )
        self._audit(object_id, "access_refresh", f"reset_to_stage=0 next_decay_at={next_decay_at}", now)
        self._metric(tenant_id, "refresh_count", 1.0, now)

    def _apply_next_stage(self, tenant_id: str, row: sqlite3.Row, now: int, shadow_mode: bool) -> bool:
        policy = self.conn.execute("SELECT * FROM rot_policy WHERE id = ?", (row["policy_id"],)).fetchone()
        object_id = int(row["object_id"])
        current_stage = int(row["current_stage"])
        last_access_at = int(row["last_access_at"])
        original_version = int(row["version"])
        created_at = int(row["created_at"])
        payload = str(row["payload"])
        record_type = str(row["record_type"])
        if int(row["legal_hold"]) == 1 or int(row["do_not_decay"]) == 1:
            self._audit(object_id, "decay_skipped", "hold_or_tag", now)
            return False
        if now - created_at < int(policy["min_retention_sec"]):
            self._audit(object_id, "decay_skipped", "min_retention", now)
            return False

        if current_stage == 0:
            new_payload = payload
            if record_type == "log":
                new_payload = summarize_log(payload)
            elif record_type == "image":
                new_payload = compress_image_marker(payload)
            elif record_type == "text_file":
                new_payload = summarize_text_file(payload)
            elif record_type == "image_file":
                new_payload = compress_image_file(payload)
            elif record_type == "binary_file":
                new_payload = compress_binary_file(payload)

            next_decay_at = last_access_at + int(policy["stage_two_after_sec"])
            if shadow_mode:
                self._audit(object_id, "shadow_stage_1", f"would_next_decay_at={next_decay_at}", now)
                return True
            updated = self.conn.execute(
                """
                UPDATE rot_state
                SET current_stage = 1, next_decay_at = ?, fidelity_score = 0.6, version = version + 1
                WHERE object_id = ? AND version = ?
                """,
                (next_decay_at, object_id, original_version),
            )
            if updated.rowcount == 0:
                return False
            self.conn.execute(
                "UPDATE object_data SET payload = ? WHERE id = ?",
                (new_payload, object_id),
            )
            self._save_artifact(object_id, 1, "stage_1", new_payload, now)
            self._audit(object_id, "decay_stage_1", f"next_decay_at={next_decay_at}", now)
            self._metric(tenant_id, "stage_1_count", 1.0, now)
            self._metric(tenant_id, "bytes_saved", float(max(self._size(payload) - self._size(new_payload), 0)), now)
            return True

        if current_stage == 1:
            if not shadow_mode:
                stage2_payload = None
                if record_type == "binary_file":
                    stage2_payload = metadata_only_file(payload)
                elif record_type == "image_file":
                    stage2_payload = compress_image_file_aggressive(payload)
                elif record_type == "spreadsheet_file":
                    stage2_payload = summarize_spreadsheet_file(payload)
                elif record_type in {"document_file", "pdf_file"}:
                    stage2_payload = summarize_document_file(payload)
                if stage2_payload:
                    payload = stage2_payload
                    self.conn.execute("UPDATE object_data SET payload = ? WHERE id = ?", (payload, object_id))
            next_decay_at = last_access_at + int(policy["delete_after_sec"]) + int(policy["grace_delete_sec"])
            if shadow_mode:
                self._audit(object_id, "shadow_stage_2", f"would_next_decay_at={next_decay_at}", now)
                return True
            updated = self.conn.execute(
                """
                UPDATE rot_state
                SET current_stage = 2, next_decay_at = ?, fidelity_score = 0.2, version = version + 1
                WHERE object_id = ? AND version = ?
                """,
                (next_decay_at, object_id, original_version),
            )
            if updated.rowcount == 0:
                return False
            self._audit(object_id, "decay_stage_2", f"next_decay_at={next_decay_at}", now)
            self._metric(tenant_id, "stage_2_count", 1.0, now)
            return True

        if current_stage >= 2:
            if current_stage == 3:
                # Purge file artifacts after delayed tombstone window.
                self._purge_files_for_object(object_id)
                self.conn.execute("DELETE FROM rot_artifact WHERE object_id = ?", (object_id,))
                self.conn.execute(
                    """
                    UPDATE rot_state
                    SET current_stage = 4, next_decay_at = ?, version = version + 1
                    WHERE object_id = ? AND version = ?
                    """,
                    (now + 315360000, object_id, original_version),
                )
                self.conn.execute("UPDATE object_data SET payload = '[purged]' WHERE id = ?", (object_id,))
                self._audit(object_id, "purge_files", "storage_artifacts_removed", now)
                self._metric(tenant_id, "purge_count", 1.0, now)
                return True
            if shadow_mode:
                self._audit(object_id, "shadow_delete", "would_delete", now)
                return True
            updated = self.conn.execute(
                """
                UPDATE rot_state
                SET current_stage = 3, next_decay_at = ?, deleted_at = ?, fidelity_score = 0.0, restore_available = ?, version = version + 1
                WHERE object_id = ? AND version = ?
                """,
                (
                    now + int(policy["purge_after_sec"]),
                    now,
                    int((not policy["irreversible"]) and int(policy["restore_window_sec"]) > 0),
                    object_id,
                    original_version,
                ),
            )
            if updated.rowcount == 0:
                return False
            if int(policy["irreversible"]) == 0:
                self._save_artifact(object_id, 3, "pre_delete", payload, now)
            self.conn.execute("UPDATE object_data SET deleted = 1, payload = '[deleted]' WHERE id = ?", (object_id,))
            self._audit(object_id, "delete", "hard_delete_applied", now)
            self._metric(tenant_id, "delete_count", 1.0, now)
            return True

        return False

    def _audit(self, object_id: int, action: str, detail: str, now: int) -> None:
        self.conn.execute(
            """
            INSERT INTO rot_audit_log (object_id, action, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (object_id, action, detail, now),
        )

    def _save_artifact(self, object_id: int, stage: int, artifact_kind: str, content: str, now: int) -> None:
        self.conn.execute(
            """
            INSERT INTO rot_artifact (object_id, stage, artifact_kind, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (object_id, stage, artifact_kind, content, now),
        )

    def _metric(self, tenant_id: str, metric_name: str, metric_value: float, now: int) -> None:
        self.conn.execute(
            "INSERT INTO rot_metrics (tenant_id, metric_name, metric_value, recorded_at) VALUES (?, ?, ?, ?)",
            (tenant_id, metric_name, metric_value, now),
        )

    def _size(self, payload: str) -> int:
        if os.path.exists(payload):
            try:
                return int(os.path.getsize(payload))
            except OSError:
                return len(payload)
        return len(payload)

    def _purge_files_for_object(self, object_id: int) -> None:
        rows = self.conn.execute("SELECT content FROM rot_artifact WHERE object_id = ?", (object_id,)).fetchall()
        for row in rows:
            value = str(row["content"])
            if os.path.exists(value):
                try:
                    os.remove(value)
                except OSError:
                    pass

    def metrics_summary(self, tenant_id: str) -> dict:
        rows = self.conn.execute(
            """
            SELECT metric_name, SUM(metric_value) AS total
            FROM rot_metrics
            WHERE tenant_id = ?
            GROUP BY metric_name
            """,
            (tenant_id,),
        ).fetchall()
        return {row["metric_name"]: row["total"] for row in rows}

    def export_policy_dsl(self, tenant_id: str, policy_id: int) -> str:
        policy = self.conn.execute(
            "SELECT * FROM rot_policy WHERE id = ? AND tenant_id = ?",
            (policy_id, tenant_id),
        ).fetchone()
        if not policy:
            raise ValueError(f"Policy not found: {policy_id}")
        return json.dumps({key: policy[key] for key in policy.keys()}, sort_keys=True)

