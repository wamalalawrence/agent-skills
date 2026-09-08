#!/usr/bin/env python3
"""Validate repository structure, skill contracts, links, versions, and public-safety guardrails."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
MARKDOWN_MAX_LINE_LENGTH = 200
MARKDOWN_AVG_LINE_WARN = 115
MARKDOWN_DENSITY_FAIL_RATIO = 200
MARKDOWN_DENSITY_MIN_BYTES = 1500
SOURCE_MAX_LINE_LENGTH = 200
SOURCE_WARN_LINE_LENGTH = 140
SOURCE_AVG_LINE_WARN = 125
SOURCE_DENSITY_FAIL_RATIO = 180
SOURCE_DENSITY_MIN_BYTES = 1500

REQUIRED_FILES = [
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "VERSION",
    ".agent-skills.example.yml",
    ".env.example",
    ".jira-config.example.yml",
    ".github/markdown-link-check.json",
    ".github/workflows/ci.yml",
    ".github/copilot-instructions.md",
    ".github/copilot-instructions.example.md",
    "docs/README.md",
    "docs/quickstart.md",
    "docs/known-limitations.md",
    "docs/versioning.md",
    "docs/validation.md",
    "docs/skill-quality-scorecard.md",
    "docs/release-checklist.md",
    "docs/destructive-action-safety.md",
    "docs/requirement-understanding.md",
    "docs/requirement-understanding-scorecard.md",
    "docs/auth-discovery.md",
    "docs/access-resolution.md",
    "docs/github-access.md",
    "docs/project-memory.md",
    "docs/repo-knowledge.md",
    "docs/mcp.md",
    "docs/lifecycle-preflight.md",
    "docs/skill-source-resolution.md",
    "docs/updates.md",
    "docs/output-discipline.md",
    "docs/writing-voice.md",
    "docs/insightful-simplifications.md",
    "docs/examples/requirement-understanding.md",
    "scripts/validate-repo.py",
    "scripts/validate_skills.py",
    "scripts/auth-preflight.py",
    "scripts/access.py",
    "scripts/project-context.py",
    "scripts/locate-config.py",
    "bin/agent-skills",
    "lib/runtime.sh",
    "lib/install.sh",
    "lib/migrate.sh",
    "lib/hosts.registry",
    "docs/plans/2026-09-global-install-and-access-resolver.md",
    "scripts/test-global-install.sh",
    "scripts/test-access-resolution.sh",
    "scripts/project-memory.py",
    "scripts/knowledge.py",
    "scripts/start-task.sh",
    "scripts/finish-task.sh",
    "scripts/task-context.sh",
    "scripts/github-access.sh",
    "scripts/doctor.sh",
    "hooks/README.md",
    "hooks/claude-code-settings.json",
    "hooks/kiro-lifecycle.json",
    "hooks/generic-session-hooks.sh",
    "scripts/check-updates.py",
    "skills/software-engineer/SKILL.md",
    "skills/software-engineer/README.md",
    "skills/software-engineer/references/architecture-patterns.md",
    "skills/software-engineer/references/code-review-checklist.md",
    "skills/software-engineer/references/definition-of-done.md",
    "skills/software-engineer/references/destructive-action-guardrails.md",
    "skills/software-engineer/references/required-environment.md",
    "skills/software-engineer/references/evidence-pack.md",
    "skills/software-engineer/references/security-checklist.md",
    "skills/software-engineer/references/sonarqube-checklist.md",
    "skills/software-engineer/skills/issue-investigator/SKILL.md",
    "skills/software-engineer/skills/issue-investigator/README.md",
    "skills/software-engineer/skills/code-reviewer/SKILL.md",
    "skills/software-engineer/skills/code-reviewer/README.md",
    "skills/product-owner/SKILL.md",
    "skills/product-owner/README.md",
    "skills/manual-tester/SKILL.md",
    "skills/manual-tester/README.md",
    "skills/test-automation-engineer/SKILL.md",
    "skills/test-automation-engineer/README.md",
    "skills/delivery-planner/SKILL.md",
    "skills/delivery-planner/README.md",
    "skills/delivery-planner/references/plan-quality-checklist.md",
    "skills/delivery-planner/references/phase-template.md",
    "skills/delivery-planner/references/destination-template.md",
    "skills/delivery-planner/references/plan-index-template.md",
    "skills/delivery-runner/SKILL.md",
    "skills/delivery-runner/README.md",
    "skills/delivery-runner/references/handoff-prompt-template.md",
    "skills/delivery-runner/references/run-loop-checklist.md",
    "skills/tech-lead/SKILL.md",
    "skills/tech-lead/README.md",
    "skills/tech-lead/references/routing-table.md",
    "skills/tech-lead/references/handoff-prompt-template.md",
    "evals/tech-lead-routing.md",
    "docs/examples/tech-lead-routing.md",
    "skills/domain-modeler/SKILL.md",
    "skills/domain-modeler/README.md",
    "skills/domain-modeler/references/ADR-FORMAT.md",
    "skills/domain-modeler/references/CONTEXT-FORMAT.md",
    "scripts/delivery-run-next.py",
    "evals/delivery-runner-autonomous-handoff.md",
    "eval-runs/v0.34.0/summary.md",
    "evals/delivery-planner-phased-plan.md",
    "evals/delivery-planner-phase-continuity.md",
    "docs/examples/delivery-planner-feature-decomposition.md",
    "evals/issue-investigator-bug-root-cause.md",
    "evals/all-skills-lifecycle-compliance.md",
    "evals/code-reviewer-issue-aware-review.md",
    "evals/software-engineer-bugfix-flow.md",
    "evals/software-engineer-skill-compliance-sonarqube.md",
    "evals/product-owner-story-refinement.md",
    "evals/manual-tester-defect-report.md",
    "evals/test-automation-engineer-flaky-test-review.md",
    "evals/multi-skill-bug-to-regression-flow.md",
    "evals/issue-investigator-read-only-investigation.md",
    "evals/code-reviewer-unavailable-context.md",
    "evals/requirement-understanding-ambiguous-ticket.md",
    "evals/requirement-understanding-conflicting-criteria.md",
    "evals/requirement-understanding-bug-vs-feature.md",
    "evals/requirement-understanding-wrong-root-cause-trap.md",
    "evals/requirement-understanding-security-sensitive-request.md",
    "evals/auth-discovery-jira-confluence.md",
    "evals/skill-source-resolution-ambiguity.md",
    "evals/jira-issue-scope-and-existing-pr.md",
    "evals/code-reviewer-concise-output.md",
    "evals/writing-voice-human-tone.md",
    "evals/insightful-simplifications-concise.md",
    "eval-runs/README.md",
    "eval-runs/v0.9.0/summary.md",
    "eval-runs/v0.9.0/issue-investigator-bug-root-cause.md",
    "eval-runs/v0.9.0/code-reviewer-issue-aware-review.md",
    "eval-runs/v0.9.0/software-engineer-bugfix-flow.md",
    "eval-runs/v0.9.0/product-owner-story-refinement.md",
    "eval-runs/v0.9.0/manual-tester-defect-report.md",
    "eval-runs/v0.9.0/test-automation-engineer-flaky-test-review.md",
    "eval-runs/v0.9.0/multi-skill-bug-to-regression-flow.md",
    "eval-runs/v0.10.0/summary.md",
    "eval-runs/v0.10.0/issue-investigator-read-only-investigation.md",
    "eval-runs/v0.10.0/code-reviewer-unavailable-context.md",
    "eval-runs/v0.11.0/summary.md",
    "eval-runs/v0.11.0/setup-flow-hardening.md",
    "eval-runs/v0.17.0/summary.md",
    "eval-runs/v0.17.0/requirement-understanding-multi-skill.md",
    "eval-runs/v0.18.0/summary.md",
    "eval-runs/v0.18.0/auth-discovery-jira-confluence.md",
    "eval-runs/v0.19.0/summary.md",
    "eval-runs/v0.19.0/skill-source-resolution.md",
    "eval-runs/v0.20.0/summary.md",
    "eval-runs/v0.20.0/code-reviewer-concise-output.md",
    "eval-runs/v0.20.0/model-routing-removal.md",
    "eval-runs/v0.21.0/summary.md",
    "eval-runs/v0.21.0/code-reviewer-verdict-gating.md",
    "eval-runs/v0.21.0/setup-update-preserves-credentials.md",
    "eval-runs/v0.21.0/updating-discoverability.md",
    "eval-runs/v0.33.0/summary.md",
    "eval-runs/v0.33.1/summary.md",
    "eval-runs/v0.36.0/summary.md",
    "evals/code-reviewer-verdict-gating.md",
    "scripts/test-setup-update-preserves-credentials.sh",
]

# Setup-managed environment keys. They MUST appear inside the
# `# >>> agent-skills setup.init` ... `# <<< agent-skills setup.init` marker
# block in `.env.example` (and any user-generated `.env`) — never as a second
# top-level definition outside the block. Duplicates cause silent overrides.
SETUP_MANAGED_KEYS = [
    "ORG_NAME",
    "ORG_DOMAIN",
    "WORKSPACE_ROOT",
    "GITHUB_ORG",
    "GITHUB_DEFAULT_BRANCH",
    "PROJECTS_JSON",
    "JIRA_CONFIG_FILE",
    "JIRA_HOST",
    "JIRA_AUTH_TYPE",
    "JIRA_LOGIN",
    "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEYS",
    "JIRA_KEY_REGEX",
    "CONFLUENCE_HOST",
    "CONFLUENCE_LOGIN",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_SPACE_KEYS",
    "SONAR_HOST_URL",
    "SONAR_TOKEN",
    "ENVIRONMENTS_JSON",
]
SETUP_MARKER_START = "# >>> agent-skills setup.init"
SETUP_MARKER_END = "# <<< agent-skills setup.init"

REQUIRED_SKILL_SECTIONS = [
    # The lifecycle block is first because it is load-bearing: it wires memory,
    # the blackboard, the capability report, and telemetry. It was held in place
    # by convention alone until v0.36.0, which meant a skill could ship with the
    # entire Company Brain loop absent and still pass validation.
    "⚠️ PREFLIGHT — Execute before ANY other action",
    "Purpose",
    "When To Use",
    "When Not To Use",
    "Related And Reused Skills",
    "Required Inputs",
    "Required Workflow",
    "Stopping Conditions",
    "Expected Output Contract",
    "Behavior Checklist",
    "Quality Standards",
    "Guardrails",
    "Example Prompts",
]

LINK_REQUIREMENTS = {
    "skills/software-engineer/SKILL.md": [
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
        "skills/software-engineer/skills/code-reviewer/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
    "skills/manual-tester/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
    "skills/test-automation-engineer/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
    "skills/product-owner/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
    "skills/delivery-planner/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
        "skills/delivery-runner/SKILL.md",
    ],
    "skills/delivery-runner/SKILL.md": [
        "skills/delivery-planner/SKILL.md",
        "skills/software-engineer/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
    ],
    "skills/tech-lead/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/delivery-planner/SKILL.md",
        "skills/delivery-runner/SKILL.md",
        "skills/domain-modeler/SKILL.md",
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
        "skills/software-engineer/skills/code-reviewer/SKILL.md",
    ],
    "skills/domain-modeler/SKILL.md": [
        "skills/product-owner/SKILL.md",
        "skills/software-engineer/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
    "skills/software-engineer/skills/code-reviewer/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/software-engineer/skills/issue-investigator/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
    ],
    "skills/software-engineer/skills/issue-investigator/SKILL.md": [
        "skills/software-engineer/SKILL.md",
        "skills/software-engineer/skills/code-reviewer/SKILL.md",
        "skills/product-owner/SKILL.md",
        "skills/manual-tester/SKILL.md",
        "skills/test-automation-engineer/SKILL.md",
        "skills/delivery-planner/SKILL.md",
    ],
}

TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".json", ".example", ".init", ".txt"}
TEXT_NAMES = {"VERSION", "LICENSE", "setup.init", ".gitignore"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".cache",
    ".claude",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
GENERATED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".cache",
    ".skills-cache",
}
FORBIDDEN_TRACKED = GENERATED_NAMES | {".env", ".env.local", ".jira-config.yml", ".skills"}
ALLOWED_HOSTS = {
    "agentskills.io",
    "code.visualstudio.com",
    "skills.sh",
    "github.com",
    "docs.github.com",
    "example.com",
    "example.org",
    "example.net",
    "localhost",
}
PLACEHOLDER_TICKET_PREFIXES = {"ABC", "DEMO", "EXAMPLE", "PROJ", "SHA", "TEST"}


@dataclass
class Result:
    errors: list[str]
    warnings: list[str]

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, object] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return _hand_parse(text[4:end])


def _strip_quotes(value: str) -> str:
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _hand_parse(block: str) -> dict[str, object]:
    result: dict[str, object] = {}
    lines = block.splitlines()
    index = 0

    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if raw.startswith(" "):
            index += 1
            continue

        key, separator, value = raw.partition(":")
        if not separator:
            index += 1
            continue

        key = key.strip()
        value = value.strip()

        if value in {">", ">-", "|", "|-"}:
            index += 1
            scalar_lines: list[str] = []
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith(" ")):
                if lines[index].strip() and not lines[index].lstrip().startswith("#"):
                    scalar_lines.append(lines[index].strip())
                index += 1
            result[key] = (
                " ".join(scalar_lines).strip()
                if value.startswith(">")
                else "\n".join(scalar_lines).strip()
            )
            continue

        if value == "":
            index += 1
            block_lines: list[str] = []
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith(" ")):
                if lines[index].strip() and not lines[index].lstrip().startswith("#"):
                    block_lines.append(lines[index].strip())
                index += 1

            if not block_lines:
                result[key] = ""
            elif all(":" in line and not line.startswith(("'", '"')) for line in block_lines):
                nested: dict[str, str] = {}
                for line in block_lines:
                    nested_key, _, nested_value = line.partition(":")
                    nested[nested_key.strip()] = _strip_quotes(nested_value.strip())
                result[key] = nested
            else:
                result[key] = _strip_quotes(" ".join(block_lines).strip())
            continue

        result[key] = _strip_quotes(value)
        index += 1

    return result


def yaml_bool(value: object) -> bool | None:
    """Interpret a hand-parsed frontmatter scalar as a YAML boolean.

    ``_hand_parse`` deliberately keeps every scalar as a string, so a caller that
    needs a boolean has to normalise it. Returns None when the value is neither a
    boolean nor a recognised boolean spelling.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on"}:
            return True
        if lowered in {"false", "no", "off"}:
            return False
    return None


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    return text[end + 4 :] if end != -1 else text


def normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", heading.strip().lower())


def markdown_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.md") if not should_skip_path(path))


def text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or should_skip_path(path):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            files.append(path)
    return sorted(files)


def should_skip_path(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def check_required_files(result: Result) -> None:
    for required in REQUIRED_FILES:
        if not (ROOT / required).exists():
            result.error(f"missing required file: {required}")


def check_markdown_structure(result: Result) -> None:
    for path in markdown_files():
        text = read_text(path)
        body = strip_frontmatter(text)
        line_count = len(text.splitlines()) or 1
        if len(text) > 600 and line_count <= 2:
            result.error(f"{rel(path)}: appears compressed into {line_count} giant line(s)")
        if (
            len(text) >= MARKDOWN_DENSITY_MIN_BYTES
            and len(text) / line_count > MARKDOWN_DENSITY_FAIL_RATIO
        ):
            result.error(
                f"{rel(path)}: appears compressed ("
                f"{len(text)} bytes across {line_count} lines, "
                f"{len(text) / line_count:.1f} bytes/line)"
            )
        check_markdown_readability(path, text, result)
        if not re.search(r"^#{1,6}\s+\S", body, re.MULTILINE):
            result.error(f"{rel(path)}: missing Markdown heading")
        check_code_fences(path, text, result)
        check_internal_links(path, text, result)


def is_long_url_or_reference(line: str) -> bool:
    stripped = line.strip()
    if re.match(r"^\[[^\]]+\]:\s+\S+$", stripped):
        return True
    return stripped.startswith(("http://", "https://")) and " " not in stripped


def is_code_fence_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def check_markdown_readability(path: Path, text: str, result: Result) -> None:
    in_code_fence = False
    nonblank_lengths: list[int] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        starts_fence = is_code_fence_line(line)

        if ("```" in line or "~~~" in line) and not starts_fence:
            result.error(f"{rel(path)}:{line_number}: code fence starts mid-line")

        if starts_fence:
            in_code_fence = not in_code_fence
            continue

        if in_code_fence:
            continue

        if stripped:
            nonblank_lengths.append(len(line))

        if "\t" in line:
            result.error(f"{rel(path)}:{line_number}: tab character in Markdown source")

        if len(line) > MARKDOWN_MAX_LINE_LENGTH and not is_long_url_or_reference(line):
            result.error(
                f"{rel(path)}:{line_number}: Markdown line exceeds "
                f"{MARKDOWN_MAX_LINE_LENGTH} chars ({len(line)})"
            )

        if not line.lstrip().startswith("#") and re.search(r"\S\s+#{1,6}\s+\S", line):
            result.error(f"{rel(path)}:{line_number}: Markdown heading appears mid-line")

        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") > 10:
            result.error(f"{rel(path)}:{line_number}: possible collapsed Markdown table rows")

    if nonblank_lengths:
        average = sum(nonblank_lengths) / len(nonblank_lengths)
        if average > MARKDOWN_AVG_LINE_WARN:
            result.warn(
                f"{rel(path)}: average Markdown line length is suspiciously high "
                f"({average:.1f})"
            )


def check_source_readability(result: Result) -> None:
    for path in text_files():
        if path.suffix not in {".py", ".yml", ".yaml"}:
            continue
        text = read_text(path)
        lines = text.splitlines()
        nonblank_lengths = [len(line) for line in lines if line.strip()]
        line_count = len(lines) or 1
        if (
            len(text) >= SOURCE_DENSITY_MIN_BYTES
            and len(text) / line_count > SOURCE_DENSITY_FAIL_RATIO
        ):
            result.error(
                f"{rel(path)}: appears compressed/minified ("
                f"{len(text)} bytes across {line_count} lines, "
                f"{len(text) / line_count:.1f} bytes/line)"
            )
        for line_number, line in enumerate(lines, start=1):
            if "\t" in line:
                result.error(f"{rel(path)}:{line_number}: tab character in source file")
            if len(line) > SOURCE_MAX_LINE_LENGTH and not is_long_url_or_reference(line):
                result.error(
                    f"{rel(path)}:{line_number}: source line exceeds "
                    f"{SOURCE_MAX_LINE_LENGTH} chars ({len(line)})"
                )
            elif len(line) > SOURCE_WARN_LINE_LENGTH and not is_long_url_or_reference(line):
                result.warn(f"{rel(path)}:{line_number}: long source line ({len(line)} chars)")
        if path.suffix in {".yml", ".yaml"}:
            check_yaml_minification(path, lines, result)
        if path.suffix == ".py":
            check_python_minification(path, lines, result)
        if nonblank_lengths:
            average = sum(nonblank_lengths) / len(nonblank_lengths)
            if average > SOURCE_AVG_LINE_WARN:
                result.warn(
                    f"{rel(path)}: average source line length is suspiciously high "
                    f"({average:.1f})"
                )


YAML_INLINE_KEY_RE = re.compile(r"[A-Za-z_][\w-]*\s*:\s*\S")


def check_yaml_minification(path: Path, lines: list[str], result: Result) -> None:
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("{", "[")) and len(stripped) > 80:
            result.error(
                f"{rel(path)}:{line_number}: YAML inline flow value looks minified"
            )
            continue
        if not line.startswith((" ", "\t")) and stripped.count(": ") >= 3:
            inline_keys = len(YAML_INLINE_KEY_RE.findall(stripped))
            if inline_keys >= 3:
                result.error(
                    f"{rel(path)}:{line_number}: multiple YAML keys collapsed onto one line"
                )


