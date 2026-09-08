# Eval Run Summary — v0.38.0

Release-scoped verification for the front-door rename: `tech-lead` became `wamala`.

Run type: automated and structural. **No model was invoked** — the harness still has no agent
runner behind `--invoke` — so nothing here says anything about routing *quality*. What it does say
is that the routing *contract* survived the rename byte-for-byte, and that an existing v0.37.0
installation migrates without losing a user's own files. Read
[what this run does not prove](#what-this-run-does-not-prove) before treating any of it as evidence
that the skills behave better.

Reproduce the mechanical half with one command:

```bash
bash scripts/test-release-readiness.sh
```

## Structural verification

| Check | Command | Result |
| --- | --- | --- |
| Repository validation | `python3 scripts/validate-repo.py` | pass, 71 warnings |
| Compatibility shim | `python3 scripts/validate_skills.py` | pass |
| Eval corpus | `python3 scripts/run-evals.py` | 38 files, 10 skills, 0 failures, 0 warnings |
| Eval corpus, strict | `python3 scripts/run-evals.py --strict-sections` | 0 failures, 0 warnings |
| Version consistency | `VERSION` vs every `metadata.version` | all at `0.38.0` |
| Shell syntax | `bash -n` on `setup.init`, `lib/*.sh`, `bin/agent-skills`, `scripts/*.sh`, `hooks/*.sh` | pass |
| Python syntax | `ast.parse` on every `scripts/*.py` | pass |
| JSON templates | `json.load` on both hook templates and the link-check config | pass |
| Workflow | `yaml.safe_load` on `.github/workflows/ci.yml` | pass |
| Release readiness | `bash scripts/test-release-readiness.sh` | 76 checks, 0 failures |

The warning count is **unchanged at 71**, and the categories are identical to v0.37.0's. That is
the expected result for a rename: no new hostname, ticket key, or email-shaped string entered the
tree. Every warning is one v0.37.0 already carried and accounted for.

Release-readiness grew from 66 checks to 76: the nine new checks in section 6b, plus the
front-door suite joining section 3.

## Automated suites

| Suite | Assertions | Result |
| --- | --- | --- |
| `scripts/test-global-install.sh` | 119 | pass |
| `scripts/test-access-resolution.sh` | 100 | pass |
| `scripts/test-front-door-skill.sh` | 50 | pass |
| `scripts/test-setup-update-preserves-credentials.sh` | 10 exact `.env` lines | pass |
| `scripts/test-release-readiness.sh` | 76 | pass |

`test-global-install.sh` grew from 103 to 119. `test-front-door-skill.sh` is new.

## The routing contract, compared rather than asserted

The risk in a rename is that the identity edit quietly takes the architecture with it. Prose
checks cannot see that; a diff can. `test-front-door-skill.sh` extracts the routing rows from
`SKILL.md` and `references/routing-table.md`, substitutes the identity, and compares them against
`git show v0.37.0:skills/tech-lead/...`.

| Comparison | Result |
| --- | --- |
| `SKILL.md` routing rows vs `v0.37.0` | identical |
| `references/routing-table.md` rows vs `v0.37.0` | identical |
| `SKILL.md` `##` section structure vs `v0.37.0` | identical |

Fourteen behavioural clauses are asserted individually rather than as one blob, so a partial
regression names itself:

| Clause | Asserted |
| --- | --- |
| Requirement-understanding gate runs before routing | yes |
| The gate's verdict outranks the classification | yes |
| Dispatch opens a fresh empty-context agent, never a nested invocation | yes |
| Steps are verified from artifacts, never from a chat summary | yes |
| A missing artifact is retried exactly once | yes |
| The depth cap of two is preserved | yes |
| One owner per dispatched step | yes |
| A hard cap of six dispatches bounds a run | yes |
| The destructive-action safety floor is inherited | yes |
| Routing is not a laundering step for a forbidden request | yes |
| Direct specialist invocation stays first-class | yes |
| An existing plan is handed to `delivery-runner` | yes |
| Routing is capability-aware | yes |
| Stopping conditions are enumerated | yes |

When `v0.37.0` is not fetched — a shallow CI clone — the three comparison cases report as
**skipped**, not as passed. A comparison that silently succeeds because it had nothing to compare
against is worse than no comparison.

## Identity

| Property | Result |
| --- | --- |
| `skills/wamala/SKILL.md` exists | pass |
| Declared `name` is exactly `wamala` | pass |
| Heading is `# Wamala` | pass |
| Directory name matches the declared name | pass |
| `skills/tech-lead/` does not exist | pass |
| No `SKILL.md` anywhere declares `name: tech-lead` | pass |
| Eight top-level skills are registerable | pass |
| Nine specialists keep their role-based names | pass (9 cases) |
| No active doc, skill, example, or eval advertises the old name | pass |
| The eval corpus resolves every named skill against `skills/` on disk | pass |

The last two are the ones that would have caught a half-finished rename. The eval harness fails
hard on a `## Skill Under Test` naming a directory that does not exist, so `evals/wamala-routing.md`
and `evals/legacy-workspace-migration.md` are checked by construction rather than by reading.

## Migration from a v0.37.0 global installation

Two independent exercises, because they fail differently.

**In `test-global-install.sh` (16 assertions, runs in CI).** A v0.37.0-shaped source tree is
built, installed into a throwaway `HOME` whose path contains a space, and then upgraded in place —
which is what `agent-skills update` does to a clone.

| Case | Result |
| --- | --- |
| Pre-upgrade: `tech-lead` registered, `wamala` absent | pass |
| Upgrade registers `wamala`, and it resolves to a `SKILL.md` | pass |
| Upgrade removes the agent-skills-owned `tech-lead` registration | pass |
| Upgrade names the registration it removed in its output | pass |
| A user's own `tech-lead` **directory** survives, unconverted | pass |
| A user's own `tech-lead` **symlink** into their tree survives and still resolves | pass |
| Re-running the upgrade adds nothing | pass |
| Exactly one `wamala` registration after two upgrades | pass |
| A second run has nothing left to prune, and says nothing | pass |
| `verify` passes after the migration | pass |
| `verify` reports an unmigrated stale registration | pass |
| `install` clears the registration `verify` complained about | pass |

**In `test-release-readiness.sh` section 6b (9 checks, local only).** The same upgrade against a
real `git worktree` of the `v0.37.0` tag, so the baseline is the shipped release rather than a
reconstruction.

| Case | Result |
| --- | --- |
| `v0.37.0` really did ship the front door as `tech-lead` | pass |
| `v0.37.0` registered `tech-lead` globally | pass |
| The upgrade registered `wamala`, resolving to a `SKILL.md` | pass |
| The agent-skills-owned `tech-lead` registration was removed | pass |
| The user's own `tech-lead` skill survived | pass |
| `verify` passes after the upgrade | pass |
| A second run leaves exactly one `wamala` registration | pass |
| The installed CLI resolves the deprecated name with a notice | pass |

### Each migration assertion was shown failing

Per the release checklist's rule about probes that assert against a mechanism the code does not
use: `as_orphan_registrations` was stubbed to return nothing, the suite re-run, and the fix
restored. Four assertions failed with the mechanism disabled and pass with it:

```text
FAIL upgrade removes our own tech-lead registration
FAIL upgrade reports which stale registration it removed
FAIL verify reports a stale registration for a renamed skill
FAIL install clears the stale registration verify complained about
```

The first pass of that experiment found a real weakness in the tests themselves rather than in the
code: `test -e` follows symlinks, so it called a **dangling** `tech-lead` link absent, and two
absence assertions passed against the stub. That is exactly the state a botched rename leaves
behind. The assertions now use a `no_entry` helper that checks `! -e` **and** `! -L`.

## The deprecated alias

`tech-lead` is recognised by `start-task` and `finish-task` for `--skill`, and nowhere else.

| Case | Result |
| --- | --- |
| `start-task --skill tech-lead` prints `tech-lead was renamed to wamala; using wamala` | pass |
| The blackboard records `wamala` | pass |
| The blackboard does **not** contain `tech-lead` | pass |
| `finish-task --skill tech-lead` prints the same notice | pass |
| Telemetry attributes the run to `wamala` | pass |
| An unknown skill name passes through unchanged | pass |
| The alias has a documented removal release (`v0.41.0`) | pass |

The notice goes to stderr, so a caller capturing stdout does not get it mixed into a value. The
last two cases are the ones that keep this bounded: the table cannot swallow a typo, and it cannot
live forever without someone noticing.

## Telemetry review

Verbatim, from `python3 scripts/telemetry.py report --all`:

```json
{
  "total_events": 2,
  "skills": {
    "software-engineer": {
      "completed": 1
    },
    "manual-tester": {
      "completed": 1
    }
  },
  "unknown_events": {}
}
```

Unchanged from v0.37.0, and still not evidence of anything. Two events from this maintainer's own
machine is a smoke test of the counter, not a usage signal. No skill change this release was driven
by telemetry, and saying so is the point of recording it: an unread counter presented as evidence
is worse than no counter.

`wamala` shows zero `invoked` events, as `tech-lead` did before it. That is the expected state for
a skill whose lifecycle wrappers only run when someone invokes it on a real task, and it is the
first thing to re-check once the rename has been in use for a release.

## What this run does not prove

- **No model was invoked.** Nothing here measures whether `wamala` classifies a real request
  correctly, picks the right owner, or writes a good handoff. `evals/wamala-routing.md` is a
  scenario for a human or an agent to run; the harness only checks that the file is structurally
  intact and names a skill that exists.
- **Routing quality is unmeasured**, exactly as it was in v0.36.0 and v0.37.0. What changed this
  release is narrower and worth stating precisely: the routing contract is now proven *unchanged*,
  which is a claim about the rename, not about the router.
- **No multi-agent dispatch was executed.** The fresh-context dispatch path is asserted from the
  skill's own text, not observed.
- **No IDE was launched.** Host registration is verified at the filesystem level: the symlink
  exists, is ours, and resolves into the canonical tree. Whether a given host's skill panel then
  lists `wamala` is the host's behaviour, and this run does not claim it.
- **The alias is tested through the lifecycle scripts, not through a host.** A host that discovered
  `tech-lead` before the upgrade will simply stop offering it; the alias does not and cannot make
  a host resolve the old name.

## Follow-ups

1. Invoke `wamala` on real requests and record misroutes as lessons in the repo knowledge base.
   The rename does not change this being the outstanding gap.
2. Remove the `tech-lead` alias in `v0.41.0`, per the deprecations step in the release checklist.
3. Once an agent runner exists behind `--invoke`, `evals/wamala-routing.md`'s four requests are the
   cheapest first target: each has a single correct owner and a documented wrong one.
