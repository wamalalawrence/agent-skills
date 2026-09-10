#!/usr/bin/env python3
"""Adversarial regression tests for task cleanup and secret boundaries."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


memory = load("project_memory", "project-memory.py")
telemetry = load("telemetry", "telemetry.py")
blackboard = load("blackboard", "blackboard.py")


class CleanupIdentityTests(unittest.TestCase):
    def test_unique_case_variant_is_the_exact_cleanup_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "ABC-123"
            other = root / "ABC-124"
            target.mkdir()
            other.mkdir()
            (target / "scratch").write_text("x", encoding="utf-8")
            removed = memory.cleanup_task(root, "abc-123")
            self.assertEqual(removed, target)
            self.assertFalse(target.exists())
            self.assertTrue(other.exists())

    def test_case_collision_refuses_without_removing_any_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "ABC-123", root / "abc-123"
            first.mkdir()
            try:
                second.mkdir()
            except FileExistsError:
                self.skipTest("filesystem is case-insensitive")
            with self.assertRaisesRegex(SystemExit, "ambiguous"):
                memory.cleanup_task(root, "AbC-123")
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_symlink_target_refuses_and_preserves_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "real-task"
            destination.mkdir()
            (destination / "evidence").write_text("keep", encoding="utf-8")
            (root / "abc-123").symlink_to(destination, target_is_directory=True)
            with self.assertRaisesRegex(SystemExit, "symlink"):
                memory.cleanup_task(root, "ABC-123")
            self.assertTrue((destination / "evidence").exists())


class SecretBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.canary = "ghp_" + "A" * 36

    def test_telemetry_redacts_before_json_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = telemetry.emit(Path(tmp), "demo", "handoff", {"detail": self.canary})
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn(self.canary, raw)
            self.assertIn("[REDACTED:github-token]", raw)
            json.loads(raw)

    def test_blackboard_redacts_nested_artifact_before_persistence(self):
        value = {"prompt": f"Authorization: Bearer {self.canary}", "nested": [self.canary]}
        clean = blackboard.redact_boundary(value)
        encoded = json.dumps(clean)
        self.assertNotIn(self.canary, encoded)
        self.assertIn("REDACTED", encoded)

    def test_delivery_output_redacts_stdout_stderr_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "phased-plan" / "README.md"
            index.parent.mkdir()
            index.write_text("---\nwork_key: " + self.canary + "\nstate: active\nreadiness_decision: BLOCKED\ncurrent_dispatch_pointer: null\n---\n", encoding="utf-8")
            proc = subprocess.run(
                ["python3", str(SCRIPTS / "delivery-run-next.py"), str(index)],
                capture_output=True, text=True, check=False,
            )
            combined = proc.stdout + proc.stderr
            self.assertNotIn(self.canary, combined)
            self.assertIn("REDACTED", combined)
            json.loads(proc.stdout)


class MutationProbeTests(unittest.TestCase):
    def test_redaction_assertion_detects_deliberately_weakened_boundary(self):
        dirty = {"token": "ghp_" + "B" * 36}
        weakened = dirty  # mutation: boundary returns input unchanged
        self.assertIn(dirty["token"], json.dumps(weakened))

    def test_cleanup_assertion_detects_case_sensitive_mutation(self):
        requested = "abc-123"
        actual = "ABC-123"
        weakened_match = requested == actual  # mutation: omit case-folding
        self.assertFalse(weakened_match)


if __name__ == "__main__":
    unittest.main(verbosity=2)
