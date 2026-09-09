# RC certification — v1.0.0-rc.1

Release-candidate certification evidence. Not a feature release: the work was to freeze the
contracts `agent-skills` will support after `1.0.0`, fix the blockers found while certifying
them, and record the proof. Everything below was produced by running the command named.

## What this candidate changed

- **`docs/one-point-oh.md`** (new) — the enumerated list of frozen contracts: CLI command and
  subcommand names, exit codes, `--json` shapes, the install layout and semantics, the
  release-provider interface, the npm-bootstrap lockstep rule, the skill names, and the
  Engineering Tool Capability Framework contract.
- **`SECURITY.md`** rewritten — describes how the project treats security rather than listing
  predetermined defects.
- **`ROADMAP.md`** brought current — v0.44.0 shipped, repointed at the RC and 1.0.
- **`docs/versioning.md`** leads with RC status and the frozen-contract pointer.
- **`check-updates --vendored`** and `docs/updates.md` corrected for the private repo — the
  GitHub releases API call must be authenticated; the message and CI example say so.
- **`agent-skills tools resolve`** prints the bounded-read / Context Optimizer instruction
  inline for a `bounded` capability — the minimal hardening for the v0.44.0 residual, with the
  framework still executing nothing.
- **`scripts/install.py`** — a `--dev` install resolves the release channel to `any` so a
  development install of a pre-release working tree is not refused. The provider channel gate is
  unchanged; `stable` machines are unaffected.

No command, flag, exit code, skill, tool class, or capability was renamed or renumbered.

## RC blocker found and fixed: installing a pre-release checkout

The first pre-release the project has cut. The local release provider correctly refuses to
install an `rc` version under the default `stable` channel — right for `npx … install`, wrong
for a development install of a working tree.

**Product fix — `scripts/install.py`.** `setup.init` and `agent-skills dev install` could not
install a pre-release working tree. `install.py` now resolves the effective channel: an explicit
`--channel` always wins; a `--dev` install falls back to `any`; every other install falls back
to `stable`, unchanged. A plain `install --provider local --source …` **still** refuses a
pre-release checkout without `--channel` — asserted by new `test-cli-install.sh` cases. The
release-provider channel gate is untouched and `stable` machines are unaffected.

**Test / CI fixes** — every path that installs the current tree without `--dev`:

| Where | Symptom | Fix |
| --- | --- | --- |
| `test-cli-install.sh` | `install_from_source` hit exit 2; git fixture found no stable tag | `--channel any` on the helper; `--channel rc` on the git-fixture publish |
| `test-global-install.sh` | the `as_run` helper + three direct local installs hit exit 2 | `--channel any` in `as_run` and the three sites |
| `test-release-readiness.sh` | section 3 failed via the above | `--channel any` on the five current-tree local installs |
| `.github/workflows/ci.yml` | local-install + npm-bootstrap-over-git steps hit exit 1/4 | `--channel any` on the two local installs; `--channel` derived on the git-fixture step |
| `test-private-source.sh` | would install `v0.44.0` (latest stable) not the RC | derive `rc` from a pre-release `VERSION` for install / update / check-updates |

`--channel any` is the existing "install exactly this tree" mechanism and is a no-op for a
stable version. The only product change is the `install.py` `--dev` channel resolution; the
release-provider channel gate itself is untouched, and `stable` machines are unaffected. After
the fix, all four suites pass at full count (`test-cli-install.sh` 107, `test-global-install.sh`
112).

## Contract freeze

| Contract | Frozen at | Source of truth |
| --- | --- | --- |
| CLI command + subcommand names | v1.0.0-rc.1 | `bin/agent-skills`, `docs/one-point-oh.md` |
| Release-lifecycle exit codes `0 2 3 4 5 6 7 10` | already frozen (`0.44.0`) | `lib/asrelease/exits.py`, `test-release-engine.py` |
| Subsystem exit contracts (`access` `tools` `context` `guard`) | v1.0.0-rc.1 | `docs/one-point-oh.md` |
| `--json` shapes for reporting commands | v1.0.0-rc.1 | fields may be added; never renamed/retyped; no secret value ever present |
| Install layout, `current` activation, transaction + rollback | v1.0.0-rc.1 | `docs/installation.md`, `docs/one-point-oh.md` |
| `stable` / `rc` channel semantics | already frozen | `docs/updates.md` |
| Release-provider 4-verb interface, `release.json` schema | v1.0.0-rc.1 | `docs/release-providers.md`, `lib/asrelease/providers/` |
| npm bootstrap: public thin, lockstep with runtime | v1.0.0-rc.1 | `docs/one-point-oh.md`, `scripts/audit-npm-package.sh` |
| 9 top-level + 2 nested skill names; Wamala routing model | v1.0.0-rc.1 | `docs/one-point-oh.md`, `docs/skill-boundaries.md` |
| 5 tool classes, 4 action classes, 18 capability families + names + action classes | v1.0.0-rc.1 | `lib/tools/`, `docs/engineering-tool-capabilities.md` |
| `agent-skills.tool-definition/v1` schema | v1.0.0-rc.1 | `lib/tools/registry.d/`, `scripts/tools.py` |

