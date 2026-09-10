#!/usr/bin/env python3
"""Contract tests for adaptive delivery-runner dispatch decisions."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "scripts" / "delivery-run-next.py"


class DeliveryRunNextContractTest(unittest.TestCase):
    def write_plan(self, size: str = "M") -> Path:
        box = Path(tempfile.mkdtemp())
        plan = box / "phased-plan"
        plan.mkdir()
        (box / "destination.md").write_text("# Destination\n", encoding="utf-8")
        (plan / "phase-01-example.md").write_text("# Phase 01\n", encoding="utf-8")
        (plan / "README.md").write_text(
            """---
work_key: adaptive-test
plan_branch: feature/adaptive-test
state: active
current_dispatch_pointer: phase-01
readiness_decision: READY_FOR_DISPATCH
---

| ID | Title | Owner skill | Size | State | Prereqs |
| --- | --- | --- | --- | --- | --- |
| phase-01 | Example | software-engineer | %s | ready | none |
""" % size,
            encoding="utf-8",
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(box))
        return box

    def run_helper(self, work_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(HELPER), str(work_dir), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_default_mode_preserves_standard_dispatch_and_existing_types(self) -> None:
        result = self.run_helper(self.write_plan("M"))

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("dispatch", payload["action"])
        self.assertEqual("STANDARD", payload["execution_mode"])
        self.assertIsInstance(payload["work_key"], str)
        self.assertIsInstance(payload["totals"], dict)
        self.assertIsInstance(payload["phase"], dict)

    def test_each_mode_reports_a_stable_explicit_contract(self) -> None:
        expected = {
            "LIGHT": ("S", ["S"]),
            "STANDARD": ("M", ["S", "M"]),
            "RIGOROUS": ("L", ["S", "M", "L"]),
        }
        for mode, (budget, eligible) in expected.items():
            with self.subTest(mode=mode):
                result = self.run_helper(self.write_plan("S"), "--mode", mode.lower())
                payload = json.loads(result.stdout)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(mode, payload["execution_mode"])
                self.assertEqual(
                    {
                        "phase_budget": budget,
                        "eligible_phase_sizes": eligible,
                        "mandatory_gates": True,
                    },
                    payload["execution_contract"],
                )

    def test_invalid_mode_fails_closed_with_classified_json(self) -> None:
        result = self.run_helper(self.write_plan(), "--mode", "turbo")

        self.assertEqual(2, result.returncode)
        self.assertEqual(
            {
                "action": "error",
                "reason": "invalid-mode",
                "message": "Invalid execution mode 'turbo'. Expected LIGHT, STANDARD, or RIGOROUS.",
            },
            json.loads(result.stdout),
        )

    def test_mode_refuses_a_phase_above_its_budget(self) -> None:
        result = self.run_helper(self.write_plan("M"), "--mode", "LIGHT")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("stop", payload["action"])
        self.assertEqual("mode-phase-ineligible", payload["reason"])
        self.assertEqual("LIGHT", payload["execution_mode"])
        self.assertNotIn("phase", payload)

    def test_rigorous_dispatches_a_large_phase(self) -> None:
        result = self.run_helper(self.write_plan("L"), "--mode", "RIGOROUS")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("dispatch", payload["action"])
        self.assertEqual("L", payload["phase"]["size"])

    def test_runner_instructions_forward_the_selected_mode_for_every_decision(self) -> None:
        skill = (REPO_ROOT / "skills" / "delivery-runner" / "SKILL.md").read_text(encoding="utf-8")
        checklist = (
            REPO_ROOT / "skills" / "delivery-runner" / "references" / "run-loop-checklist.md"
        ).read_text(encoding="utf-8")

        command = r'agent-skills plan-next\s+"\$\{CACHE_DIR\}/<work-key>"\s+--mode'
        self.assertGreaterEqual(len(re.findall(command, skill)), 3)
        self.assertIn('--mode "${EXECUTION_MODE}"', checklist)


if __name__ == "__main__":
    unittest.main()
