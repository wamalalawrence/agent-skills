# Eval run — v0.44.0 (Engineering Tool Capability Framework)

Release-scoped evidence for `v0.44.0`. Everything below was produced by running the commands
named, not by assertion.

## What this release changed

Agent Skills gained a layer between "a skill knows what engineering work it needs" and "a
credential is resolved": the Engineering Tool Capability Framework. A skill names a **capability**
(`ci.logs.read`, `database.query.read`, `infrastructure.plan`); `scripts/tools.py` walks a fixed
transport order and reports how that capability can be provided on this machine.

```text
skill ─> required capability ─> Engineering Tool Resolver
        host ─> mcp ─> authenticated CLI ─> local/native client ─> profile ─> API ─> unresolved
             │                                              │
   needs auth? ─> agent-skills access resolve      dangerous? ─> Execution Guard
```

It authenticates nothing (that stays with the Access Resolver) and enforces nothing (that stays
with the Execution Guard). It classifies every capability `READ | WRITE | ELEVATED | DESTRUCTIVE`
so a skill knows the blast radius before it proposes a command.

New: `scripts/tools.py`, `lib/tools/capabilities.json`, `lib/tools/classes.json`,
`lib/tools/registry.d/*.json` (16 reference tools), `lib/tools/fixtures/*.json` (4 extensibility
fixtures), `scripts/test-tools.sh`, `docs/engineering-tools.md`,
`docs/engineering-tool-capabilities.md`, `evals/engineering-tools-capability-resolution.md`,
`agent-skills tools` CLI, a `check_engineering_tools` gate in `validate-repo.py`.

Also: the repository's former MIT license is removed (private repo → proprietary notice, no
invented terms).

## Verification

| Gate | Result |
| --- | --- |
| `validate-repo.py` | pass — 61 warnings (was 64 at v0.43.1; licensing rewrites removed 3) |
| `run-evals.py` | pass — 48 files, 11 skills known, 0 failures, 0 warnings |
| `scripts/test-tools.sh` | pass — 41 assertions |
| `test-access-resolution.sh` | pass — 100 assertions |
| `test-guard.sh` | pass — 108 assertions (54 rules, 31 floor; unchanged) |
| `test-context-optimizer.sh` | pass — 105 checks |
| `test-cli-install.sh` | pass — 104 assertions |
| `test-release-engine.py` | pass — 21 checks |
| `audit-npm-package.sh` | pass — 14 files, no product content, version matches VERSION |
| `bash -n` across `bin`, `lib`, `scripts` | pass |
| `python3 -m py_compile scripts/*.py` | pass |
| `test-release-readiness.sh` | pass — 80/80 after three pre-existing release-harness bugs were fixed (see below) |

### test-release-readiness.sh — pre-existing harness bugs fixed in this release

Successive runs surfaced three failures, all in the release **harness**, not the product, and
all a consequence of state that predates v0.44.0 (the `--yes` bug since v0.38.0; the private-repo
transition and README drift since v0.43.1):

1. **`FAIL v0.43.1 install` — bad flag.** Sections 6 / 6b ran the *previous release's* installer
   as `agent-skills install --yes`. No `install` subcommand has ever accepted `--yes` (it is a
   flag on `uninstall`); v0.43.1 and `main` `install.py` both reject it. Removed from both calls.
2. **`FAIL v0.43.1 install` — private source.** With the flag fixed, the baseline install then
   failed because the v0.43.1 installer defaults to the git provider and re-fetched
   `github.com/wamalalawrence/agent-skills` from a throwaway `$HOME` with no credentials — the
   repo is private. Section 6 is about upgrade mechanics and state preservation, not distribution
   access (that is `scripts/test-private-source.sh`). Fixed to install the previous tag from its
   own on-disk tree: `--provider local --source "$UP_OLD"`, matching section 6b and section 6's
   own upgrade-to-this-release step. Verified in isolation: `install rc=0`, `install.json`
   present, `wamala` registered.
3. **`FAIL v0.43.1 registration`** — cascade from (1)/(2); passes once the install succeeds.
4. **`FAIL README`** — the harness required bold count prose `**N top-level skills**` /
   `**N nested support skills**` that the README had dropped in favour of "the eleven skills".
   Restored the bold prose (`**Nine top-level skills**`, `**Two nested support skills**`), which
   `validate-repo.py`'s own `check_readme_skill_counts` now also verifies against the 9 + 2 on
   disk.

Telemetry (`agent-skills telemetry report --all`, from the sandboxed run):

```json
{ "total_events": 2, "skills": { "software-engineer": { "completed": 1 },
  "manual-tester": { "completed": 1 } }, "unknown_events": {} }
```

No telemetry finding drove a skill change this release.

## test-tools.sh — the 14 required proofs