`data_pipeline.*`, `design.*`, and `security.*` ship with vocabulary and design only — no
validated reference tool. Freezing the names does not require one; adding a tool later is a
compatible change.

## Gate results

| Gate | Result |
| --- | --- |
| `python3 scripts/validate-repo.py` | pass — 61 warnings |
| `python3 scripts/run-evals.py` | pass — 48 files, 11 skills, 0 failures, 0 warnings |
| `bash scripts/test-tools.sh` | pass — 43 assertions |
| `bash scripts/test-access-resolution.sh` | pass — 100 assertions |
| `bash scripts/test-guard.sh` | pass — 108 assertions (54 rules / 31 floor; BYPASS + REDTEAM corpora) |
| `bash scripts/test-context-optimizer.sh` | pass — 105 checks (+ 5 mutation probes) |
| `bash scripts/test-cli-install.sh` | pass — 107 assertions |
| `bash scripts/test-global-install.sh` | pass — 112 assertions |
| `bash scripts/test-front-door-skill.sh` | pass — 63 assertions |
| `python3 scripts/test-release-engine.py` | pass — 21 checks (archive traversal, symlink escape, integrity, downgrade, hostile provider) |
| `bash scripts/audit-npm-package.sh` | pass — 14 files, no product content, version matches VERSION |
| `bash scripts/test-release-readiness.sh` | pass — 80/80 (final clean run, exit 0) |
| `bash scripts/test-private-source.sh` (against `v0.44.0`) | `PRIVATE_SOURCE_DISTRIBUTION_READY: YES` — 41 assertions |
| RC adversarial probes (`advprobe`) | pass — 17 assertions |
| RC upgrade/rollback cycle | pass — 16 assertions |
| RC offline smoke | pass — 13/13 local commands work network-dead (`context check` exit `10` is over-threshold, correct) |

`test-private-source.sh` against the `v1.0.0-rc.1` tag is run after the tag is pushed and appended
below. The npm bootstrap is built and audited (14 files, clean, version matches `VERSION`) but
**publishing is deferred to the maintainer** — no npm credentials were present on the
certification machine (`npm whoami` → 401; published `latest` is `0.43.0`). It publishes with
`npm publish --tag rc` from `npm/`, never `--tag latest`.

## Clean private install (`test-private-source.sh`, against v0.44.0)

```text
PRIVATE_REPOSITORY_ACCESS       PASS      HOST_REGISTRATION               PASS (8/8)
CLEAN_PRIVATE_INSTALL           PASS      EXECUTION_GUARD_COHERENCE       PASS
AGENT_SKILLS_DOCTOR             PASS      EXISTING_STATE_ISOLATION        PASS
AGENT_SKILLS_VERIFY             PASS      RELEASE_PROVIDER                git
PRIVATE_UPDATE_PATH             PASS

PRIVATE_AUTHENTICATED_INSTALL: PASS
PRIVATE_UPDATE: PASS
AUTHENTICATION_REQUIRED_BEHAVIOR: PASS   (exit 3, no hang, no partial install,
                                         no partial host registration, no token echoed)
PRIVATE_SOURCE_DISTRIBUTION_READY: YES
```

Installed from the remote through the packed npm bootstrap into a throwaway `HOME`; the real
installation on this machine was hashed before and after and is unchanged. Re-run against the
`v1.0.0-rc.1` tag post-push.

## Upgrade / rollback (`0.44.0 → 1.0.0-rc.1 → rollback → 0.44.0 → upgrade`)

16 assertions pass. Preserved across every hop: credential identities
(`work-jira` intact in `credentials.json`), repository bindings (`bindings.json` byte-identical),
the user's own host skill (`~/.claude/skills/my-own-skill`), and host registrations
(`wamala` re-registered). A staged payload missing a required runtime file fails self-test,
exits `6`, and leaves the previous release active — `verify` green afterward. **No mixed-version
install state was produced by any failure path.**

