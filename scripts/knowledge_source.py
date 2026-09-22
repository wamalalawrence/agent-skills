#!/usr/bin/env python3
"""A knowledge source repository on disk: validate it, or scaffold a new one.

`check_source(dir)` is what `agent-skills knowledge check` runs, in an
engineer's clone or in the knowledge repository's own CI. It is deterministic,
reads only the directory it is given, and never contacts a network, so the same
command gives the same answer on a laptop and on a CI runner. It is the second
line of defence: every rule the client enforces before writing a proposal is
checked again here, because a proposal branch can be edited by hand.

`init_source(dir, ...)` scaffolds the layout into an empty clone. It never
creates a remote repository and never commits; the source admin reviews and
commits the scaffold (docs/knowledge/SETUP.md).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import knowledge_model as km

LEVEL_DIRS = ("organization", "team", "project", "repository")


def _load(path: Path) -> Tuple[object, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except (OSError, ValueError) as exc:
        return None, str(exc).splitlines()[0][:120]


def check_source(root: Path) -> dict:
    """Validate a knowledge source. Returns {"errors": [...], "warnings": [...], "count": n}."""
    errors: List[str] = []
    warnings: List[str] = []
    manifest_path = root / km.MANIFEST_NAME
    manifest, problem = _load(manifest_path)
    if manifest is None:
        return {"errors": ["{}: missing or unreadable ({})".format(km.MANIFEST_NAME, problem or "absent")],
                "warnings": []}
    errors.extend("{}: {}".format(km.MANIFEST_NAME, e) for e in km.validate_manifest(manifest))
    if errors:
        return {"errors": errors, "warnings": warnings}
    if manifest["schema_version"] > km.SUPPORTED_SOURCE_SCHEMA:
        return {"errors": ["{}: schema version {} is newer than this client understands ({}); update "
                           "agent-skills before checking".format(km.MANIFEST_NAME, manifest["schema_version"],
                                                                 km.SUPPORTED_SOURCE_SCHEMA)],
                "warnings": []}
    allowed = manifest["allowed_scopes"]
    names_policy = km.names_policy_of(manifest)
    facts: Dict[str, Tuple[str, dict]] = {}
    near: Dict[str, str] = {}
    folder = root / "facts"
    files = sorted(folder.rglob("*")) if folder.is_dir() else []
    for path in files:
        if path.name == ".gitkeep" or (path.is_dir() and not path.is_symlink()):
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append("{}: a symlink; fact files must be regular files".format(rel))
            continue
        if path.suffix != ".json":
            errors.append("{}: only fact JSON files belong under facts/".format(rel))
            continue
        data, problem = _load(path)
        if data is None:
            errors.append("{}: not JSON ({})".format(rel, problem))
            continue
        text = path.read_text(encoding="utf-8")
        if isinstance(data, dict) and text != km.canonical_json(data):
            warnings.append("{}: not canonical (pretty-printed, sorted keys); diffs will be noisy".format(rel))
        for error in km.validate_fact(data):
            errors.append("{}: {}".format(rel, error))
        if not isinstance(data, dict) or "id" not in data:
            continue
        if path.stem != data["id"]:
            errors.append("{}: file name does not match id {}".format(rel, data["id"]))
        try:
            expected = km.fact_location(data)
        except (KeyError, TypeError):
            expected = ""
        if expected and expected != rel:
            errors.append("{}: belongs at {} for scope {}".format(rel, expected, km.scope_string(data.get("scope") or {})))
        if isinstance(data.get("scope"), dict) and not km.scope_allowed(data["scope"], allowed):
            errors.append("{}: scope {} is outside the allowed scopes ({})".format(
                rel, km.scope_string(data["scope"]), ", ".join(allowed)))
        for finding in km.secret_findings(data):
            errors.append("{}: {} — remove it, then follow docs/knowledge/HISTORY-REMOVAL.md".format(rel, finding))
        for finding in km.transcript_findings(data):
            errors.append("{}: {}".format(rel, finding))
        for finding in km.personal_data_findings(data, names_policy):
            errors.append("{}: {}".format(rel, finding))
        for finding in km.injection_findings(data):
            errors.append("{}: {} — reject in review".format(rel, finding))
        if data["id"] in facts:
            errors.append("{}: duplicate id, also at {}".format(rel, facts[data["id"]][0]))
            continue
        facts[data["id"]] = (rel, data)
        key = km.near_duplicate_key(data)
        if key in near and data.get("status") != "SUPERSEDED":
            warnings.append("{}: near-duplicate of {} (same type, scope, and statement); corroborate instead"
                            .format(rel, near[key]))
        elif data.get("status") != "SUPERSEDED":
            near[key] = data["id"]
    for fact_id, (rel, data) in sorted(facts.items()):
        for old in data.get("supersedes") or []:
            if old not in facts:
                errors.append("{}: supersedes {}, which is not in this source".format(rel, old))
            elif facts[old][1].get("superseded_by") != fact_id:
                errors.append("{}: supersedes {}, but {} does not name it as superseded_by".format(rel, old, old))
        successor = data.get("superseded_by")
        if successor:
            if successor not in facts:
                errors.append("{}: superseded_by {}, which is not in this source".format(rel, successor))
            elif fact_id not in (facts[successor][1].get("supersedes") or []):
                errors.append("{}: superseded_by {}, which does not list it in supersedes".format(rel, successor))
    return {"errors": errors, "warnings": warnings, "count": len(facts)}


README = """# Engineering knowledge