| No. | Proof | Cases |
| --- | --- | --- |
| 1 | tool discovery works | `list`, `list --json` (≥16), `doctor`, `capabilities` |
| 2 | local tool vs remote service handled differently | `LOCAL_TOOL` missing → `UNAVAILABLE`; `REMOTE_SERVICE` unconfigured → `NEEDS SETUP` |
| 3 | an authenticated capability beats a stored credential | fake logged-in CLI (rank 3) wins over API adapter (rank 6) even with a resolving credential stub |
| 4 | GitHub / Jira still resolve through the framework | reuse `github-access.md` / `auth-discovery.md`; `resolve` only ever calls `access resolve --service <own>` |
| 5 | AWS / Kubernetes / Terraform action classification | `plan`=READ, `apply`=ELEVATED, `destroy`/`delete`=DESTRUCTIVE; `resolve` blocks ELEVATED without `--allow-write` (exit 2) |
| 6 | PostgreSQL production query bounded / read-only | `database.query.read` is READ + bounded; `database.write` blocked without `--allow-write` |
| 7 | Context Optimizer bounds large tool output | 64k-line pod log → `context check` exit 10; `context pack` keeps the `OOMKilled` line |
| 8 | malicious external text stays untrusted | stdin poison does not change a classification; `guard scan-content` flags it |
| 9 | provider failure is isolated | one probe failing → `status` still reports every tool, exit 0 |
| 10 | multiple identities → no wrong-account selection | each tool delegates only its own `auth_service`; no cross-service call |
| 11 | READ cannot escalate to WRITE | `--allow-write` cannot raise `database.query.read` above READ; no `*.read` capability is a mutation |
| 12 | destructive op still blocked by Execution Guard | framework says DESTRUCTIVE **and** `guard check-command` denies `terraform destroy` / `DROP TABLE` (exit 20) |
| 13 | an unknown future tool needs no core change | a new definition file is discovered / inspected / classified with zero code change; `tools.py` contains no hardcoded provider id |
| 14 | GitLab / GCP / MySQL / New Relic fixtures fit with no special branch | all four load through the same path; opt-in and labelled; `doctor` passes with them |

## Framework shape

```text
tool classes       AGENT_HOST  LOCAL_TOOL  REMOTE_SERVICE  RUNTIME_RESOURCE  DATA_RESOURCE
capability families 18 (scm tracker knowledge communication runtime infrastructure cloud api
                       ci quality observability incident messaging database data_pipeline
                       package design security)
capabilities       72
action classes     READ  WRITE  ELEVATED  DESTRUCTIVE
transports         host  mcp  cli  native-client  profile  api  (+ unresolved)
reference tools    github github-actions jenkins jira confluence slack aws kubernetes terraform
                   postman sonarqube sentry pagerduty kafka postgresql npm      (16, validated)
fixtures           gitlab gcp mysql newrelic                                    (4, not supported)
```

## Developer workflows covered by the design

Production incident, ticket implementation, PR review, CI failure, runtime failure (pod
restart), infrastructure change (plan only), API debugging, production regression (Sentry →
release → commits), database performance (EXPLAIN + schema), messaging backlog (consumer lag),
code-quality finding (retrieve → route to `software-engineer`), incident history, knowledge
lookup. Each is a specialist-skill scenario that now requests capabilities after Wamala routes by
ownership. `evals/engineering-tools-capability-resolution.md` scores the incident path through
`issue-investigator`.

## Licensing

`LICENSE` is now an all-rights-reserved proprietary notice. `SKILL.md` `license:` →
`PROPRIETARY`. `npm/package.json` → `UNLICENSED`. Public-project wording removed from `README.md`,
`CONTRIBUTING.md`, `SUPPORT.md`, `GOVERNANCE.md`. npm publication deferred — distribution is
git-provider (tag + GitHub release) only this cycle; the public bootstrap decision is the
owner's, recorded in `docs/security-review-v0.44.0.md`.

## Security review

`docs/security-review-v0.44.0.md` — threat-by-threat. No finding required a code change; the
framework adds no credential store, no network client, and no enforcement engine. Residual risks
recorded: the bounded-read marking is not runtime-enforced (Context Optimizer residual), the
`host` transport is not script-probeable, and the public npm bootstrap decision is deferred.

## 1.0 readiness verdict

- **Tool-definition contract (`agent-skills.tool-definition/v1`)** — ready to freeze at 1.0.
  Small, declarative, no per-tool branching, and the four fixtures plus one in-test synthetic
  tool prove a new provider needs only a file.
- **Capability vocabulary** — ready to freeze at 1.0, with the caveat that the 1.0-rc review
  should sanity-check family coverage for `data_pipeline.*`, `design.*`, and `security.*`, which
  have no validated reference tool in this release (only the design and intent are proven).