## Real host matrix (this machine)

Verifiable = `agent-skills verify` resolves every registered skill link to the canonical tree
(N/N). Guard level is from `lib/guard.registry`; `ENFORCED-capable` means a blocking hook exists
but is not registered on this machine (`guard doctor` reports `AVAILABLE`).

| Host | Discovered | Registered | Verifiable | Guard level | Smoke-tested |
| --- | --- | --- | --- | --- | --- |
| Claude Code | yes | yes | yes (N/N) | ENFORCED-capable | **yes** — this certification ran as a Claude Code agent |
| Agent Skills standard dir | yes | yes | yes (N/N) | n/a (convention dir) | filesystem only |
| Codex | yes | yes | yes (N/N) | ENFORCED-capable | UNPROVEN (not driven) |
| Cursor | yes | yes | yes (N/N) | ENFORCED-capable | UNPROVEN |
| GitHub Copilot / VS Code | yes | yes | yes (N/N) | PARTIAL | UNPROVEN |
| Kiro | yes | yes | yes (N/N) | ENFORCED-capable | UNPROVEN |
| Windsurf | yes | yes | yes (N/N) | ADVISORY | UNPROVEN |
| Continue | yes | yes | yes (N/N) | ADVISORY | UNPROVEN |
| JetBrains AI Assistant | n/a | manual | **no — not filesystem-verifiable** | ADVISORY | UNPROVEN |

`ENFORCED` is never claimed for a host where the hook is not registered. JetBrains registration
is an IDE-settings action and cannot be confirmed from disk — `verify` reports it `manual` and a
green `verify` is explicitly not evidence the entry exists. No verification was manufactured for
any host.

## Real-agent evaluation

- **Contract and structural layer — PROVEN for every host.** Every `SKILL.md` loads and carries
  its required sections; `run-evals.py` (48 files) and `test-front-door-skill.sh` (63) pass; the
  lifecycle wrappers, `tools resolve`, `context pack`, and `guard check-command` — the runtime
  the skills orchestrate — were executed directly throughout this certification.
- **Interactive execution — PROVEN for Claude Code only.** This certification pass ran as a
  Claude Code agent against the installed skills and runtime.
- **Autonomous multi-step Wamala dispatch chains — UNPROVEN.** There is no automated real-agent
  runner yet (`scripts/run-evals.py --invoke` is a roadmap item). Marked `UNPROVEN`, not `PASS`.

## Offline

After a successful install, with `http_proxy` / `https_proxy` / `ALL_PROXY` pointed at a dead
port: `doctor --brief`, `verify`, `context inspect|pack|check`, `guard check-command|rules`,
`tools status|doctor|resolve` (local tool), `project`, `access backend|profiles` all succeed.
Only `install`, `update`, `check-updates`, and external-service resolution require the network,
by design. `scripts/{doctor.sh,context.py,tools.py,knowledge.py,project-context.py,
project-memory.py}` contain no network client.

## Security

`docs/security-review-v1.0.0-rc.1.md` — threat by threat. No finding required a code change to
the installer, provider, Access Resolver, or Execution Guard. The RC adversarial probe set (17
assertions) plus the standing suites cover prompt injection across ticket/log/DB fixtures,
capability escalation (`READ ≠ WRITE ≠ ELEVATED ≠ DESTRUCTIVE`, `--allow-write` cannot raise a
class, `DESTRUCTIVE` never resolves), credential confusion, the Guard red-team corpus, supply
chain (archive traversal, symlink escape, integrity, downgrade, hostile provider, npm contents),
and a synthetic-secret leak sweep across every reporting command — no canary appeared anywhere.

Residuals (all documented, none blocking): the bounded-read marking is not runtime-*enforced* at
the read (the framework does not execute); the `host` transport is not script-probeable;
JetBrains is not filesystem-verifiable; interactive multi-agent execution is proven only for
Claude Code.

## RC-readiness verdict

- **Contracts ready to freeze at 1.0:** YES — enumerated in `docs/one-point-oh.md`, no rename or
  renumber required to get there.
- **P0 defects:** none.
- **P1 defects:** none. One P2-class residual (bounded-read not runtime-enforced) accepted and
  documented.
- **Ready for `v1.0.0`:** YES, after this RC has been exercised from the published `rc` channel.