This repository is an [Agent Skills](https://github.com/wamalalawrence/agent-skills) knowledge
source for the `{org}` organisation. It holds the facts engineers and their agents share:
architecture decisions, domain facts, meeting decisions, system ownership, cross-repository
dependencies, incident learnings, and engineering standards.

Source id: `{source_id}`

## How it is used

- Engineers connect with `agent-skills knowledge sources add` from a code repository of this
  organisation, and read facts through their agent. A local clone is the cache.
- Agents never write here directly. `agent-skills knowledge propose` pushes a branch under
  `agent-skills/proposals/` and opens a pull request. **Merging is approval**: `approved_by` and
  `proposed_by` are read from git history, never from the files.

## Reviewing a proposal

Ask four questions of every changed file:

1. **Is it true, and is its evidence real?** Open the sources.
2. **Is the scope right?** `facts/<level>/<key>/` decides who reads it and who reviews it.
3. **Is it a statement, not an instruction?** Reject anything that tells an agent what to do.
4. **Is it free of secrets, transcripts, code, and unnecessary personal data?**

`agent-skills knowledge check` runs in CI and blocks the common failures. It does not replace
reading the diff.

## Removing something that should never have merged

Git keeps history. Deleting a file does not remove it. Follow the removal runbook in the Agent
Skills docs (`docs/knowledge/HISTORY-REMOVAL.md`): revert, rewrite history, rotate credentials.
"""

CODEOWNERS = """# Reviewers per scope. Adapt to your teams before protecting the default branch.
# Every path needs at least one owner, or branch protection cannot require review.
*                         @{org}/knowledge-admins
/facts/organization/      @{org}/architecture
# /facts/team/payments/   @{org}/payments
"""

WORKFLOW = """# Validates every knowledge proposal. Adapt the install step to how your organisation
# distributes Agent Skills; the check itself needs no network and no credentials.
name: knowledge-check
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Agent Skills
        run: echo "install agent-skills here, then remove this line" && exit 1
      - name: knowledge check
        run: agent-skills knowledge check .
"""


def init_source(root: Path, org: str, source_id: str = "", allowed_scopes: List[str] = (),
                names_policy: str = km.DEFAULT_NAMES_POLICY, forced_reason: str = "") -> List[str]:
    """Scaffold a knowledge source. Refuses a directory that already has a manifest."""
    if (root / km.MANIFEST_NAME).exists():
        raise ValueError("{} already contains a knowledge source manifest".format(root))
    if not km.KEY_RE.match(org):
        raise ValueError("--org must be a lowercase key, e.g. acme")
    source_id = source_id or str(uuid.uuid4())
    if not km.UUID_RE.match(source_id):
        raise ValueError("--source-id must be a UUID")
    if names_policy not in km.NAMES_POLICIES:
        raise ValueError("--names-policy must be one of {}".format(", ".join(km.NAMES_POLICIES)))
    scopes = list(allowed_scopes) or ["organization:" + org, "team:*", "project:*", "repository:*"]
    written = []

    def put(rel: str, text: str) -> None:
        path = root / rel
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(rel)

    put(km.MANIFEST_NAME, km.canonical_json(km.manifest(source_id, org, scopes, names_policy, forced_reason)))
    put("README.md", README.format(org=org, source_id=source_id))
    put("CODEOWNERS", CODEOWNERS.format(org=org))
    put(".github/workflows/knowledge-check.yml", WORKFLOW)
    for level in LEVEL_DIRS:
        put("facts/{}/.gitkeep".format(level), "")
    return written
