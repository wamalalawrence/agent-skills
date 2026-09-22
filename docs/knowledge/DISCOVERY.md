# Shared organisational knowledge: discovery

Written before any shared-knowledge code, against the `1.2.0` release tree (commit `138b295`,
Meeting Intelligence merged and published). It extends
[the Meeting Intelligence discovery](../meeting-intelligence/DISCOVERY.md) rather than repeating
it: every subsystem named there still exists in the shape recorded there. This document records
what reads and writes knowledge today, what the shared-knowledge brief assumed, where the two
disagree, and the decisions that follow.

No genuine conflict with the brief was found. Nine deviations are recorded in the last section,
each with its reason.

## 1. Every knowledge read and write today

"Knowledge" here means the durable fact tiers. The per-task scratch (`task-context.sh`), the
blackboard, and telemetry are working state, not knowledge, and are out of scope.

### Owners

| Tier | Module | On disk | Committed |
| --- | --- | --- | --- |
| Repository: notes | `scripts/knowledge.py` `append_note` | `<repo>/.agent-skills/knowledge/project.md` | yes |
| Repository: lessons | `knowledge.py` `add_lesson`, `confirm_lesson`, `contradict_lesson`, `run_decay` | `<repo>/.agent-skills/knowledge/lessons/<id>.md` | yes |
| Repository: meeting facts | `knowledge.py` `write_meeting_facts`, `meeting_facts` | `<repo>/.agent-skills/knowledge/meetings/m_<id>.json` | yes |
| Unscoped meeting facts | `scripts/meeting_store.py` `save_pending_facts`, `load_pending_facts` | `~/.agent-skills/state/meetings/<id>/facts.json` | no |
| Project memory | `scripts/project-memory.py` | `<cache>/_projects/<slug>/memory.{md,json}` | no |
| Org memory | `scripts/org-memory.py` | `<cache>/_org/memory.{md,json}` | no |

### Call sites outside the owning module

| Id | Call site | Operation | Kind |
| --- | --- | --- | --- |
| C1 | `meeting.py:224` `resolve_scope` | `knowledge.repository_scope` | read (identity) |
| C2 | `meeting.py:463` `_prior_facts` | `knowledge.meeting_facts` | read |
| C3 | `meeting.py:496` `_finalize` | `knowledge.write_meeting_facts` | write |
| C4 | `meeting.py:564-573` `_mark_transcript_unavailable` | reads `meetings/<id>.json` **by path**, then `write_meeting_facts` | read + write |
| C5 | `meeting.py:580` `_facts_for` | reads `meetings/<id>.json` **by path** | read |
| C6 | `meeting.py:823-854` `_accept` | reads `meetings/<id>.json` **by path**, then `write_meeting_facts` | read + write |
| C7 | `eval-meeting-intelligence.py:246-258` | `repository_scope`, `write_meeting_facts`, `render_read` | read + write |
| C8 | `start-task.sh:352` | `knowledge.py read` (subprocess) | read |
| C9 | `finish-task.sh:382`, `:396` | `knowledge.py note`, `knowledge.py lesson add` (subprocess) | write |
| C10 | `doctor.sh:253-257` `probe_memory` | `find .agent-skills/knowledge/lessons` (counts files, reads no content) | presence |
| C11 | `outcome-recorder.py:60-81` | `project-memory.py`, `org-memory.py` (subprocess) | write |
| C12 | `knowledge.py` `promote_candidates` | reads project memory `memory.md` | read |
| C13 | `test-*.sh`, `test-meeting.py` | every module, by design | test |

Skills never open a knowledge file directly. The only skill reference is
`skills/wamala/references/routing-table.md:268`, which shows the `agent-skills knowledge lesson
add` CLI. Every skill reaches knowledge through `start-task` / `finish-task` or the CLI.

## 2. Fact schemas today

Four shapes, recorded in full in the Meeting Intelligence discovery §3:

- **Lesson** (`lessons/<id>.md`, front matter): a trigger → action **rule**, with confidence
  clamped to 0.3–0.9, a flat `evidence` string list, and status `active | disputed | superseded |
  archived`.
