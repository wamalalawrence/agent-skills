#!/usr/bin/env python3
"""The fact model shared by the local and the organisational knowledge stores.

One schema, `agent-skills.fact/v1`, for every fact whichever store holds it. It
extends the Meeting Intelligence fact (`agent-skills.knowledge-meeting/v1`):
every field a meeting fact carries keeps its meaning, and a meeting fact is
presented in this schema by `from_meeting_fact` without its committed file ever
being rewritten (docs/knowledge/DISCOVERY.md, D2).

This module is pure: no git, no network, no store. It owns

  * the vocabulary: types, statuses, scope levels, source kinds, categories;
  * identity: content-derived ids and the normalised statement used for
    near-duplicate detection;
  * validation: a closed schema, checked the same way before a proposal is
    written and again by `knowledge check` in the knowledge repository's CI;
  * content safety: secrets, transcript-shaped text, code snippets, personal
    data, and instruction-shaped text;
  * the on-disk layout of a knowledge source (`facts/<level>/<key>/<id>.json`).

Two rules this module enforces by type rather than convention:

  * A fact whose `category` is personal (credential references, machine
    bindings, private preferences, task context) is never shareable. There is
    no flag that makes it shareable.
  * `approved_by` and `proposed_by` are never part of fact content. They are
    derived from git history by the store that reads the fact; a fact that
    carries them is rejected, because a proposer could otherwise approve
    their own statement.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

FACT_SCHEMA_VERSION = 1
MANIFEST_NAME = ".agent-skills-knowledge.json"
MANIFEST_SCHEMA = "agent-skills.knowledge-source/v1"
# The newest source layout this client can write. A manifest with a larger
# schema_version makes the client read-only for that source.
SUPPORTED_SOURCE_SCHEMA = 1

FACT_TYPES = (
    "DECISION",
    "ARCHITECTURE_DECISION",
    "ACTION",
    "REQUIREMENT",
    "CONSTRAINT",
    "RISK",
    "ASSUMPTION",
    "OPEN_QUESTION",
    "DEPENDENCY",
    "INCIDENT_FACT",
    "DOMAIN_FACT",
    "SYSTEM_OWNERSHIP",
    "ENGINEERING_STANDARD",
)
STATUSES = ("CONFIRMED", "PROPOSED", "OPEN", "REJECTED", "SUPERSEDED", "UNCERTAIN", "STALE")
# Ranking order: settled first, then open, then the ones that must not be
# presented as settled.
STATUS_RANK = {s: i for i, s in enumerate(
    ("CONFIRMED", "PROPOSED", "OPEN", "UNCERTAIN", "STALE", "REJECTED", "SUPERSEDED"))}
SCOPE_LEVELS = ("repository", "project", "team", "organization")
SOURCE_KINDS = ("meeting", "code", "ticket", "incident", "manual", "agent_session")
HOSTS = ("claude-code", "cursor", "codex", "copilot", "cli")
VERIFICATION_METHODS = ("code_ref_check", "human", "meeting")
SUPERSEDABLE_TYPES = ("DECISION", "ARCHITECTURE_DECISION", "REQUIREMENT", "CONSTRAINT",
                      "ENGINEERING_STANDARD", "SYSTEM_OWNERSHIP", "DOMAIN_FACT", "DEPENDENCY")

SHARED_CATEGORY = "fact"
# Never eligible for a shared store, whatever the caller asks.
PERSONAL_CATEGORIES = ("credential_ref", "machine_binding", "preference", "task_context")
CATEGORIES = (SHARED_CATEGORY,) + PERSONAL_CATEGORIES

# Person-name policy, set per source in the manifest.
NAMES_POLICIES = ("action_owners_only", "none", "allowed")
DEFAULT_NAMES_POLICY = "action_owners_only"

MAX_STATEMENT_CHARS = 280
MAX_TEXT_CHARS = 200
LOW_CONFIDENCE = 0.5

ID_RE = re.compile(r"^f_[0-9a-f]{16}$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
REPO_KEY_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]+)?(?:/[a-z0-9._~-]+){1,8}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

FACT_FIELDS = {
    "id", "type", "statement", "scope", "status", "confidence", "sources", "produced_by",
    "corroborated_by", "created_at", "last_verified_at", "verification", "supersedes",
    "superseded_by", "schema_version", "category", "owner", "due", "imported_from",
}
REQUIRED_FIELDS = {"id", "type", "statement", "scope", "status", "confidence", "sources",
                   "created_at", "schema_version", "category"}
# Derived from git by the reading store. Present in content = forged.
DERIVED_FIELDS = ("approved_by", "proposed_by")
SOURCE_FIELDS = {
    "meeting": {"kind", "ref", "at", "title", "offsets"},
    "code": {"kind", "ref", "at", "repo", "commit", "path", "lines", "snippet_sha256"},
    "ticket": {"kind", "ref", "at", "system", "key"},
    "incident": {"kind", "ref", "at"},
    "manual": {"kind", "ref", "at"},
    "agent_session": {"kind", "ref", "at"},
}


class FactError(ValueError):
    """A fact that does not satisfy the schema or the content rules."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def normalise_statement(text: str) -> str:
    # Identical to meeting_intel.normalise_statement, so a meeting fact and a
    # recorded fact saying the same thing normalise to the same string.
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).split())