def check_python_minification(path: Path, lines: list[str], result: Result) -> None:
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        in_string = False
        quote = ""
        statements = 0
        for ch in stripped:
            if in_string:
                if ch == quote:
                    in_string = False
            elif ch in {'"', "'"}:
                in_string = True
                quote = ch
            elif ch == "#":
                break
            elif ch == ";":
                statements += 1
        if statements >= 2:
            result.error(
                f"{rel(path)}:{line_number}: multiple Python statements on one line"
            )


def check_code_fences(path: Path, text: str, result: Result) -> None:
    stack: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if stack and stack[-1][0] == marker:
                stack.pop()
            else:
                stack.append((marker, line_number))
    if stack:
        marker, line_number = stack[-1]
        result.error(f"{rel(path)}:{line_number}: unbalanced code fence {marker}")


INLINE_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\[[^\]]+\]:\s+(\S+)", re.MULTILINE)


def markdown_link_targets(text: str) -> list[str]:
    targets = [match.group(1).strip() for match in INLINE_LINK_RE.finditer(text)]
    targets.extend(match.group(1).strip() for match in REFERENCE_LINK_RE.finditer(text))
    return targets


def is_external_or_anchor(target: str) -> bool:
    parsed = urlparse(target)
    return bool(parsed.scheme or parsed.netloc) or target.startswith("#")


