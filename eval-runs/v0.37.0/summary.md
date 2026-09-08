# Eval Run Summary — v0.37.0

Release-scoped verification for the machine-global install and the generic access resolver.

Run type: automated and structural, plus maintainer-authored adversarial probes. No model was
invoked, because the harness still has no agent runner behind `--invoke`. Read
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
| Version consistency | `VERSION` vs every `metadata.version` | all at `0.37.0` |
| Shell syntax | `bash -n` on `setup.init`, `lib/*.sh`, `bin/agent-skills`, `scripts/*.sh`, `hooks/*.sh` | pass |
| Python syntax | `ast.parse` on every `scripts/*.py` | pass |
| JSON templates | `json.load` on both hook templates and the link-check config | pass |
| Workflow | `yaml.safe_load` on `.github/workflows/ci.yml` | pass |
| Release readiness | `bash scripts/test-release-readiness.sh` | 59 checks, 0 failures |

The warning count rose from 61 to 71. Every one of the ten is an existing category, not a new one:

- `example.atlassian.net` in the new access-resolution docs and evals. It is a placeholder, but
  `atlassian.net` is not in the validator's `ALLOWED_HOSTS`, and v0.36.0 already carried the same
  warnings from `docs/auth-discovery.md`.
- Quote-terminated hosts such as `attacker.example.com"` and `sandbox.example.atlassian.net"`. The
  validator's URL regex captures the trailing quote, so the `.example.com` suffix test misses. A
  false positive of the check, not of the content.
- Two placeholder emails in new prose, on `example.*` subdomains.

No new warning category appeared, and no warning names real infrastructure.

## Automated suites

| Suite | Assertions | Result |
| --- | --- | --- |
| `scripts/test-global-install.sh` | 103 | pass |
| `scripts/test-access-resolution.sh` | 100 | pass |
| `scripts/test-setup-update-preserves-credentials.sh` | 10 exact `.env` lines | pass |
| `scripts/test-release-readiness.sh` | 66 | pass |