def scope_string(scope: dict) -> str:
    return "{}:{}".format(scope.get("level", "?"), scope.get("key", "?"))


def parse_scope(value: str) -> dict:
    """`team:payments`, `organization:acme`, `repository:<remote>` -> scope."""
    level, sep, key = str(value).partition(":")
    level = {"org": "organization", "repo": "repository"}.get(level, level)
    if not sep or level not in SCOPE_LEVELS or not key:
        raise FactError("scope must be <level>:<key> with level one of {}: {!r}".format(
            ", ".join(SCOPE_LEVELS), value))
    key = key.strip().lower()
    if level == "repository":
        # Accept any remote form; the key is the normalised remote.
        key = re.sub(r"^remote:", "", key)
        key = _normalise_remote(key)
        if not REPO_KEY_RE.match(key):
            raise FactError("repository scope needs a normalised remote, e.g. "
                            "repository:github.com/acme/api: {!r}".format(value))
    elif not KEY_RE.match(key):
        raise FactError("scope key must be lowercase letters, digits, '.', '_' or '-': {!r}".format(key))
    return {"level": level, "key": key}


def _normalise_remote(url: str) -> str:
    from access import normalise_remote

    return normalise_remote(url)


def fact_id(fact_type: str, scope: dict, statement: str) -> str:
    """Content-derived at creation: type + scope + normalised statement.

    Computed once, when a fact is first recorded, and never recomputed: a later
    edit to the statement keeps the id, and an id is never reused for another
    fact. Meeting facts keep the ids Meeting Intelligence gave them (D1).
    """
    raw = "{}|{}|{}".format(fact_type, scope_string(scope), normalise_statement(statement))
    return "f_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def near_duplicate_key(fact: dict) -> str:
    """Conservative near-duplicate identity: same type, scope, and statement."""
    return "{}|{}|{}".format(fact.get("type"), scope_string(fact.get("scope") or {}),
                             normalise_statement(fact.get("statement", "")))


def content_hash(fact: dict) -> str:
    """Hash of the shareable content, independent of key order and derived data."""
    clean = {k: v for k, v in fact.items() if k in FACT_FIELDS}
    return hashlib.sha256(canonical_json(clean).encode("utf-8")).hexdigest()


def candidate_hash(fact: dict) -> str:
    """Hash of what a proposal would share, ignoring the local view's overlay.

    Used to tell whether a fact rejected in shared review has changed since.
    """
    body = shareable_body(fact)
    base = (fact.get("_local") or {}).get("base_status")
    if base:
        body["status"] = base
    for key in ("produced_by", "verification", "last_verified_at"):
        body.pop(key, None)
    return content_hash(body)


