# Release certification — v1.5.0

Every number below was produced by running the command named, on this branch, before tagging. The
suites ran in a clean `git worktree` of the release commit (`346d063`), so untracked files in the
developer's checkout could not affect them. `c113753` (path display only) followed; the access suite
and eval runner were re-run on it with the same results.

## What this release changed

Access Discovery: `agent-skills access check` asks seven questions - route, launch, auth, mode,
target, intent, policy - for one operation on one target before any dependent work, and reports
each with its evidence strength (`verified`, `declared`, `inferred`). Company launcher scripts are
read, never run; organisation specifics are learned on the user's machine. Wamala runs the check
and, when it does not pass, a resolution dialogue instead of an improvised workaround. The design
record is `DISCOVERY-access.md` (deviations D1-D11); the guide is
[docs/access/README.md](../../docs/access/README.md); the security review is
[security-review-v1.5.0.md](../../docs/security-review-v1.5.0.md). Additive: exit code `11` is new,
nothing is renumbered, and no host configuration changes without an interactive yes.

## Verification

| Gate | Result | 1.4.0 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 84 warnings | pass, 94 warnings |
| `scripts/run-evals.py` (+ `--strict-sections`) | 62 files, 0 failures | 59 files, 0 failures |
| `scripts/test-access-discovery.py` (new) | 26 passed, 0 failed, offline | — |
| `scripts/eval-access-discovery.py` (new) | 10/10 scenarios correct | — |
| `scripts/test-cli-install.sh` | 150 passed, 0 failed | 150 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 78 assertions | 78 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 43 |
| `scripts/test-lifecycle-fs.sh` | pass | pass |
| `scripts/test-secret-boundary.sh` | pass | pass |
| `scripts/test-adaptive-execution.sh` | pass | pass |
| `scripts/test-knowledge.sh` | pass | pass |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-meeting.py` | 39 passed, 0 failed | 39 |
| `scripts/test-shared-knowledge.py` | 36 passed, 0 failed | 36 |
| `scripts/eval-shared-knowledge.py` | all targets met | all targets met |
| `scripts/test-private-source.sh` | version assertions fail by construction before the tag (see below) | run after tag |

`test-private-source.sh` installs from the remote, which still advertises `1.4.0` until `v1.5.0` is
tagged; its header documents that the three version assertions fail before the tag. Run it after
tagging. Every version-independent check in it passed.

**Warnings** fell from 94 to 84: `atlassian.net` joined the product-host allowlist (Atlassian
Cloud's public domain; docs and fixtures use invented sites under it), which cleared pre-existing
`example.atlassian.net` warnings too. No warning comes from a new file.

### Access evals (CLI half)

The evals in `evals/wamala-access-*.md` score what Wamala does with a check's output; that half needs
a model. `scripts/eval-access-discovery.py` runs the other half deterministically and records the
exact output Wamala would relay in [access-discovery/](access-discovery/).

| Scenario | Facts correct | What the check told Wamala |
| --- | --- | --- |
| incident: read-only launcher | yes | blocked at mode [inferred], exit 11, options confirm-inferred,write-profile,manual-handoff |
| write profile present | yes | available via atlassian-write; preview, then proceed on your go-ahead |
| no route | yes | blocked at route, exit 1, options setup-route,tell-tool,manual-handoff |
| no credential | yes | blocked at auth, exit 3, options store-token,manual-handoff |
| credential found, no route | yes | blocked at route; found keychain item offered only as setup input |
| target out of scope | yes | blocked at target: personal space excluded by CONFLUENCE_SPACES_FILTER |
| account lacks permission | yes | blocked at target [verified]: no update permission; ask the space owner |
| host divergence | yes | unknown at route: asks which host; scan warns about divergence |
| unknown wrapper confirmed by the user | yes | no route until the user says what it is; then available [declared] |
| mid-task 403 | yes | 403 -> target rung (permission / token scope), exit 11, no other route |

### Incident regression, before and after

On the `1.4.0` tree, the incident fixture (Codex, `~/.local/bin/acme-mcp-atlassian`, read-only
unless `ACME_ATL_RW=1`) produced `NO  mcp  no MCP configuration found` from doctor (it never read
`config.toml`) and `status: needs-setup ... check for a confluence tool` from `access resolve`. On
`1.5.0` it is blocked at `mode`, `inferred`, citing launcher lines 14-15, exit `11`, with the
keychain item reported as a locator, the browser never attempted, and a write profile using
`ACME_ATL_RW=1` offered ([01-incident.txt](access-discovery/01-incident.txt)). After the write
profile and the user's confirmation, the same check is `AVAILABLE` and policy asks for a preview
([02-write-profile.txt](access-discovery/02-write-profile.txt)).

### Mutation probes

Each weakened build was run against the named check; all five were caught.

| Probe | Property | Check |
| --- | --- | --- |
| M1 | a wrapper named after its upstream is not the upstream (substring match) | A1 fails |
| M2 | `setup` writes only after an interactive yes | A2 fails |
| M3 | `--probe` sends a credential only to the site its identity names | P2 fails |
| M4 | presence checks never ask the keychain for the secret (`-w`) | A1 fails |
| M5 | an explicit read-only setting outranks remembered knowledge | K1 fails |

### Rollback

Against state written by `1.5.0` (routes, grants, setup history, audit), the `1.4.0` tree's
`access profiles`, `resolve`, `forget --profile`, `backend`, `check-permissions` and
`doctor --json` all behave as before, with no traceback. Test X3 asserts `1.5.0` ignores a
future `local-routes` schema rather than half-reading it.