Both new suites grew after a pre-merge review of the release diff: `test-global-install.sh` from 78
to 103, `test-access-resolution.sh` from 77 to 100. See
[what the pre-merge review changed](#what-the-pre-merge-review-changed) — the added assertions cover
defects the original suites could not have caught, and were each confirmed to fail against the
pre-fix code.

### Global installation

Every case runs against a throwaway `HOME` whose path contains a space, so a missed quote fails in
the suite rather than on a user's machine.

| Case | Expected | Result |
| --- | --- | --- |
| Clean first install | exits 0, manifest written, canonical trees linked | pass |
| No credential requested | nothing credential-shaped in the output | pass |
| No credential state created | no `credentials.json`, no `.env`, no `.skills` | pass |
| Rerun | no second registration, manifest rewritten not appended | pass |
| Path with spaces | skills resolve through it | pass |
| Host present with an existing skills dir | registered | pass |
| Host present with only a config dir | registered | pass |
| Host absent | skipped and reported, directory not created | pass |
| Unrelated user skill alongside ours | survives, still a real directory | pass |
| Name collision with an unrelated real directory | left alone, content untouched, reported | pass |
| Realpath identity across four host directories | `present=4 distinct=1` | pass |
| `--all-hosts` | registers an undetected host | pass |
| Nested support skill | reachable through its parent, not registered twice | pass |
| Broken canonical symlink | `verify` fails; reinstall repairs it | pass |
| Missing host registration | `verify` says to rerun install | pass |
| Version drift | detected, and cleared by reinstall | pass |
| Ownership after the source tree is deleted | `uninstall` still removes its 8 registrations | pass |
| Runtime from an unrelated repository | resolves via PATH | pass |
| Runtime several directories deep | resolves | pass |
| No PATH at all | the `AGENT_SKILLS_HOME` launcher still works | pass |
| Zero-config repository | valid context, stack inferred, build flagged for confirmation, exit 0 | pass |
| Committed config outranks inference | `build` and `mode` honoured | pass |
| Context from a nested directory | resolves from the repository root | pass |
| Legacy `.skills` and lock file | reported obsolete; `.env` reported still read | pass |
| `migrate --remove-obsolete` | removes the symlink and lock, never `.env` | pass |
| Inherited `WORKSPACE_ROOT` with a `.env` | selects the legacy model, creates no global install | pass |
| Uninstall | removes ours, keeps an unrelated user skill, leaves the clone alone | pass |
| In-repo mode | vendored skills load with no global install | pass |

### Access resolution

The canary is a fixed string searched for in every output. If it ever appears, a secret leaked.

| Case | Expected | Result |
| --- | --- | --- |
| Backend report | names the active store; `--json` valid | pass |
| File fallback | reported as a warning with the `0600` mode stated, never silently | pass |
| Nothing configured | `needs-setup`, missing fields named, exit 1 | pass |
| Guidance | points at hidden input, never asks for the value | pass |
| Caller-supplied resource | satisfies the `host` field | pass |
| Arbitrary custom service | resolves with its own field names | pass |
| Secret in output | absent from `resolve`, `--json`, `profiles`, `profiles --json` | pass |
| Secret file permissions | file `0600`, directory `0700`, outside every repository | pass |
| Metadata | contains no secret value | pass |
| `check-permissions` | passes when correct, fails on a world-readable file | pass |
| Process environment | outranks a stored identity; both spellings honoured | pass |
| One compatible identity | used without a prompt, reason reported | pass |
| Two repositories, one identity | second repo resolves, credential not duplicated | pass |
| Two accounts for one service | refuses to guess, names both candidates | pass |
| Binding | resolves the ambiguity; registry holds no secret | pass |
| Different host, same service | an identity for another host is not offered | pass |
| Strict binding | lone identity not auto-used; resolves once bound | pass |
| Committed `.agent-skills.local.yml` | refused as tracked, no identity chosen, no secret reached | pass |
| Untracked `.agent-skills.local.yml` | honoured as the supported override | pass |
| Committed `.agent-skills.yml` `credentials:` block | never read | pass |
| Hostile names | path traversal, separator, and command substitution all rejected | pass |
| Case-folding | `Mixed-Case` becomes one lowercase identity | pass |
| Secret passed as a plain `--field` | refused | pass |
| Unavailable secure store | reported, never downgraded; request left unresolved | pass |
| Unknown forced backend | rejected | pass |
| No TTY | refuses to read a secret and explains why | pass |
| Legacy `.env` | still resolves; source reported; value not echoed | pass |
| Unresolved `${VAR}` placeholder | treated as incomplete config, never as a value | pass |
| `import-legacy` | read-only without `--apply`; never displays or deletes | pass |
| `forget` | deletes the secret and clears bindings, prints no value | pass |
| Authenticated CLI present | resolves with no stored secret, states nothing was stored | pass |

## Upgrade from v0.36.0

Performed against a real `git worktree` of the `v0.36.0` tag, installed the old way first.

| Case | Expected | Result |
| --- | --- | --- |
| v0.36.0 install | produces `.env` and the `.skills` symlink | pass |
| Upgrade install | global install created, exits 0 | pass |
| Legacy `.env` | not deleted | pass |
| Legacy `.skills` | left alone by the install itself | pass |
| `migrate` | reports `.skills` obsolete and `.env` still read | pass |
| `migrate --remove-obsolete` | removes `.skills`, keeps `.env` | pass |
| A credential in the legacy `.env` | still resolves after the upgrade | pass |
| That credential's value | not echoed | pass |
| `--update` in a legacy workspace | preserves all ten credential lines verbatim | pass |

An upgrade from `v0.35.0` was also exercised and passed the same assertions.

## Adversarial probes

Maintainer-authored, run for [the security review](../../docs/security-review-v0.37.0.md).

| Probe | Expected | Result |
| --- | --- | --- |
| Attacker-planted symlink at a name we register | left pointing where it was, victim file survives, reported | pass |
| Unmanaged symlink at a canonical install path | install refuses with exit 2, path untouched | pass |
| Eight hostile profile and service names | all rejected, no injection artifact created | pass |
| Canary across seven read commands and the metadata file | absent from all | pass |
| `doctor` across its three new probes | no secret-shaped string | pass |
| `AGENT_SKILLS_SOURCE` pointing at a non-source tree | ignored, real tree used | pass |
| Instruction-shaped committed knowledge lesson | rejected by `knowledge doctor` | pass |

One finding was raised: `UPPER` was accepted as a profile name, because names are case-folded before
validation. Reviewed and kept as intended behaviour; the documentation was wrong to claim no
transformation at all, and the behaviour is now pinned by a test rather than left to drift.

## Host support: what was actually verified

The task this release answers is "which agents can see the skills", so the basis for each claim
matters more than the checkmark.

| Host | Basis |
| --- | --- |
| Claude Code | structurally validated from official documentation, and integration tested — registration created, `verify` confirms realpath identity |
| Agent Skills standard dir | structurally validated from Codex and Copilot documentation, integration tested |
| Codex | structurally validated from official documentation, integration tested |
| Cursor | structurally validated from official documentation, integration tested |
| GitHub Copilot | structurally validated from VS Code and GitHub documentation, integration tested |
| Kiro | structurally validated from official documentation, integration tested |
| JetBrains AI Assistant | structurally validated from official documentation only. Requires one settings action that cannot safely be automated, and is reported as such rather than claimed |
| Windsurf | structurally validated, integration tested for registration. Host discovery is less thoroughly documented than the others |
| Continue | same as Windsurf |

"Integration tested" here means the filesystem contract was exercised in a sandboxed `HOME`:
the registration is created, it resolves to the canonical tree, an unrelated skill survives, and
`verify` agrees. **No host application was launched.** Nothing below was manually verified inside a
running IDE, so a host that changed its discovery behaviour in a recent build would not be caught
here — `agent-skills verify` on the user's own machine is the check that matters.

## Telemetry review

Required by the [release checklist](../../docs/release-checklist.md#telemetry-review). The report,
verbatim:

```json
{
  "total_events": 2,
  "skills": {
    "software-engineer": { "completed": 1 },
    "manual-tester": { "completed": 1 }
  },
  "unknown_events": {}
}
```

**Two events, identical to the v0.36.0 baseline of two.** The counters did not move between releases:
still no `invoked` events, no `loop_round`, no `stopped`, and eight of the ten skills absent
entirely.

**No skill change in this release traces to a telemetry finding, because there was nothing to find.**
Recorded rather than glossed. An unread counter is worse than no counter, because it looks like
evidence.

The baseline for the next release remains **2 events**. The question it answers is unchanged and
still open: whether the lifecycle wrappers are actually running in real use. This release makes that
more likely to become answerable, because the wrappers are now invoked through one command that
resolves from anywhere rather than a relative path that only worked in one layout — but that is a
hypothesis, not a measurement.

`agent-skills knowledge doctor` passes on a fresh knowledge base and still rejects an
instruction-shaped entry.

## What the pre-merge review changed

The release was validated green — every suite passing, the checklist run end to end — and then
reviewed as a diff before merge. That review returned **25 issues, 5 reproduced live**, including two
against the criterion this release calls critical. Recording it here because "all suites passed" was
true at the time and was not sufficient.

Five of these reproduced live in sandboxes; the rest were confirmed by reading. Each accepted finding
has a regression test, and the security ones were confirmed to fail against the pre-fix code.

**Reproduced live.**

1. **A repository file routed a machine credential.** A repo `.env` supplied `host` while an
   auto-selected identity supplied `token`, and the result was `status: resolved` — a corporate
   credential aimed at an attacker-chosen endpoint, without the repository ever naming an identity.
   Blocking *selection* was not enough, because resolution fills fields independently.
   *Fix:* tracked-check every credential source inside the repository, and refuse an identity whose
   recorded `resource` disagrees with a repo-supplied host, reporting a `security:` finding.
   *Pinned by* `test-access-resolution.sh`.
2. **The tracked-file check failed open.** Any `git` failure — no binary, dubious ownership, a broken
   `GIT_DIR` — read as "untracked, therefore trusted", so with `git` off `PATH` a *committed*
   `.agent-skills.local.yml` selected the profile.
   *Fix:* a tri-state `tracked` / `untracked` / `unknown`, where `unknown` refuses the file and says
   why. *Pinned by* `test-access-resolution.sh`.
3. **`agent-skills install --hosts` looped forever, printing nothing.** `--hosts`, `--source`, and
   `--branch` used `shift 2`, which shifts nothing when the flag is the last argument.
   *Fix:* an explicit value guard on every such flag, in both the CLI and `setup.init`.
   *Pinned by* `test-global-install.sh`, using a timeout so a hang is distinguishable from a refusal.
4. **A foreign *dangling* symlink was adopted, then deleted by `uninstall`** — the user lost both
   their link and ours. The rationale had been that a broken link holds no data; the link is the data.
   *Fix:* ownership by location (inside the install root) or by literal target; a dangling link
   satisfying neither is a conflict to preserve. *Pinned by* `test-global-install.sh`.
5. **A legacy workspace was silently migrated.** The workspace was detected only under `--verify`, so
   the same machine answered "legacy" for `--verify` and "global" for the bare run and for
   `--update` — the command v0.36 documented for updating.
   *Fix:* legacy detection applies to every command, migrating is opt-in via `--global`, and the
   global path no longer sources a legacy `.env` that could redirect `AGENT_SKILLS_HOME` or `PATH`.
   *Pinned by* `test-global-install.sh`.

**Found by reading, fixed.**

6. **Two install failures reported success.** A missing `lib/hosts.registry` or a missing `python3`
   registered nothing, wrote no manifest, printed "installed globally", and exited 0. Both ran inside
   `$(...)`, which discards the exit status of what it contains.
   *Fix:* both checked as prerequisites before anything is written; the manifest verified before the
   banner. *Pinned by* `test-global-install.sh`.
7. **`verify` could never go green after a name collision.** Install preserves a user's own same-named
   skill on purpose; verify counted that as a broken registration and exited 1.
   *Fix:* distinguish "ours but broken" from "yours, left alone". *Pinned by*
   `test-global-install.sh`.
8. **A capability resolution reported no fields.** `status: resolved` came back with `fields_present`
   and `fields_missing` both empty, and the probes ignored `--resource`, so a `gh` session for
   github.com resolved a GitHub Enterprise host.
   *Fix:* populate the fields from the request, and require a probe to be able to serve the named
   resource before it short-circuits. *Pinned by* `test-access-resolution.sh`.
9. **Task scratch dirtied every repository.** `.cache/` was created at the repo root with nothing
   ignoring it, so `git add -A` would commit ticket notes and investigation state.
   *Fix:* `.git/info/exclude` on first write — local to the clone, never committed, and no edit to a
   tracked `.gitignore`. *Pinned by* `test-global-install.sh`.
10. **A profile split across two stores lost one.** `backend` was a scalar overwritten by the most
    recent write, leaving the earlier secret unreadable *and* undeletable.
    *Fix:* storage recorded per secret field; the scalar remains only so older profiles resolve.
    *Pinned by* `test-access-resolution.sh`.
11. **`import-legacy --apply` overwrote an existing identity** and read in-repo files with no tracked
    check. *Fix:* the tracked check applies, and a clash refuses and points at `--force`.
    *Pinned by* `test-access-resolution.sh`.
12. **`migrate --remove-obsolete` deleted `.skills` on filename alone** — the one deletion in the
    release that did not verify the target was ours. *Fix:* ownership checked first, against both the
    install root and the source tree.
13. **A committed `project.build` was the one value marked as needing no confirmation**, despite being
    an executable command editable by anyone who can open a pull request.
    *Fix:* committed `build` and `format` are listed under `needs_confirmation`; descriptive fields
    are unchanged.
14. **A bare `./setup.init --yes` erased the credentials in its own managed block.** Found while
    fixing defect 5: once a bare run correctly stays on the legacy path, it runs the legacy writer,
    which emits empty strings for any service whose mode resolves to "no". `--update` had been immune
    because it already opted populated services back in. This is pre-v0.37.0 behaviour that the
    routing fix exposed rather than introduced — previously the bare run migrated to global and never
    touched `.env`, so the data loss was hidden behind a different bug.
    *Fix:* the opt-in logic is shared between both paths and honours an explicit `--no-jira`.
    *Pinned by* `test-release-readiness.sh`, whose fixture now seeds the credential **inside** the
    managed block. Appending it after the block — as the fixture did before — tests a shape
    `setup.init` deliberately normalises away, so that assertion had been passing for the wrong reason.

Documentation corrected in the same pass: the resolution order is described as per-field rather than
"first step that satisfies every required field wins" (the mismatch the routing hole depended on); a
tracked local override is documented as ignored **whole**, not just its `credentials:` block; rule 5
of skill-source resolution is given an internal order so the claim that the order is total holds; the
consequence of rule 3 — a vendored copy silently outranking the global install — is now stated; and
the claim that `access resolve` is "the single mechanism every skill uses" is scoped to what is true,
with the tracker migration recorded as follow-up 7.

Two residual risks were accepted rather than fixed, with the reasoning recorded at the call site and
in the review: the macOS Keychain write passes the secret in argv (piping it instead makes `security`
store an empty secret — measured), and lone-compatible-identity auto-selection stays on by default.

## What this run does not prove

Stated plainly, because the tables above are easy to over-read.

- **No model was invoked.** `run-evals.py` verifies that eval files are well-formed and reference
  real skills. It does not run a skill and grade the output. The four new evals are specifications
  of correct behaviour, not measurements of it.
- **No IDE was launched.** Host support is a filesystem contract verified in a sandbox plus a
  reading of current official documentation. Whether Cursor, Kiro, or Copilot *lists* these skills
  in a real session on a real machine was not observed. Kiro's symlink and recursion behaviour is
  not documented at all; it is inferred from the standard and from the directory contract.
- **JetBrains is documentation only.** The one settings action is described, not performed.
- **Linux Secret Service is untested on real hardware.** `secret-tool` is not installed on the
  review machine. The macOS Keychain path and the file fallback were exercised; the Secret Service
  backend is reviewed by reading it and by its own availability probe.
- **Windows is not assessed.** WSL and Git Bash remain the supported route.
- **Agent judgement is unmeasured.** Whether an agent reaches for the shared resolver instead of
  inventing discovery, keeps working around a blocked service, refuses to reason past a control that
  is working, or declines to echo a value it legitimately obtained — all of that is what the evals
  describe and what nothing here checks.
- **The security review is not a penetration test.** It is targeted probes against the threats named
  in the release scope, written by the same person who wrote the code.
- **Races are reasoned about, not measured.** A local attacker who can write into the user's own host
  skills directory at exactly the wrong moment is discussed in the review, not tested.
- **Long-run behaviour is untested by construction.** Whether one global install stays healthy across
  months of clone moves, host updates, and OS upgrades is the actual claim, and it needs months.
- **A green suite was not enough, and this one may not be either.** Every suite passed before the
  pre-merge review found five live defects, two of them in the criterion this release calls critical.
  The suites now cover those specific defects. They do not establish that no similar class remains,
  and the honest reading of the table above is "these cases pass", not "this code is correct".

## Follow-ups

1. Put an agent runner behind `run-evals.py --invoke`. The evals carrying
   `## Required Output Fields` — now including three of the four added this release — remain the
   cheapest first grader, because field presence is checkable without a model judging prose.
2. Manually verify each host inside a running IDE and record the result, converting
   "structurally validated" into "manually verified" per row. This is the largest honesty gap in the
   table above.
3. Re-run the telemetry report next release and compare against the baseline of 2 events. A flat
   count after real use means the wrappers are being skipped, which is exactly the question the
   counters exist to answer.
4. Exercise the access resolver against a real Linux Secret Service session.
5. Decide whether `AGENT_SKILLS_STRICT_BINDING` should become the default once there is evidence
   about how many users hold several identities for one service.
6. Revisit the nine-host registry each release. Agent Skills discovery paths are still moving, and a
   stale row is worse than an absent one because it reads as verified.
7. Move the tracker preflight in `scripts/doctor.sh` and the `locate-config` guidance in the skills
   onto `agent-skills access resolve`. The resolver is the general mechanism and is reachable through
   `docs/auth-discovery.md`, but Jira and Confluence still go through `auth-preflight.py`, so the
   release ships two paths to the same answer. Deferred rather than rushed: it touches nine `SKILL.md`
   files and their evals, which is not last-mile work.
8. Teach capability probes to report the host they actually serve, instead of falling back to a static
   table. `gh auth status` and `jira` both know their configured host; parsing that would turn
   "cannot confirm it serves this resource" into a real answer for Enterprise and multi-tenant setups.
9. Run a diff-level review *before* declaring a release green, not after. This release passed every
   gate and then failed a reading of its own diff. The review skill exists; the checklist did not
   require it.