def canonical_json(data: object) -> str:
    """Pretty-printed, sorted keys, trailing newline: line-level diffs."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def repository_dir_key(repo_key: str) -> str:
    return hashlib.sha256(repo_key.encode("utf-8")).hexdigest()[:16]


def fact_location(fact: dict) -> str:
    """Where a fact lives inside a knowledge source. One fact per file."""
    scope = fact.get("scope") or {}
    level, key = scope.get("level"), scope.get("key", "")
    if level == "organization":
        return "facts/organization/{}.json".format(fact["id"])
    if level == "repository":
        return "facts/repository/{}/{}.json".format(repository_dir_key(key), fact["id"])
    return "facts/{}/{}/{}.json".format(level, key, fact["id"])


# ---------------------------------------------------------------------------
# Scope policy
# ---------------------------------------------------------------------------
def scope_allowed(scope: dict, patterns: Iterable[str]) -> bool:
    """Whether a scope is inside a manifest's `allowed_scopes` patterns."""
    import fnmatch

    text = scope_string(scope)
    return any(fnmatch.fnmatchcase(text, pattern) for pattern in patterns)


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------
# Speaker turns and caption timestamps: the shapes a pasted transcript has.
_SPEAKER_TURN = re.compile(
    r"(?m)(?:^|(?<=[.!?])\s)\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?"
    r"[A-Z][\w'.-]{1,20}(?: [A-Z][\w'.-]{1,20})?:\s+\S")
_CAPTION_STAMP = re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?\s*-->")
_CODE_SHAPE = re.compile(r"```|;\s*$|^\s*(?:def|class|function|import|from|return)\b|[{}]\s*$", re.M)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_MENTION = re.compile(r"(?<![\w@])@[A-Za-z][\w.-]{1,38}\b")


def _text_fields(fact: dict) -> List[Tuple[str, str]]:
    """Every free-text value a fact carries, with a label for findings."""
    out = [("statement", str(fact.get("statement", "")))]
    if fact.get("owner"):
        out.append(("owner", str(fact["owner"])))
    for group in ("sources", "corroborated_by"):
        for index, source in enumerate(fact.get(group) or []):
            if not isinstance(source, dict):
                continue
            for field in ("ref", "title", "path", "system", "key", "repo"):
                if source.get(field):
                    out.append(("{}[{}].{}".format(group, index, field), str(source[field])))
    return out


def secret_findings(fact: dict) -> List[str]:
    """Credential-shaped values, by every pattern set the runtime has."""
    from guard_audit import redact
    from knowledge import SECRET_PATTERNS
    from meeting_secrets import redact_text

    found = []
    for label, text in _text_fields(fact):
        if any(p.search(text) for p in SECRET_PATTERNS):
            found.append("{}: credential-shaped value".format(label))
        elif redact(text) != text or redact_text(text)[1]:
            found.append("{}: credential-shaped value".format(label))
    return found


def transcript_findings(fact: dict) -> List[str]:
    """Transcript text, raw meeting text, or code beyond a short reference."""
    found = []
    statement = str(fact.get("statement", ""))
    if "\n" in statement:
        found.append("statement: spans several lines (one sentence expected)")
    if len(statement) > MAX_STATEMENT_CHARS:
        found.append("statement: longer than {} characters".format(MAX_STATEMENT_CHARS))
    for label, text in _text_fields(fact):
        turns = len(_SPEAKER_TURN.findall(text))
        # Three turns on one line, or two across lines: "Decision: x. Reason: y."
        # alone is a statement, not a transcript.
        if turns >= 3 or (turns >= 2 and "\n" in text) or _CAPTION_STAMP.search(text):
            found.append("{}: reads as transcript text".format(label))
        if label != "statement" and len(text) > MAX_TEXT_CHARS:
            found.append("{}: longer than {} characters".format(label, MAX_TEXT_CHARS))
        if _CODE_SHAPE.search(text) and ("\n" in text or "```" in text):
            found.append("{}: carries a code snippet (store a path, lines, and a hash)".format(label))
    return found


def personal_data_findings(fact: dict, names_policy: str = DEFAULT_NAMES_POLICY) -> List[str]:
    found = []
    for label, text in _text_fields(fact):
        if _EMAIL.search(text):
            found.append("{}: contains an email address".format(label))
    if names_policy != "allowed":
        if _MENTION.search(str(fact.get("statement", ""))):
            found.append("statement: names a person (@handle); policy {}".format(names_policy))
        if fact.get("owner") and (names_policy == "none" or fact.get("type") != "ACTION"):
            found.append("owner: person names are allowed only for ACTION owners (policy {})".format(
                names_policy))
    return found