- **Note** (`project.md` bullet): free text under a section heading, with no structure.
- **Meeting fact** (`agent-skills.knowledge-meeting/v1`, one JSON file per meeting): `id, type,
  statement, status, confidence, evidence[{segment_id, start_ts, end_ts}], speakers[], owner,
  due, supersedes[{fact_id, evidence}], superseded_by, review_state, review_note, created_at`.
  The file carries `meeting_id, title, date, platform, scope{kind,key,label}, source_method,
  partial, transcript_available, notes, committed_at`.
- **Memory bullet** (project/org cache): free text, with a date prefix.

Of the brief's §3 fields, a meeting fact already holds:

| §3 field | Meeting fact | Gap |
| --- | --- | --- |
| `id` | yes, `f_` + sha256(meeting id, type, normalised statement)[:16] | derived from the meeting, not the scope (D1) |
| `type` | 10 of the 13 types | adds `DOMAIN_FACT`, `SYSTEM_OWNERSHIP`, `ENGINEERING_STANDARD` |
| `statement` | yes, redacted | — |
| `scope` | file-level `{kind: repository, key: remote:<normalised>}` | per fact, `{level, key}` |
| `status` | 6 of 7 | adds `STALE` |
| `confidence` | yes, unclamped 0–1 | — |
| `sources[]` | `evidence[]` segment refs, plus meeting title and date on the file | typed `{kind, ref, at}`; code / ticket / incident kinds |
| `produced_by` | missing | installation id, host, skill, version |
| `proposed_by`, `approved_by` | missing | derived from git, never stored in content |
| `corroborated_by[]` | missing | — |
| `created_at` | yes (date) | — |
| `last_verified_at`, `verification` | missing | — |
| `supersedes[]`, `superseded_by` | yes (`supersedes` carries evidence) | ids, as a flat list |
| `schema_version` | on the file, not the fact | per fact |
| `owner`, `due` | yes | unchanged |

`review_state` (`ACCEPTED | PENDING_REVIEW`) has no §3 counterpart. It is kept in the local view
because it is what separates a fact a human accepted into a repository from one whose scope is
unclear.

## 3. Scopes and repository identity

In practice, only one scope exists: **repository**, with **unscoped** as the pending state.
Meeting Intelligence rejects `team:`, `project:`, and `org:` with `usage-error` (its D2). The
project and org cache tiers are keyed by a workspace slug and a single `_org` directory, not by
any identity another machine could reproduce.

A repository is identified by `access.project_identity()`: `remote:<normalise_remote(origin)>`
when an `origin` remote exists, otherwise `path:<realpath>`. `normalise_remote` makes
`git@example.com:acme/api.git` and `https://example.com/acme/api` the same key. A path-keyed
repository has no identity that another machine can reproduce, so it can never bind to a shared
source.

## 4. Who owns access and scope decisions

The Access Resolver (`scripts/access.py`) owns **credential identity**: profiles, the OS secret
store, bindings from a repository identity to a credential profile, and the rule that a committed
file cannot select an identity (`tracked_state`). As the Meeting Intelligence discovery found, it
does not own knowledge scope. Knowledge isolation today is physical (the repository tier lives
in the repository), and scope is checked on read by `knowledge.meeting_facts`.

Its interface is the CLI (`access resolve/profiles/set/bind/unbind/forget/backend`) plus
in-process `resolve_access()`, `project_identity()`, `normalise_remote()`, `tracked_state()`, and
`config_dir()`.

**Decision:** knowledge-source bindings become an Access Resolver responsibility, as the brief
asks. `access.py` gains a knowledge-binding section: the persisted source list and repository
bindings (`<config_dir>/knowledge-sources.json`, `0600`), and `resolve_knowledge_binding(identity)`,
which answers `none | bound | ambiguous`. This extends the owner of "which identity applies to
this repository" instead of creating a second one.

## 5. How the runtime invokes git, and uses the user's git access

- `access.py` `run_git_checked`: local, read-only plumbing (identity, tracked state). It never
  touches a network.
