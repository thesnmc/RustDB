# TheSNMC RustDB tests
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from decaydb.engine import DecayEngine
from decaydb.models import bootstrap


class DecayEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        bootstrap(self.conn)
        self.engine = DecayEngine(self.conn)
        self.tenant_id = "tenant_a"
        self.policy_id = self.engine.add_policy(
            tenant_id=self.tenant_id,
            name="test_policy",
            record_type="log",
            stage_one_after_sec=3,
            stage_two_after_sec=6,
            delete_after_sec=9,
            min_retention_sec=0,
            grace_delete_sec=1,
            irreversible=False,
            legal_hold_default=False,
            access_cooldown_sec=0,
            weighted_scan_factor=0.5,
            restore_window_sec=120,
        )

    def test_stage_progression_and_delete(self) -> None:
        object_id = self.engine.create_object(
            self.tenant_id, "log", "alpha beta gamma delta epsilon zeta eta theta", self.policy_id, now=100
        )
        self.engine.decay_tick(self.tenant_id, now=104)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 1)

        self.engine.decay_tick(self.tenant_id, now=107)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 2)

        self.engine.decay_tick(self.tenant_id, now=111)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 4)
        self.assertTrue(state["deleted"])

    def test_access_refresh_resets_stage(self) -> None:
        object_id = self.engine.create_object(self.tenant_id, "log", "one two three four five six seven eight", self.policy_id, now=50)
        self.engine.decay_tick(self.tenant_id, now=54)
        stage_1 = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(stage_1["current_stage"], 1)
        self.engine.get_object(self.tenant_id, object_id, now=55, access_weight=1.0)
        refreshed = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(refreshed["current_stage"], 0)
        self.assertGreaterEqual(refreshed["fidelity_score"], 1.0)

    def test_shadow_mode_no_mutation(self) -> None:
        object_id = self.engine.create_object(self.tenant_id, "log", "a b c d e f g h i j", self.policy_id, now=10)
        self.engine.decay_tick(self.tenant_id, now=14, shadow_mode=True)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 0)
        self.assertFalse(state["deleted"])

    def test_restore_after_delete(self) -> None:
        object_id = self.engine.create_object(self.tenant_id, "log", "very detailed payload for recovery", self.policy_id, now=200)
        self.engine.decay_tick(self.tenant_id, now=204)
        self.engine.decay_tick(self.tenant_id, now=207)
        self.engine.decay_tick(self.tenant_id, now=211)
        self.assertTrue(self.engine.get_state(self.tenant_id, object_id)["deleted"])
        restored = self.engine.restore_object(self.tenant_id, object_id, now=212)
        self.assertFalse(restored)

    def test_restore_after_window_is_degraded(self) -> None:
        short_window_policy = self.engine.add_policy(
            tenant_id=self.tenant_id,
            name="short_restore_window",
            record_type="log",
            stage_one_after_sec=3,
            stage_two_after_sec=6,
            delete_after_sec=9,
            restore_window_sec=1,
        )
        object_id = self.engine.create_object(self.tenant_id, "log", "quality should not fully return", short_window_policy, now=100)
        self.engine.decay_tick(self.tenant_id, now=104)
        self.engine.decay_tick(self.tenant_id, now=107)
        self.engine.decay_tick(self.tenant_id, now=111)
        restored = self.engine.restore_object(self.tenant_id, object_id, now=120)
        self.assertFalse(restored)

    def test_keep_original_toggle_allows_restore(self) -> None:
        object_id = self.engine.create_object(
            self.tenant_id,
            "log",
            "original payload for restore toggle",
            self.policy_id,
            now=300,
            original_filename="note.txt",
            keep_original_restore=True,
        )
        self.engine.decay_tick(self.tenant_id, now=304)
        self.engine.decay_tick(self.tenant_id, now=307)
        self.engine.decay_tick(self.tenant_id, now=311)
        restored = self.engine.restore_object(self.tenant_id, object_id, now=312)
        self.assertTrue(restored)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 0)

    def test_decay_rate_half_requires_two_ticks_per_stage(self) -> None:
        object_id = self.engine.create_object(
            self.tenant_id,
            "log",
            "slow decay payload",
            self.policy_id,
            now=400,
            decay_rate=0.5,
        )
        self.engine.decay_tick(self.tenant_id, now=404)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 0)
        self.engine.decay_tick(self.tenant_id, now=405)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 1)

    def test_keep_original_file_purges_after_restore_window(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(b"original bytes")
            original_path = tmp.name
        try:
            object_id = self.engine.create_object(
                self.tenant_id,
                "log",
                original_path,
                self.policy_id,
                now=500,
                original_filename="sample.txt",
                keep_original_restore=True,
            )
            self.engine.decay_tick(self.tenant_id, now=504)
            self.engine.decay_tick(self.tenant_id, now=507)
            self.engine.decay_tick(self.tenant_id, now=511)
            self.assertTrue(self.engine.get_state(self.tenant_id, object_id)["deleted"])
            self.assertTrue(os.path.exists(original_path))

            # Window for this policy is 120s; after expiry, kept original should be purged.
            self.engine.decay_tick(self.tenant_id, now=700)
            self.assertFalse(os.path.exists(original_path))
        finally:
            if os.path.exists(original_path):
                os.remove(original_path)

    def test_expired_original_purge_works_even_if_deleted_flag_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(b"original bytes")
            original_path = tmp.name
        try:
            object_id = self.engine.create_object(
                self.tenant_id,
                "log",
                original_path,
                self.policy_id,
                now=800,
                original_filename="sample.txt",
                keep_original_restore=True,
            )
            self.engine.decay_tick(self.tenant_id, now=804)
            self.engine.decay_tick(self.tenant_id, now=807)
            self.engine.decay_tick(self.tenant_id, now=811)
            # Simulate stale/incorrect object_data.deleted flag while stage is already terminal.
            self.conn.execute("UPDATE object_data SET deleted = 0 WHERE id = ?", (object_id,))
            self.conn.commit()
            self.engine.decay_tick(self.tenant_id, now=950)
            self.assertFalse(os.path.exists(original_path))
        finally:
            if os.path.exists(original_path):
                os.remove(original_path)

    def test_force_tick_advances_without_waiting_for_wall_time(self) -> None:
        object_id = self.engine.create_object(
            self.tenant_id,
            "log",
            "force tick payload",
            self.policy_id,
            now=1000,
        )
        self.engine.decay_tick(self.tenant_id, now=1000, force=True)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 1)

    def test_force_tick_purges_kept_original_after_delete(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(b"original bytes")
            original_path = tmp.name
        try:
            object_id = self.engine.create_object(
                self.tenant_id,
                "log",
                original_path,
                self.policy_id,
                now=1100,
                original_filename="sample.txt",
                keep_original_restore=True,
            )
            self.engine.decay_tick(self.tenant_id, now=1100, force=True)  # stage 1
            self.engine.decay_tick(self.tenant_id, now=1100, force=True)  # stage 2
            self.engine.decay_tick(self.tenant_id, now=1100, force=True)  # delete stage
            self.assertFalse(os.path.exists(original_path))
        finally:
            if os.path.exists(original_path):
                os.remove(original_path)

    def test_object_controls_prevent_decay(self) -> None:
        object_id = self.engine.create_object(self.tenant_id, "log", "protected payload", self.policy_id, now=1000)
        self.engine.set_object_controls(self.tenant_id, object_id, legal_hold=True)
        self.engine.decay_tick(self.tenant_id, now=1004)
        state = self.engine.get_state(self.tenant_id, object_id)
        self.assertEqual(state["current_stage"], 0)
        self.assertFalse(state["deleted"])

    def test_list_policies_and_export_dsl(self) -> None:
        policies = self.engine.list_policies(self.tenant_id)
        self.assertGreaterEqual(len(policies), 1)
        dsl = self.engine.export_policy_dsl(self.tenant_id, self.policy_id)
        self.assertIn("stage_one_after_sec", dsl)


if __name__ == "__main__":
    unittest.main()