def injection_findings(fact: dict) -> List[str]:
    from context import looks_like_instruction
    from knowledge import INJECTION_PATTERNS

    found = []
    for label, text in _text_fields(fact):
        if looks_like_instruction(text) or any(p.search(text) for p in INJECTION_PATTERNS):
            found.append("{}: reads as an instruction to an agent, not a fact".format(label))
    return found


def looks_like_instruction(text: str) -> bool:
    from context import looks_like_instruction as ctx
    from knowledge import INJECTION_PATTERNS

    return ctx(text) or any(p.search(text) for p in INJECTION_PATTERNS)


def redact_fact(fact: dict) -> dict:
    """Redact free-text fields only.

    Structural fields (ids, commit SHAs, hashes, dates) are validated by strict
    patterns instead. The shared high-entropy redactor would otherwise erase a
    40-character commit SHA, which is exactly the provenance a code reference
    needs.
    """
    from guard_audit import redact
    from meeting_secrets import redact_text

    def clean(value: str) -> str:
        return redact_text(redact(value))[0]

    out = json.loads(json.dumps(fact))
    out["statement"] = clean(str(out.get("statement", "")))
    if out.get("owner"):
        out["owner"] = clean(str(out["owner"]))
    for group in ("sources", "corroborated_by"):
        for source in out.get(group) or []:
            if isinstance(source, dict):
                for field in ("ref", "title", "system", "key"):
                    if source.get(field) and not (field == "ref" and source.get("kind") == "code"):
                        source[field] = clean(str(source[field]))
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _valid_source(source: object, label: str) -> List[str]:
    if not isinstance(source, dict):
        return ["{}: not an object".format(label)]
    errors = []
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        return ["{}: kind {!r} is not one of {}".format(label, kind, ", ".join(SOURCE_KINDS))]
    extra = set(source) - SOURCE_FIELDS[kind]
    if extra:
        errors.append("{}: unknown field(s) {}".format(label, ", ".join(sorted(extra))))
    if not str(source.get("ref", "")).strip():
        errors.append("{}: missing ref".format(label))
    if source.get("at") and not ISO_RE.match(str(source["at"])):
        errors.append("{}: at is not an ISO date".format(label))
    if kind == "code":
        if source.get("commit") and not SHA_RE.match(str(source["commit"])):
            errors.append("{}: commit is not a hex SHA".format(label))
        if source.get("snippet_sha256") and not HASH_RE.match(str(source["snippet_sha256"])):
            errors.append("{}: snippet_sha256 is not a sha256 hex digest".format(label))
        lines = source.get("lines")
        if lines is not None and not (
            isinstance(lines, list) and len(lines) == 2 and all(isinstance(n, int) and n > 0 for n in lines)
            and lines[0] <= lines[1]
        ):
            errors.append("{}: lines must be [start, end]".format(label))
        if not source.get("path"):
            errors.append("{}: a code source needs a path".format(label))
    if kind == "meeting":
        offsets = source.get("offsets")
        if offsets is not None and not (
            isinstance(offsets, list) and all(isinstance(n, (int, float)) and n >= 0 for n in offsets)
        ):
            errors.append("{}: offsets must be seconds".format(label))
    return errors


