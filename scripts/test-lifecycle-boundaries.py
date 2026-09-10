#!/usr/bin/env python3
"""Adversarial regression tests for task cleanup and secret boundaries."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


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
            self.assertEqual(removed, target.resolve())
            self.assertFalse(target.exists())
            self.assertTrue(other.exists())

    def test_case_collision_refuses_without_removing_any_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            colliding = [root / "ABC-123", root / "abc-123"]
            with mock.patch.object(Path, "iterdir", return_value=iter(colliding)):
                with self.assertRaisesRegex(SystemExit, "ambiguous"):
                    memory.cleanup_task(root, "AbC-123")

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

    def test_mature_secret_classes_are_redacted(self):
        pem = "-----BEGIN " + "PRIVATE KEY-----\nCANARY-DATA\n-----END PRIVATE KEY-----"
        secrets = {
            "aws": "AKIA" + "A" * 16,
            "pem": pem,
            "url": "https://" + "canary-user:canary-password@example.invalid/path",
        }
        clean = blackboard.redact_boundary(secrets)
        encoded = json.dumps(clean)
        for secret in secrets.values():
            self.assertNotIn(secret, encoded)
        self.assertIn("REDACTED:aws-access-key", encoded)
        self.assertIn("REDACTED:pem-private-key", encoded)
        self.assertIn("REDACTED:url-credentials", encoded)

    def test_blackboard_redacts_nested_artifact_before_persistence(self):
        value = {"prompt": f"Authorization: Bearer {self.canary}", "nested": [self.canary]}
        clean = blackboard.redact_boundary(value)
        encoded = json.dumps(clean)
        self.assertNotIn(self.canary, encoded)
        self.assertIn("REDACTED", encoded)

    def test_blackboard_read_redacts_legacy_unsanitized_content_before_printing(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "demo"
            task.mkdir()
            (task / "blackboard.json").write_text(
                json.dumps({"facts": [{"text": self.canary}]}), encoding="utf-8"
            )
            proc = subprocess.run(
                ["python3", str(SCRIPTS / "blackboard.py"), "--cache-root", tmp,
                 "read", "demo"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn(self.canary, proc.stdout + proc.stderr)
            self.assertIn("REDACTED", proc.stdout)

    def test_project_memory_read_redacts_legacy_unsanitized_content_before_printing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "_projects" / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "memory.md").write_text(
                f"# Project memory: demo\n\n- {self.canary}\n", encoding="utf-8"
            )
            proc = subprocess.run(
                ["python3", str(SCRIPTS / "project-memory.py"), "--cache-root", tmp,
                 "read", "demo"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn(self.canary, proc.stdout + proc.stderr)
            self.assertIn("REDACTED", proc.stdout)

    def test_project_memory_search_and_promotion_redact_legacy_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "_projects" / "demo"
            project_dir.mkdir(parents=True)
            content = f"# Project memory: demo\n\n## Project facts\n- {self.canary}\n"
            (project_dir / "memory.md").write_text(content, encoding="utf-8")
            commands = (["search", "demo", "ghp_"],
                        ["promote-candidates", "demo", "--section", "Project facts",
                         "--min-count", "1"])
            for command in commands:
                proc = subprocess.run(
                    ["python3", str(SCRIPTS / "project-memory.py"), "--cache-root", tmp,
                     *command], capture_output=True, text=True, check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertNotIn(self.canary, proc.stdout + proc.stderr)
                self.assertIn("REDACTED", proc.stdout)

    def test_project_memory_initialization_redacts_before_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "project"
            memory.ensure_skeleton(pdir, self.canary, self.canary)
            persisted = (pdir / "memory.md").read_text(encoding="utf-8")
            persisted += (pdir / "memory.json").read_text(encoding="utf-8")
            self.assertNotIn(self.canary, persisted)
            self.assertIn("REDACTED", persisted)

    def test_delivery_output_redacts_stdout_stderr_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "phased-plan" / "README.md"
            index.parent.mkdir()
            index.write_text(
                "---\nwork_key: " + self.canary
                + "\nstate: active\nreadiness_decision: BLOCKED\n"
                + "current_dispatch_pointer: null\n---\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python3", str(SCRIPTS / "delivery-run-next.py"), str(index)],
                capture_output=True, text=True, check=False,
            )
            combined = proc.stdout + proc.stderr
            self.assertNotIn(self.canary, combined)
            self.assertIn("REDACTED", combined)
            json.loads(proc.stdout)


class MutationProbeTests(unittest.TestCase):
    def test_persistence_assertion_fails_when_production_redaction_is_weakened(self):
        canary = "ghp_" + "B" * 36
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(telemetry, "redact_boundary", side_effect=lambda value: value):
                path = telemetry.emit(Path(tmp), "demo", "handoff", {"detail": canary})
            with self.assertRaises(AssertionError):
                self.assertNotIn(canary, path.read_text(encoding="utf-8"))

    def test_blackboard_assertion_fails_when_production_redaction_is_weakened(self):
        canary = "ghp_" + "C" * 36
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blackboard.json"
            with mock.patch.object(blackboard, "redact_boundary", side_effect=lambda value: value):
                blackboard.save(path, {"facts": [{"text": canary}]})
            with self.assertRaises(AssertionError):
                self.assertNotIn(canary, path.read_text(encoding="utf-8"))

    def test_project_memory_assertion_fails_when_production_redaction_is_weakened(self):
        canary = "ghp_" + "D" * 36
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp)
            memory.ensure_skeleton(pdir, "demo", None)
            with mock.patch.object(memory, "redact_text", side_effect=lambda value: value):
                memory.append_note(pdir, "Project facts", canary)
            with self.assertRaises(AssertionError):
                self.assertNotIn(canary, (pdir / "memory.md").read_text(encoding="utf-8"))

    def test_cleanup_assertion_fails_when_production_casefold_guard_is_weakened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "ABC-123"
            target.mkdir()
            with mock.patch.object(memory, "canonical_issue_key", side_effect=lambda value: value):
                with self.assertRaises(AssertionError):
                    removed = memory.cleanup_task(root, "abc-123")
                    self.assertEqual(removed, target.resolve())

    def test_cleanup_assertion_fails_when_production_symlink_guard_is_weakened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "real-task"
            destination.mkdir()
            link = root / "abc-123"
            link.symlink_to(destination, target_is_directory=True)
            with mock.patch.object(Path, "is_symlink", return_value=False):
                with self.assertRaises((AssertionError, OSError)):
                    with self.assertRaisesRegex(SystemExit, "symlink"):
                        memory.cleanup_task(root, "abc-123")


if __name__ == "__main__":
    unittest.main(verbosity=2)