def resolve_markdown_target(path: Path, target: str) -> Path | None:
    clean = target.strip("<>")
    if is_external_or_anchor(clean):
        return None
    clean = clean.split("#", 1)[0]
    if not clean:
        return None
    return (path.parent / unquote(clean)).resolve()


def check_internal_links(path: Path, text: str, result: Result) -> None:
    for target in markdown_link_targets(text):
        resolved = resolve_markdown_target(path, target)
        if resolved is None:
            continue
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            result.warn(f"{rel(path)}: relative link leaves repo: {target}")
            continue
        if not resolved.exists():
            result.error(f"{rel(path)}: broken relative link: {target}")


def check_skill_files(result: Result, repo_version: str) -> None:
    skill_files = sorted(ROOT.glob("skills/**/SKILL.md"))
    if not skill_files:
        result.error("no SKILL.md files found under skills/")
        return

    for path in skill_files:
        text = read_text(path)
        fm = parse_frontmatter(text)
        if fm is None:
            result.error(f"{rel(path)}: missing or malformed YAML frontmatter")
            continue

        validate_frontmatter(path, fm, repo_version, result)
        validate_skill_sections(path, text, result)


def validate_frontmatter(path: Path, fm: dict[str, object], repo_version: str, result: Result) -> None:
    name = fm.get("name")
    if not isinstance(name, str) or not name:
        result.error(f"{rel(path)}: frontmatter 'name' is required")
    else:
        if len(name) > 64 or not NAME_RE.match(name):
            result.error(f"{rel(path)}: invalid skill name {name!r}")
        if name != path.parent.name:
            result.error(f"{rel(path)}: name {name!r} must match parent directory {path.parent.name!r}")

    for field in ("description", "license", "compatibility"):
        value = fm.get(field)
        if not isinstance(value, str) or not value.strip():
            result.error(f"{rel(path)}: frontmatter '{field}' is required and must be non-empty")

    metadata = fm.get("metadata")
    if not isinstance(metadata, dict):
        result.error(f"{rel(path)}: frontmatter 'metadata' mapping is required")
        return

    for field in ("author", "version", "homepage"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            result.error(f"{rel(path)}: metadata.{field} is required and must be non-empty")

    version = metadata.get("version")
    if isinstance(version, str) and version != repo_version:
        result.error(f"{rel(path)}: metadata.version {version!r} must match VERSION {repo_version!r}")

    # Invocability is declared explicitly on every skill rather than left to host
    # defaults. Before v0.36.0 only the two nested skills declared these keys,
    # which was the inverse of the documented intent — the top-level skills are
    # the ones meant to be invoked directly.
    #
    # `_hand_parse` returns every scalar as a string, so compare against the YAML
    # spelling rather than a Python bool.
    if yaml_bool(fm.get("user-invocable")) is not True:
        result.error(f"{rel(path)}: frontmatter 'user-invocable: true' is required")
    if yaml_bool(fm.get("disable-model-invocation")) is not False:
        result.error(
            f"{rel(path)}: frontmatter 'disable-model-invocation: false' is required "
            f"(every skill in this repo is model-invocable)"
        )
    hint = fm.get("argument-hint")
    if not isinstance(hint, str) or not hint.strip():
        result.error(f"{rel(path)}: frontmatter 'argument-hint' is required and must be non-empty")


def validate_skill_sections(path: Path, text: str, result: Result) -> None:
    body = strip_frontmatter(text)
    headings = {
        normalize_heading(match.group(1))
        for match in re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE)
    }
    for section in REQUIRED_SKILL_SECTIONS:
        if normalize_heading(section) not in headings:
            result.error(f"{rel(path)}: missing required section '## {section}'")