- `lib/asrelease/providers/git.py` `GitReleaseProvider`: the only networked git in the product.
  It sets `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `BatchMode=yes` ssh, and a
  `GIT_CEILING_DIRECTORIES` guard. It tries the `native` strategy first (credential helpers,
  ssh-agent, `gh auth setup-git`), then the `gh` strategy, which supplies `gh auth token` through
  a temporary askpass script so the token never enters the process, argv, or disk. Stderr is
  redacted. Failures are classified by `_AUTH_MARKERS` (including GitHub's
  `repository not found` for a private repository) into exit `3`, and by `_NETWORK_MARKERS` into
  exit `4`.

**Decision:** `GitKnowledgeStore` reuses this code path by importing the provider's environment,
askpass, redaction, and classification helpers from `lib/asrelease` (already importable from
`scripts/`, and shipped in every payload). Two differences follow from the brief:

- A push uses **only** the strategy that last succeeded for that source, once. A permission
  failure goes to the fork / outbox fallback (§13.5) and is never retried with another
  credential.
- Reads may try both strategies, exactly like the installer.

## 6. Locking and concurrency

`scripts/durable.py` provides `locked(path)` (an `fcntl` advisory lock on `<path>.lock`, a 20 s
default timeout that raises `LockTimeout`, and an explicit warning when the filesystem cannot
lock), `write_text` (temporary file, fsync, `os.replace`), and `update_json` (a locked
read-modify-write that quarantines a corrupt file). Every knowledge tier already uses these.
The installer's `fcntl` lock lives in `lib/asrelease/transaction.py` and guards the install root.

**Decision:** each source has one lock, `state/knowledge/sources/<id>/source.lock`, taken by
`durable.locked` around every operation that changes the clone or the index (sync, propose,
remove). The local store's files use `update_json`. No new primitive is added.

## 7. Local index

No script uses `sqlite3` or any other database. The only index-like artefacts are Context
Optimizer's pack cache (JSON) and the telemetry JSONL. Python's `sqlite3` module is in the
standard library and present on the supported interpreters (checked here: Python 3.9.6, SQLite
3.51.0). A minimal Python build can omit it.

**Decision:** the per-source index is `sqlite3` (`state/knowledge/sources/<id>/index.sqlite`),
derived only from the clone, rebuilt whenever the clone's HEAD differs from the one it was built
from, and never authoritative. When `sqlite3` cannot be imported, the Resolver scans the clone
directly. That path returns identical results, just more slowly, and the test suite compares the
two paths.

## Mapping: current knowledge source → new owner → migration action

| Current source | New owner | Migration action |
| --- | --- | --- |
| Repository meeting facts (`meetings/*.json`) | LocalKnowledgeStore, via the Resolver | **None on disk**; unified at read time. `shareable-candidate` when remote-keyed and `ACCEPTED` |
| Unscoped pending meeting facts (`state/meetings/*/facts.json`) | LocalKnowledgeStore | None on disk; a candidate that needs a human-assigned scope first (brief §4) |
| Locally recorded facts (new: `knowledge record`) | LocalKnowledgeStore, `state/knowledge/local/facts/` | New in this release |
| Local status overlay (STALE, REJECTED, classification) | LocalKnowledgeStore, `local/overlay.json` | Written by the first-run migration |
| Shared facts | OrgKnowledgeStore → GitKnowledgeStore, `state/knowledge/sources/<id>/` | New in this release |
| Lessons (`lessons/*.md`) | Stays as-is (repository tier) | None: a rule, not a statement; already shared through the code repository's review |
| `project.md` notes | Stays as-is | None. Same reason; unstructured |
| Project memory, org memory | Stays as-is, classified personal (`task_context`) | Counted as personal by the migration; never shareable |
| Source list and repository bindings | Access Resolver (`access.py`), `<config_dir>/knowledge-sources.json` | New; category `machine_binding`, never shareable |
| Credential identities | Access Resolver (unchanged) | Category `credential_ref`, never shareable |

### Call sites after this work

| Id | Before | After |
| --- | --- | --- |
| C1-C6 | `meeting.py` → `knowledge.*`, and reads of `meetings/<id>.json` by path | `meeting.py` → `knowledge_resolver`: `repository_scope`, `prior_facts`, `write_meeting_facts`, `read_meeting_file` |
| C7 | eval → `knowledge.*` | eval → `knowledge_resolver.*` |
| C8 | `start-task.sh` → `knowledge.py read` | unchanged command; `cmd_read` renders through the Resolver, and adds a shared section only when a source is bound |
| C9 | `finish-task.sh` → `knowledge.py note` / `lesson add` | unchanged command; `cmd_note` / `cmd_lesson_*` call the Resolver, which delegates to the repository tier |
| C10 | `doctor.sh` counts lesson files | **stays as-is**: a presence probe that reads no content. The new knowledge section of `doctor` goes through `knowledge.py status --json` |
| C11, C12 | memory tiers | stay as-is (not facts; see the mapping) |

A static test (`test-shared-knowledge.py`, case 2) parses every non-test script under `scripts/`
and fails if any module other than the Resolver and the stores imports `knowledge` or builds a
`.agent-skills/knowledge` path. The only exception is `doctor.sh`'s presence probe, which is
allowlisted with this section as its reason.

## Deviations from the brief

- **D1: Meeting fact ids are kept, not re-derived.** They were derived from `(meeting id, type,
  statement)` at creation, are committed, and are referenced by `supersedes`. The brief's rule
  "stable, never reused" outranks "content-derived from type + scope + statement": re-deriving
  them would break every existing supersession link. New facts (`knowledge record`) derive ids
  from `(type, scope, normalised statement)`. Near-duplicate detection (§13.3) compares type,
  scope, and normalised statement, so an old-style id cannot hide a duplicate.
- **D2: The migration does not rewrite committed meeting files.** "Migrated in place" is met by
  presenting them in the unified schema at read time. The only thing written is the local
  classification overlay under `state/knowledge/`, which `1.2.0` never reads. This makes
  `update` then `rollback` lossless by construction: the committed files are byte-identical, and
  the previous release sees exactly what it saw before. A rewrite would have changed files in
  users' repositories and, under `1.2.0`'s schema check, hidden every meeting fact after a
  rollback.
- **D3: Lessons and `project.md` notes are not facts.** They stay in the repository tier (see
  the mapping). They are neither shareable candidates nor personal, and the migration reports
  them as "repository tier, not migrated".
- **D4: One CLI addition, `knowledge record`.** Section 11 has no way to create a local fact from
  an agent session or by hand, which the Definition of Done needs ("a meeting decision or
  agent-found fact is proposed"). `record` writes to the local store only; it never shares.
- **D5: Source discovery is `knowledge sources add` with no URL.** Section 13.1 names no command.
  `sources add` with no URL runs the pointer-file then well-known-name discovery, and every
  result is a suggestion that needs confirmation.
- **D6: Verification runs on `sync` and `knowledge verify`.** "Updated by verification, not by
  reading" rules out running it inside a query, so the code-reference check is an explicit step:
  it runs after every sync, and on demand through `knowledge verify`. Sharing a result centrally
  is `knowledge propose --mark-stale <id>` or `--reverify <id>`, both ordinary proposals.
- **D7: `doctor` does not contact a knowledge source by default.** `doctor.sh` never contacts the
  network (Meeting Intelligence D4). Reachability with current git access runs with
  `doctor --probe-knowledge`; everything else it reports (bindings, schema, sync age, index,
  setup gaps) is local.
- **D8: A fact file's `status: CONFIRMED` is a claim until git shows approval.** Section 3 says
  CONFIRMED means a human approved it, and that approval comes from the merge. The Resolver
  therefore reports a shared fact as CONFIRMED only when its introducing commit on the default
  branch is a merge (or a commit by someone other than the proposer). A file pushed straight to
  the default branch is shown as PROPOSED, with the reason. `knowledge check` also rejects
  `approved_by` / `proposed_by` in fact content.
- **D9: Exit codes.** `knowledge.py` keeps its existing `0 / 1 / 2`. Shared operations add
  `3` (authentication-required), `4` (network-failure), and `7` (verification-failure: a newer
  source schema, a deprecated source, a source whose access was lost, or a broken clone). These
  are existing codes with their frozen meanings; no new code is added.
