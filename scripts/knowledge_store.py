#!/usr/bin/env python3
"""The KnowledgeStore interface and the store that never leaves this machine.

Backend-neutral on purpose. Nothing in this interface names a branch, a commit,
or a path inside a repository: those are details of `GitKnowledgeStore`
(`knowledge_git.py`). A future `HttpKnowledgeStore` implements the same seven
methods and neither the Resolver nor any skill changes.

    get(fact_id)                          -> fact | None
    query(scope_filter, terms, types, statuses) -> [fact]
    propose(change)                       -> ProposalResult
    list_proposals()                      -> [proposal]
    sync()                                -> SyncReport
    capabilities()                        -> dict
    health()                              -> dict

Facts come back in the `knowledge_model` schema with an `_origin` key
(`local` or `shared:<source>`) and, for shared facts, `_provenance`
(`approved_by`, `proposed_by`, `review`), which are derived by the store and
never read from fact content.

`LocalKnowledgeStore` holds what must stay local: unshared and pending facts,
personal categories, the local status overlay (STALE from verification,
REJECTED from shared review), the proposal ledger, and the outbox. Everything
it keeps lives under `~/.agent-skills/state/knowledge/`, which survives update
and rollback, and which releases before 1.3.0 never read.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import knowledge_model as km
from durable import locked, update_json, write_text

LOCAL_SCHEMA = "agent-skills.knowledge-local/v1"
LEDGER_SCHEMA = "agent-skills.knowledge-proposals/v1"
PROPOSAL_STATES = ("open", "merged", "closed_unmerged")


class StoreError(Exception):
    """A store failure the CLI maps to a frozen exit code.

    kind: usage | auth | network | state | conflict | readonly
    """

    def __init__(self, message: str, kind: str = "state", hint: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.hint = hint


class KnowledgeStore:
    """The interface. Every method is required; none takes a git concept."""

    name = "abstract"

    def get(self, fact_id: str) -> Optional[dict]:
        raise NotImplementedError

    def query(self, scope_filter: Optional[List[str]] = None, terms: Iterable[str] = (),
              types: Iterable[str] = (), statuses: Iterable[str] = ()) -> List[dict]:
        raise NotImplementedError

    def propose(self, change: dict) -> dict:
        raise NotImplementedError

    def list_proposals(self) -> List[dict]:
        raise NotImplementedError

    def sync(self) -> dict:
        raise NotImplementedError

    def capabilities(self) -> dict:
        raise NotImplementedError

    def health(self) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
def home_dir() -> Path:
    home = os.environ.get("AGENT_SKILLS_HOME")
    return Path(home).expanduser() if home else Path.home() / ".agent-skills"


def knowledge_state_dir() -> Path:
    return home_dir() / "state" / "knowledge"


def local_dir() -> Path:
    return knowledge_state_dir() / "local"


def sources_dir() -> Path:
    return knowledge_state_dir() / "sources"


def outbox_dir() -> Path:
    return knowledge_state_dir() / "outbox"


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def write_private_json(path: Path, payload: object) -> None:
    private_dir(path.parent)
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", mode=0o600)


def read_json(path: Path, default: object = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        raise StoreError("unreadable knowledge state file: {}".format(path), "state")


def installation_id() -> str:
    """A random, local, non-identifying id for this installation."""
    path = knowledge_state_dir() / "installation.json"
    with locked(path):
        data = read_json(path, {}) or {}
        if not km.UUID_RE.match(str(data.get("installation_id", ""))):
            data = {"installation_id": str(uuid.uuid4()), "created_at": km.now_iso()}
            write_private_json(path, data)
    return data["installation_id"]


# ---------------------------------------------------------------------------
# Proposal ledger: open | merged | closed_unmerged, per source
# ---------------------------------------------------------------------------
class ProposalLedger:
    def __init__(self) -> None:
        self.path = local_dir() / "proposals.json"

    def _default(self) -> dict:
        return {"schema": LEDGER_SCHEMA, "proposals": {}}

    def all(self) -> List[dict]:
        data = read_json(self.path, self._default()) or self._default()
        return [dict(v, id=k) for k, v in sorted(data.get("proposals", {}).items())]

    def for_source(self, source: str) -> List[dict]:
        return [p for p in self.all() if p.get("source") == source]

    def add(self, proposal_id: str, record: dict) -> None:
        private_dir(self.path.parent)

        def change(data: dict) -> dict:
            data.setdefault("schema", LEDGER_SCHEMA)
            data.setdefault("proposals", {})[proposal_id] = record
            return data

        update_json(self.path, change, self._default())

    def set_state(self, proposal_id: str, state: str, note: str = "") -> None:
        if state not in PROPOSAL_STATES:
            raise StoreError("unknown proposal state {!r}".format(state))

        def change(data: dict) -> dict:
            entry = data.setdefault("proposals", {}).get(proposal_id)
            if entry is not None:
                entry["state"] = state
                entry["state_at"] = km.now_iso()
                if note:
                    entry["note"] = note
            return data

        update_json(self.path, change, self._default())

    def drop_source(self, source: str) -> int:
        removed = []

        def change(data: dict) -> dict:
            proposals = data.setdefault("proposals", {})
            for key in [k for k, v in proposals.items() if v.get("source") == source]:
                removed.append(key)
                del proposals[key]
            return data

        if self.path.exists():
            update_json(self.path, change, self._default())
        return len(removed)


# ---------------------------------------------------------------------------
# LocalKnowledgeStore
# ---------------------------------------------------------------------------
class LocalKnowledgeStore(KnowledgeStore):
    """Facts that have not been shared, and everything that must never be.

    Reads three places and writes two:

      * repository-tier meeting facts, through `knowledge.py` (the committed
        files are never rewritten here);
      * unscoped pending meeting facts, through `meeting_store`;
      * facts recorded with `knowledge record`, in `local/facts/<id>.json`;
      * the overlay, `local/overlay.json`: local status (STALE, REJECTED
        (shared review)), verification results, and the first-run
        classification.
    """

    name = "local"

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root
        self.facts_dir = local_dir() / "facts"
        self.overlay_path = local_dir() / "overlay.json"
        self.migration_path = local_dir() / "migration.json"
        self.ledger = ProposalLedger()

    # -- sources of local facts ---------------------------------------------
    def _meeting_facts(self) -> List[dict]:
        if self.repo_root is None:
            return []
        import knowledge

        facts, _ = knowledge.meeting_facts(self.repo_root, include_all=True)
        if not facts:
            return []
        key = knowledge.repository_scope(self.repo_root)["key"]
        out = []
        for fact in facts:
            meta = fact.get("_meeting") or {}
            file_meta = {"meeting_id": meta.get("id"), "title": meta.get("title"),
                         "date": meta.get("date"),
                         "scope": {"key": key}}
            out.append(km.from_meeting_fact(fact, file_meta))
        return out

    def _pending_meeting_facts(self) -> List[dict]:
        import meeting_store

        root = meeting_store.state_root()
        out = []
        if not root.is_dir():
            return out
        for folder in sorted(root.iterdir()):
            try:
                payload = meeting_store.load_pending_facts(folder.name)
            except Exception:  # noqa: BLE001 - a bad record must not break recall
                continue
            if not payload:
                continue
            for fact in payload.get("facts") or []:
                if isinstance(fact, dict):
                    unified = km.from_meeting_fact(fact, {
                        "meeting_id": payload.get("meeting_id"), "title": payload.get("title"),
                        "date": payload.get("date"), "scope": {"key": ""}})
                    unified["_local"]["review_state"] = "PENDING_REVIEW"
                    unified["_local"]["scope_known"] = False
                    out.append(unified)
        return out

    def _recorded_facts(self) -> List[dict]:
        out = []
        if not self.facts_dir.is_dir():
            return out
        for path in sorted(self.facts_dir.glob("f_*.json")):
            data = read_json(path, None)
            if isinstance(data, dict) and data.get("id"):
                data["_local"] = {"kind": "recorded", "review_state": "ACCEPTED", "scope_known": True}
                out.append(data)
        return out

    def overlay(self) -> dict:
        data = read_json(self.overlay_path, {}) or {}
        return data.get("facts", {}) if isinstance(data, dict) else {}

    def set_overlay(self, fact_id: str, **fields: object) -> None:
        private_dir(self.overlay_path.parent)

        def change(data: dict) -> dict:
            data.setdefault("schema", LOCAL_SCHEMA)
            entry = data.setdefault("facts", {}).setdefault(fact_id, {})
            for key, value in fields.items():
                if value is None:
                    entry.pop(key, None)
                else:
                    entry[key] = value
            return data

        update_json(self.overlay_path, change, {"schema": LOCAL_SCHEMA, "facts": {}})

    def all_facts(self, include_pending: bool = True) -> List[dict]:
        facts = self._meeting_facts() + self._recorded_facts()
        if include_pending:
            facts += self._pending_meeting_facts()
        overlay = self.overlay()
        seen: Dict[str, dict] = {}
        for fact in facts:
            if fact.get("id") in seen:
                continue
            local = overlay.get(fact["id"], {})
            review = local.get("shared_review") or {}
            if review.get("state") == "rejected" and review.get("content_hash") != km.candidate_hash(fact):
                # Changed since shared review rejected it: a new candidate (§13.6).
                local = {k: v for k, v in local.items() if k not in ("status", "shared_review")}
            if local.get("status"):
                fact["_local"]["base_status"] = fact.get("status")
                fact["status"] = local["status"]
            for key in ("verification", "last_verified_at"):
                if local.get(key):
                    fact[key] = local[key]
            if local.get("shared_review"):
                fact["_local"]["shared_review"] = local["shared_review"]
            fact["_local"]["classification"] = km.classify(fact)
            fact["_origin"] = "local"
            seen[fact["id"]] = fact
        return list(seen.values())

    # -- the interface ------------------------------------------------------
    def get(self, fact_id: str) -> Optional[dict]:
        for fact in self.all_facts():
            if fact["id"] == fact_id:
                return fact
        return None

    def query(self, scope_filter: Optional[List[str]] = None, terms: Iterable[str] = (),
              types: Iterable[str] = (), statuses: Iterable[str] = ()) -> List[dict]:
        types, statuses = set(types), set(statuses)
        out = []
        for fact in self.all_facts(include_pending=False):
            if (fact.get("_local") or {}).get("review_state") != "ACCEPTED":
                continue
            if types and fact.get("type") not in types:
                continue
            if statuses and fact.get("status") not in statuses:
                continue
            out.append(fact)
        return out

    def propose(self, change: dict) -> dict:
        raise StoreError("the local store does not accept proposals; they go to a shared source",
                         "usage")

    def list_proposals(self) -> List[dict]:
        return self.ledger.all()

    def sync(self) -> dict:
        return {"source": "local", "changed": False}

    def capabilities(self) -> dict:
        return {"read": True, "record": True, "propose": False, "shared": False}

    def health(self) -> dict:
        return {"store": "local", "facts_dir": str(self.facts_dir),
                "recorded": len(list(self.facts_dir.glob("f_*.json"))) if self.facts_dir.is_dir() else 0,
                "migrated": self.migration_path.exists()}

    # -- local writes -------------------------------------------------------
    def record(self, fact: dict) -> Path:
        """Write a locally recorded fact. Redacted, validated, never shared."""
        clean = km.redact_fact(km.shareable_body(fact))
        errors = km.validate_fact(clean, shared=False)
        if errors:
            raise StoreError("fact is not valid: " + "; ".join(errors), "usage")
        findings = km.secret_findings(clean)
        if findings:
            raise StoreError("fact still carries a credential-shaped value: " + "; ".join(findings), "usage")
        path = private_dir(self.facts_dir) / "{}.json".format(clean["id"])
        with locked(path):
            previous = read_json(path, None)
            if isinstance(previous, dict) and previous.get("created_at"):
                clean["created_at"] = previous["created_at"]
            write_private_json(path, clean)
        return path

    # -- first-run migration ------------------------------------------------
    def migrate(self, repositories: Iterable[Path] = (), from_version: str = "") -> dict:
        """Classify existing local knowledge. Idempotent and lossless.

        Nothing committed is rewritten (DISCOVERY.md D2). The record lists every
        fact seen with its content hash, so a later run, or a test, can prove
        nothing was lost across update and rollback.
        """
        private_dir(local_dir())
        with locked(self.migration_path):
            existing = read_json(self.migration_path, None)
            if isinstance(existing, dict) and existing.get("schema") == LOCAL_SCHEMA:
                return existing
            inventory: Dict[str, dict] = {}
            roots = list(repositories) + ([self.repo_root] if self.repo_root else [])
            for root in roots:
                store = LocalKnowledgeStore(root)
                for fact in store._meeting_facts():
                    inventory[fact["id"]] = {
                        "classification": km.classify(fact), "kind": "meeting",
                        "content_hash": km.content_hash(fact), "repository": str(root)}
            for fact in self._pending_meeting_facts() + self._recorded_facts():
                inventory.setdefault(fact["id"], {
                    "classification": km.classify(fact), "kind": fact["_local"]["kind"],
                    "content_hash": km.content_hash(fact)})
            record = {
                "schema": LOCAL_SCHEMA,
                "migrated_at": km.now_iso(),
                "from_version": from_version,
                "facts": inventory,
                "not_migrated": {
                    "lessons": "repository tier; a lesson is a rule, not a statement (DISCOVERY.md D3)",
                    "project_notes": "repository tier; unstructured",
                    "project_memory": "personal (task_context); never shareable",
                    "org_memory": "personal (task_context); never shareable",
                },
            }
            write_private_json(self.migration_path, record)
        for fact_id, entry in inventory.items():
            self.set_overlay(fact_id, classification=entry["classification"])
        return record