def validate_fact(fact: object, shared: bool = True) -> List[str]:
    """Closed-schema validation. Returns a list of errors; empty means valid."""
    if not isinstance(fact, dict):
        return ["fact is not an object"]
    errors = []
    for field in DERIVED_FIELDS:
        if field in fact:
            errors.append("{} is derived from git and must not be written in a fact".format(field))
    extra = set(fact) - FACT_FIELDS - set(DERIVED_FIELDS)
    if extra:
        errors.append("unknown field(s): {}".format(", ".join(sorted(extra))))
    missing = REQUIRED_FIELDS - set(fact)
    if missing:
        errors.append("missing field(s): {}".format(", ".join(sorted(missing))))
        return errors
    if not ID_RE.match(str(fact["id"])):
        errors.append("id {!r} is not f_ + 16 hex characters".format(fact["id"]))
    if fact["type"] not in FACT_TYPES:
        errors.append("type {!r} is unknown".format(fact["type"]))
    if fact["status"] not in STATUSES:
        errors.append("status {!r} is unknown".format(fact["status"]))
    if not isinstance(fact["statement"], str) or not fact["statement"].strip():
        errors.append("statement is empty")
    if fact["category"] not in CATEGORIES:
        errors.append("category {!r} is unknown".format(fact["category"]))
    elif shared and fact["category"] != SHARED_CATEGORY:
        errors.append("category {} is personal and never shareable".format(fact["category"]))
    if fact["schema_version"] != FACT_SCHEMA_VERSION:
        errors.append("schema_version {!r} is not {}".format(fact["schema_version"], FACT_SCHEMA_VERSION))
    scope = fact["scope"]
    if not isinstance(scope, dict) or set(scope) != {"level", "key"}:
        errors.append("scope must be {level, key}")
    else:
        try:
            parsed = parse_scope(scope_string(scope))
            if parsed != scope:
                errors.append("scope {} is not normalised".format(scope_string(scope)))
        except FactError as exc:
            errors.append(str(exc))
    confidence = fact["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("confidence must be a number between 0 and 1")
    sources = fact["sources"]
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
    else:
        for index, source in enumerate(sources):
            errors.extend(_valid_source(source, "sources[{}]".format(index)))
    for index, source in enumerate(fact.get("corroborated_by") or []):
        errors.extend(_valid_source(source, "corroborated_by[{}]".format(index)))
    if not ISO_RE.match(str(fact["created_at"])):
        errors.append("created_at is not an ISO date")
    if fact.get("last_verified_at") and not ISO_RE.match(str(fact["last_verified_at"])):
        errors.append("last_verified_at is not an ISO date")
    verification = fact.get("verification")
    if verification is not None:
        if not isinstance(verification, dict) or verification.get("method") not in VERIFICATION_METHODS:
            errors.append("verification.method must be one of {}".format(", ".join(VERIFICATION_METHODS)))
    supersedes = fact.get("supersedes") or []
    if not isinstance(supersedes, list) or not all(isinstance(s, str) and ID_RE.match(s) for s in supersedes):
        errors.append("supersedes must be a list of fact ids")
    elif fact["id"] in supersedes:
        errors.append("a fact cannot supersede itself")
    replaced_by = fact.get("superseded_by")
    if replaced_by is not None and not (isinstance(replaced_by, str) and ID_RE.match(replaced_by)):
        errors.append("superseded_by must be a fact id or null")
    if fact["status"] == "SUPERSEDED" and not replaced_by:
        errors.append("a SUPERSEDED fact must name superseded_by")
    if replaced_by and fact["status"] != "SUPERSEDED":
        errors.append("superseded_by is set but status is {}".format(fact["status"]))
    produced = fact.get("produced_by")
    if produced is not None:
        if not isinstance(produced, dict) or set(produced) - {"installation_id", "host", "skill",
                                                              "agent_skills_version"}:
            errors.append("produced_by has unknown fields")
        elif produced.get("host") and produced["host"] not in HOSTS:
            errors.append("produced_by.host {!r} is unknown".format(produced["host"]))
    if (fact.get("owner") or fact.get("due")) and fact["type"] != "ACTION":
        # Owner and due come over from Meeting Intelligence for ACTION facts only.
        errors.append("owner/due are only valid on ACTION facts")
    if fact.get("due") and not ISO_RE.match(str(fact["due"])):
        errors.append("due is not an ISO date")
    imported = fact.get("imported_from")
    if imported is not None and not (
        isinstance(imported, dict) and set(imported) <= {"source_id", "fact_id", "url"}
        and ID_RE.match(str(imported.get("fact_id", "")))
    ):
        errors.append("imported_from must be {source_id, fact_id, url}")
    return errors


def content_findings(fact: dict, names_policy: str = DEFAULT_NAMES_POLICY) -> List[str]:
    """Everything that must block a fact from reaching a shared store."""
    return (secret_findings(fact) + transcript_findings(fact)
            + personal_data_findings(fact, names_policy) + injection_findings(fact))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def new_fact(
    fact_type: str,
    statement: str,
    scope: dict,
    sources: List[dict],
    status: str = "PROPOSED",
    confidence: float = 0.7,
    category: str = SHARED_CATEGORY,
    produced_by: Optional[dict] = None,
    owner: str = "",
    due: str = "",
) -> dict:
    fact = {
        "id": fact_id(fact_type, scope, statement),
        "type": fact_type,
        "statement": " ".join(str(statement).split()),
        "scope": scope,
        "status": status,
        "confidence": round(float(confidence), 3),
        "sources": sources,
        "produced_by": produced_by or {},
        "corroborated_by": [],
        "created_at": now_iso(),
        "last_verified_at": None,
        "verification": None,
        "supersedes": [],
        "superseded_by": None,
        "schema_version": FACT_SCHEMA_VERSION,
        "category": category,
    }
    if owner:
        fact["owner"] = owner
    if due:
        fact["due"] = due
    return fact


def parse_source(value: str) -> dict:
    """`kind:ref` from the command line into a source object.

    `code:<remote>@<sha>:<path>#L<start>-<end>` is expanded into its fields so the
    code-reference check can use them.
    """
    kind, sep, ref = str(value).partition(":")
    if not sep or kind not in SOURCE_KINDS or not ref:
        raise FactError("source must be <kind>:<ref> with kind one of {}".format(", ".join(SOURCE_KINDS)))
    source = {"kind": kind, "ref": ref, "at": now_iso()[:10]}
    if kind == "code":
        match = re.match(r"^(?P<repo>[^@]+)@(?P<sha>[0-9a-f]{7,64}):(?P<path>[^#]+)"
                         r"(?:#L(?P<a>\d+)(?:-L?(?P<b>\d+))?)?$", ref)
        if not match:
            raise FactError("code source must be <remote>@<sha>:<path>[#L<start>-<end>]")
        source.update({"repo": _normalise_remote(match["repo"]), "commit": match["sha"],
                       "path": match["path"]})
        if match["a"]:
            source["lines"] = [int(match["a"]), int(match["b"] or match["a"])]
    if kind == "ticket":
        system, _, key = ref.partition(":")
        if key:
            source.update({"system": system, "key": key})
    return source


def from_meeting_fact(fact: dict, file_meta: dict) -> dict:
    """Present a Meeting Intelligence fact in the unified schema.

    Nothing is dropped from the meeting fact that the unified schema can hold;
    `speakers` and `review_state` are local-only and kept beside it under
    `_local`, never in the shareable body.
    """
    scope_meta = file_meta.get("scope") or {}
    key = str(scope_meta.get("key", ""))
    if key.startswith("remote:"):
        scope = {"level": "repository", "key": key[len("remote:"):]}
    else:
        # A path-keyed or unscoped meeting has no identity another machine
        # can reproduce; it keeps a placeholder scope and is never shareable
        # until a human assigns one.
        scope = {"level": "repository", "key": ""}
    offsets = []
    for item in fact.get("evidence") or []:
        if isinstance(item, dict) and isinstance(item.get("start_ts"), (int, float)):
            offsets.append(round(float(item["start_ts"]), 2))
    source = {
        "kind": "meeting",
        "ref": str(file_meta.get("meeting_id", "")),
        "at": str(file_meta.get("date", ""))[:10] or str(fact.get("created_at", ""))[:10],
        "title": str(file_meta.get("title", ""))[:MAX_TEXT_CHARS],
        "offsets": offsets[:20],
    }
    unified = {
        "id": fact.get("id"),
        "type": fact.get("type"),
        "statement": fact.get("statement", ""),
        "scope": scope,
        "status": fact.get("status"),
        "confidence": fact.get("confidence", 0),
        "sources": [source],
        "produced_by": {"skill": "meeting-intelligence"},
        "corroborated_by": [],
        "created_at": str(fact.get("created_at", ""))[:10],
        "last_verified_at": None,
        "verification": None,
        "supersedes": [s["fact_id"] for s in fact.get("supersedes") or [] if isinstance(s, dict)
                       and s.get("fact_id")],
        "superseded_by": fact.get("superseded_by") if fact.get("status") == "SUPERSEDED" else None,
        "schema_version": FACT_SCHEMA_VERSION,
        "category": SHARED_CATEGORY,
    }
    if fact.get("type") == "ACTION":
        if fact.get("owner"):
            unified["owner"] = fact["owner"]
        if fact.get("due"):
            unified["due"] = fact["due"]
    unified["_local"] = {
        "kind": "meeting",
        "review_state": fact.get("review_state"),
        "review_note": fact.get("review_note", ""),
        "speakers": list(fact.get("speakers") or []),
        "scope_known": bool(scope["key"]),
    }
    return unified


def shareable_body(fact: dict) -> dict:
    """The exact content written to a shared store: no local-only keys."""
    body = {k: v for k, v in fact.items() if k in FACT_FIELDS}
    body.setdefault("corroborated_by", [])
    body.setdefault("supersedes", [])
    body.setdefault("superseded_by", None)
    body.setdefault("last_verified_at", None)
    body.setdefault("verification", None)
    body.setdefault("produced_by", {})
    return body


def classify(fact: dict) -> str:
    """`personal` (never shareable) or `shareable-candidate`."""
    if fact.get("category") in PERSONAL_CATEGORIES:
        return "personal"
    local = fact.get("_local") or {}
    if local.get("kind") == "meeting" and not local.get("scope_known") and local.get("review_state") \
            == "ACCEPTED":
        # Accepted into a path-keyed repository: bound to this machine.
        return "personal"
    return "shareable-candidate"


def manifest(source_id: str, org: str, allowed_scopes: List[str], names_policy: str,
             forced_reason: str = "") -> dict:
    data = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SUPPORTED_SOURCE_SCHEMA,
        "source_id": source_id,
        "org": org,
        "status": "active",
        "successor": None,
        "allowed_scopes": allowed_scopes,
        "policy": {
            "person_names": names_policy,
            "require_review": True,
        },
    }
    if forced_reason:
        data["created_despite_existing_source"] = forced_reason
    return data