def check_version_consistency(result: Result) -> str:
    version_path = ROOT / "VERSION"
    version = read_text(version_path).strip() if version_path.exists() else ""
    if not version:
        result.error("VERSION is empty")
        return version
    if not SEMVER_RE.match(version):
        result.error(f"VERSION is not semver-shaped: {version!r}")

    expected = os.environ.get("AGENT_SKILLS_EXPECTED_VERSION")
    if expected and version != expected:
        result.error(f"VERSION {version!r} does not match AGENT_SKILLS_EXPECTED_VERSION {expected!r}")

    changelog = read_text(ROOT / "CHANGELOG.md") if (ROOT / "CHANGELOG.md").exists() else ""
    if not re.search(r"^##\s+\[?Unreleased\]?\s*$", changelog, re.MULTILINE):
        result.error("CHANGELOG.md is missing an Unreleased section")

    readme = read_text(ROOT / "README.md") if (ROOT / "README.md").exists() else ""
    if version and version not in readme:
        result.warn(f"README.md does not mention current VERSION {version}")

    return version


def check_skill_link_consistency(result: Result) -> None:
    for skill, required_targets in LINK_REQUIREMENTS.items():
        path = ROOT / skill
        if not path.exists():
            continue
        resolved_links = {
            rel(resolved)
            for target in markdown_link_targets(read_text(path))
            if (resolved := resolve_markdown_target(path, target)) is not None and resolved.exists()
        }
        for required in required_targets:
            if required not in resolved_links:
                result.error(f"{skill}: missing required cross-skill link to {required}")