def validate_manifest(data: object) -> List[str]:
    if not isinstance(data, dict):
        return ["manifest is not a JSON object"]
    errors = []
    if data.get("schema") != MANIFEST_SCHEMA:
        errors.append("manifest schema is not {}".format(MANIFEST_SCHEMA))
    if not isinstance(data.get("schema_version"), int) or data["schema_version"] < 1:
        errors.append("manifest schema_version must be a positive integer")
    if not UUID_RE.match(str(data.get("source_id", ""))):
        errors.append("manifest source_id must be a UUID")
    if not KEY_RE.match(str(data.get("org", ""))):
        errors.append("manifest org must be a lowercase key")
    if data.get("status") not in ("active", "deprecated"):
        errors.append("manifest status must be active or deprecated")
    if data.get("status") == "deprecated" and not data.get("successor"):
        errors.append("a deprecated manifest must name its successor")
    scopes = data.get("allowed_scopes")
    if not isinstance(scopes, list) or not scopes or not all(isinstance(s, str) for s in scopes):
        errors.append("manifest allowed_scopes must be a non-empty list of patterns")
    policy = data.get("policy") or {}
    if policy.get("person_names", DEFAULT_NAMES_POLICY) not in NAMES_POLICIES:
        errors.append("manifest policy.person_names must be one of {}".format(", ".join(NAMES_POLICIES)))
    return errors


def names_policy_of(manifest_data: Optional[dict]) -> str:
    policy = (manifest_data or {}).get("policy") or {}
    value = policy.get("person_names", DEFAULT_NAMES_POLICY)
    return value if value in NAMES_POLICIES else DEFAULT_NAMES_POLICY


def summary_line(fact: dict) -> str:
    return "{} {} [{} · {}] {}".format(fact.get("id"), scope_string(fact.get("scope") or {}),
                                        fact.get("type"), fact.get("status"), fact.get("statement"))


def index_by_id(facts: Iterable[dict]) -> Dict[str, dict]:
    return {f["id"]: f for f in facts if isinstance(f, dict) and f.get("id")}