def check_forbidden_content(result: Result) -> None:
    secret_patterns = [
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(
            r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}"
        ),
    ]
    private_path_re = re.compile(r"(?:/Users/[^\s)]+|/home/[^\s)]+|[A-Za-z]:\\\\Users\\\\[^\s)]+)")
    email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
    ticket_re = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b")
    url_host_re = re.compile(r"https?://([^/\s)]+)")
    internal_host_re = re.compile(
        r"(?<![A-Za-z0-9_.-])(?:[a-z0-9-]+\.)+[a-z0-9-]+\.(?:corp|internal|local)\b",
        re.I,
    )

    for path in text_files():
        text = read_text(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("#") and path.suffix != ".md":
                continue
            if "$" not in line and "<" not in line:
                for pattern in secret_patterns:
                    if pattern.search(line):
                        result.error(f"{rel(path)}:{line_number}: possible committed secret or token")
            if "private_path_re =" not in line and private_path_re.search(line):
                result.error(f"{rel(path)}:{line_number}: private local absolute path detected")
            for host in url_host_re.findall(line):
                host = host.split(":", 1)[0].lower()
                if not re.search(r"[a-z0-9]", host):
                    continue
                if not is_allowed_host(host):
                    result.warn(f"{rel(path)}:{line_number}: review hardcoded hostname {host!r}")
            if internal_host_re.search(line):
                result.warn(f"{rel(path)}:{line_number}: possible private/internal hostname")
            for match in email_re.finditer(line):
                domain = match.group(1).lower()
                if not (domain.startswith("example.") or domain in {"localhost"}):
                    result.warn(f"{rel(path)}:{line_number}: possible real email/customer data")
            if "ticket_re =" not in line:
                for match in ticket_re.finditer(line):
                    prefix = match.group(1)
                    if prefix not in PLACEHOLDER_TICKET_PREFIXES:
                        result.warn(f"{rel(path)}:{line_number}: review hardcoded ticket key {match.group(0)!r}")


def is_allowed_host(host: str) -> bool:
    if host in ALLOWED_HOSTS:
        return True
    return any(host.endswith(f".{allowed}") for allowed in ALLOWED_HOSTS)


def git_ls_files() -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in completed.stdout.splitlines() if line]


def is_git_ignored(path: Path) -> bool:
    try:
        subprocess.run(
            ["git", "check-ignore", "-q", rel(path)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def check_generated_files(result: Result) -> None:
    for tracked in git_ls_files():
        parts = Path(tracked).parts
        if Path(tracked).name in FORBIDDEN_TRACKED or any(part in FORBIDDEN_TRACKED for part in parts):
            result.error(f"generated/cache/private file is tracked: {tracked}")

    for path in ROOT.iterdir():
        if path.name in GENERATED_NAMES and not path.name.startswith(".git") and not is_git_ignored(path):
            result.warn(f"local generated/cache file exists and should not be committed: {path.name}")


def check_env_example_marker_block(result: Result) -> None:
    """`.env.example` must keep all setup-managed keys inside one marker block.

    A duplicate top-level definition outside the block silently overrides the
    generated value at runtime ("last assignment wins" in shell sourcing).
    """
    path = ROOT / ".env.example"
    if not path.exists():
        return
    text = read_text(path)
    starts = [i for i, line in enumerate(text.splitlines()) if line == SETUP_MARKER_START]
    ends = [i for i, line in enumerate(text.splitlines()) if line == SETUP_MARKER_END]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        result.error(
            f".env.example: must contain exactly one '{SETUP_MARKER_START}' ... "
            f"'{SETUP_MARKER_END}' block (found {len(starts)} start, {len(ends)} end)"
        )
        return

    in_block_start, in_block_end = starts[0], ends[0]
    lines = text.splitlines()
    inside_pattern = re.compile(
        r"^\s*(?:export\s+)?(" + "|".join(SETUP_MANAGED_KEYS) + r")\s*="
    )
    in_quote = False
    quote_char = ""
    for index, line in enumerate(lines):
        if in_quote:
            if quote_char in line:
                in_quote = False
                quote_char = ""
            continue
        if in_block_start <= index <= in_block_end:
            # Track multi-line single-quoted values (PROJECTS_JSON).
            stripped = line.rstrip()
            if re.search(r"=\s*'[^']*$", stripped):
                in_quote = True
                quote_char = "'"
            continue
        match = inside_pattern.match(line)
        if match:
            result.error(
                f".env.example:{index + 1}: setup-managed key {match.group(1)} "
                f"defined OUTSIDE the marker block; move it inside or remove it"
            )


def check_jira_placeholder_consistency(result: Result) -> None:
    """`.jira-config.example.yml` placeholders must reference keys in `.env.example`.

    A `${JIRA_HOST}` in the YAML that is not defined in `.env.example` will sit unresolved
    after `setup.init` runs and cause an avoidable agent-side "no Jira access" failure.
    """
    yml_path = ROOT / ".jira-config.example.yml"
    env_path = ROOT / ".env.example"
    if not yml_path.exists() or not env_path.exists():
        return

    yml_text = read_text(yml_path)
    env_text = read_text(env_path)
    placeholders = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)\}", yml_text))
    env_keys = {
        match.group(1) for match in re.finditer(
            r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=", env_text, re.MULTILINE
        )
    }
    for name in sorted(placeholders):
        if name not in env_keys:
            result.error(
                f".jira-config.example.yml references ${{{name}}} but {name} is not defined "
                f"in .env.example; add it or remove the placeholder"
            )


REQUIRED_SKILLS_BLOCK_KEYS = (
    "canonical_dir",
    "duplicate_policy",
    "source_repo_dir",
    "allow_source_repo_fallback",
    "warn_on_version_drift",
)


OUTPUT_DISCIPLINE_DOC = "docs/output-discipline.md"
OUTPUT_DISCIPLINE_PHRASE = "Omit empty sections"
WRITING_VOICE_DOC = "docs/writing-voice.md"
WRITING_VOICE_PHRASE = "Write like a person"


def _extract_h2_section(body: str, heading: str) -> str | None:
    """Return the body of the named ``## <heading>`` section.

    Scans line-by-line and tracks fenced-code-block state so that headings
    written *inside* a fenced contract template (e.g. the literal ``## Manual
    Test Plan`` inside the contract code-fence) are not mistaken for the next
    H2 boundary.
    """
    lines = body.splitlines()
    in_section = False
    in_fence = False
    collected: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        is_fence = stripped.startswith("```") or stripped.startswith("~~~")
        if is_fence:
            in_fence = not in_fence
            if in_section:
                collected.append(line)
            continue
        if not in_fence and re.match(r"^##\s+\S", line):
            heading_text = re.sub(r"\s+", " ", line[2:].strip().lower())
            if heading_text == heading.lower():
                in_section = True
                continue
            if in_section:
                break
        if in_section:
            collected.append(line)
    return "\n".join(collected) if in_section else None


def check_skill_output_discipline(result: Result) -> None:
    """Every SKILL.md must inline the output-discipline rule inside its
    Expected Output Contract section.

    Background: in v0.19.0 and earlier the contracts read like menus, and
    agents responded by echoing every section heading even when empty. The
    v0.20.0 fix is two-fold: (1) tighten each contract to "menu, not checklist"
    and (2) gate the rule here so a future SKILL.md cannot silently drop it.
    """
    skill_files = sorted(ROOT.glob("skills/**/SKILL.md"))
    for path in skill_files:
        text = read_text(path)
        body = strip_frontmatter(text)
        section = _extract_h2_section(body, "Expected Output Contract")
        if section is None:
            result.error(
                f"{rel(path)}: missing '## Expected Output Contract' section "
                f"(required for skill-output-discipline gate)"
            )
            continue
        if "output-discipline.md" not in section:
            result.error(
                f"{rel(path)}: Expected Output Contract must link to "
                f"{OUTPUT_DISCIPLINE_DOC} (output-discipline rule)"
            )
        if OUTPUT_DISCIPLINE_PHRASE not in section:
            result.error(
                f"{rel(path)}: Expected Output Contract must restate the "
                f"'{OUTPUT_DISCIPLINE_PHRASE}' rule inline so it cannot drift"
            )
        if "writing-voice.md" not in section:
            result.error(
                f"{rel(path)}: Expected Output Contract must link to "
                f"{WRITING_VOICE_DOC} (writing-voice rule)"
            )
        if WRITING_VOICE_PHRASE not in section:
            result.error(
                f"{rel(path)}: Expected Output Contract must restate the "
                f"'{WRITING_VOICE_PHRASE}' rule inline so it cannot drift"
            )


# Files that legitimately reference the removed CODE_REVIEWER_MODEL /
# code_reviewer_model knobs (history, removal notes, eval transcripts).
CODE_REVIEWER_MODEL_ALLOWED = {
    "CHANGELOG.md",
    "scripts/validate-repo.py",
    "scripts/validate_skills.py",
    "docs/output-discipline.md",  # may discuss model routing in passing
    "skills/software-engineer/skills/code-reviewer/README.md",  # documents the removal
}
CODE_REVIEWER_MODEL_ALLOWED_DIRS = (
    "eval-runs/",
)


def check_no_code_reviewer_model(result: Result) -> None:
    """The model-routing knob `CODE_REVIEWER_MODEL` / `code_reviewer_model`
    was removed in v0.20.0 (see the changelog). The host already owns model
    routing; the skill exposing its own knob caused operator confusion.

    Forbid the strings in tracked files except where they are needed for
    history (CHANGELOG, validator allow-list, eval transcripts).
    """
    pattern = re.compile(r"CODE_REVIEWER_MODEL|code_reviewer_model")
    for path in text_files():
        rel_path = rel(path)
        if rel_path in CODE_REVIEWER_MODEL_ALLOWED:
            continue
        if any(rel_path.startswith(prefix) for prefix in CODE_REVIEWER_MODEL_ALLOWED_DIRS):
            continue
        text = read_text(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                result.error(
                    f"{rel_path}:{line_number}: references removed "
                    f"CODE_REVIEWER_MODEL / code_reviewer_model knob "
                    f"(removed in v0.20.0; the host owns model routing)"
                )


def check_agent_skills_yaml_skills_block(result: Result) -> None:
    """`.agent-skills.example.yml` must keep the documented `skills:` block keys.

    The block is the user-facing knob defined in
    ``docs/skill-source-resolution.md``. If a key is removed from the example
    without updating the doc, downstream users lose the documented escape hatch
    for source-of-truth conflicts.
    """
    path = ROOT / ".agent-skills.example.yml"
    if not path.exists():
        return
    text = read_text(path)
    match = re.search(r"^skills:\s*$", text, re.MULTILINE)
    if match is None:
        result.error(
            ".agent-skills.example.yml: missing top-level 'skills:' block "
            "(see docs/skill-source-resolution.md)"
        )
        return
    block_start = match.end()
    block_end = len(text)
    next_top = re.search(r"^[A-Za-z_][^\s:]*:\s", text[block_start:], re.MULTILINE)
    if next_top is not None:
        block_end = block_start + next_top.start()
    block = text[block_start:block_end]
    for key in REQUIRED_SKILLS_BLOCK_KEYS:
        if not re.search(rf"^\s+{re.escape(key)}\s*:", block, re.MULTILINE):
            result.error(
                f".agent-skills.example.yml: skills.{key} key missing from the "
                "skills: block (see docs/skill-source-resolution.md)"
            )


NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def discovered_skills() -> tuple[list[Path], list[Path]]:
    """Return (top_level, nested) SKILL.md paths found on disk.

    A skill at ``skills/<name>/SKILL.md`` is top-level. One at
    ``skills/<parent>/skills/<name>/SKILL.md`` is nested.
    """
    top_level: list[Path] = []
    nested: list[Path] = []
    for path in sorted(ROOT.glob("skills/**/SKILL.md")):
        depth = len(path.relative_to(ROOT / "skills").parts)
        if depth == 2:
            top_level.append(path)
        else:
            nested.append(path)
    return top_level, nested


def check_skill_registration(result: Result) -> None:
    """Every skill on disk must be registered in both hand-maintained registries.

    ``REQUIRED_FILES`` and ``LINK_REQUIREMENTS`` are edited by hand, so a new
    skill can ship without either entry. That happened once: `domain-modeler`
    was absent from both, which meant its files could be deleted and its
    cross-skill links broken with validation still passing. This check closes
    the class of bug rather than the single instance.
    """
    required = set(REQUIRED_FILES)
    top_level, nested = discovered_skills()

    for path in top_level + nested:
        skill_rel = rel(path)
        skill_dir = path.parent

        if skill_rel not in required:
            result.error(
                f"{skill_rel}: skill is not listed in REQUIRED_FILES "
                f"(scripts/validate-repo.py) — add it so deletion cannot pass CI"
            )

        readme_rel = rel(skill_dir / "README.md")
        if (skill_dir / "README.md").exists() and readme_rel not in required:
            result.error(f"{readme_rel}: skill README is not listed in REQUIRED_FILES")

        for reference in sorted((skill_dir / "references").glob("*.md")):
            reference_rel = rel(reference)
            if reference_rel not in required:
                result.error(
                    f"{reference_rel}: skill reference file is not listed in REQUIRED_FILES"
                )

        if skill_rel not in LINK_REQUIREMENTS:
            result.error(
                f"{skill_rel}: skill has no LINK_REQUIREMENTS entry "
                f"(scripts/validate-repo.py) — its cross-skill links are unverified"
            )

    for skill_rel in sorted(LINK_REQUIREMENTS):
        if not (ROOT / skill_rel).exists():
            result.error(
                f"{skill_rel}: listed in LINK_REQUIREMENTS but the file does not exist"
            )


def check_readme_skill_counts(result: Result) -> None:
    """README prose counts must match the number of skills on disk.

    The README claimed "seven top-level and two nested" in one place and "the
    eight specialist skills" in another. Prose that restates a countable fact
    drifts unless something counts it.
    """
    readme_path = ROOT / "README.md"
    if not readme_path.exists():
        return
    text = read_text(readme_path)
    top_level, nested = discovered_skills()
    total = len(top_level) + len(nested)

    expectations = [
        (
            r"\*\*(\w+) top-level skills\*\*",
            len(top_level),
            "top-level skill count",
        ),
        (
            r"\*\*(\w+) nested support skills\*\*",
            len(nested),
            "nested support skill count",
        ),
        (
            r"the (\w+) specialist skills",
            total,
            "total specialist skill count",
        ),
    ]

    for pattern, expected, label in expectations:
        for match in re.finditer(pattern, text):
            stated = match.group(1).lower()
            expected_word = NUMBER_WORDS.get(expected, str(expected))
            if stated not in {expected_word, str(expected)}:
                line_number = text[: match.start()].count("\n") + 1
                result.error(
                    f"README.md:{line_number}: {label} says {stated!r} but "
                    f"{expected} skill(s) exist on disk (expected "
                    f"{expected_word!r})"
                )


def main() -> int:
    result = Result(errors=[], warnings=[])
    check_required_files(result)
    repo_version = check_version_consistency(result)
    check_markdown_structure(result)
    check_source_readability(result)
    check_skill_files(result, repo_version)
    check_skill_registration(result)
    check_readme_skill_counts(result)
    check_skill_link_consistency(result)
    check_skill_output_discipline(result)
    check_no_code_reviewer_model(result)
    check_forbidden_content(result)
    check_generated_files(result)
    check_env_example_marker_block(result)
    check_jira_placeholder_consistency(result)
    check_agent_skills_yaml_skills_block(result)

    for warning in result.warnings:
        print(f"WARN {warning}")
    for error in result.errors:
        print(f"FAIL {error}", file=sys.stderr)

    if result.errors:
        print(
            f"\n{len(result.errors)} validation failure(s), {len(result.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    print(f"ok: repository validation passed with {len(result.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
