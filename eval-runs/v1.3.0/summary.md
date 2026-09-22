# Release certification — v1.3.0

Every number below was produced by running the command named, on this branch, before tagging. The
full `scripts/test-release-readiness.sh` run was made in a clean `git worktree` of the release
commit, so untracked files in the developer's checkout could not affect it.

## What this release changed

Shared organisational knowledge: one reviewed, provenance-carrying knowledge source per
organisation, kept in a git repository the organisation already hosts, read and proposed to
through a single Knowledge Resolver. A merge is the only approval. The design was settled in
[DISCOVERY.md](../../docs/knowledge/DISCOVERY.md) before any code, and it records nine
deviations from the brief. The user guide is [docs/shared-knowledge.md](../../docs/shared-knowledge.md),
the admin guide [SETUP.md](../../docs/knowledge/SETUP.md), and the security review
[security-review-v1.3.0.md](../../docs/security-review-v1.3.0.md). Additive: with no source
configured, `knowledge read`, `facts`, and `doctor` produce byte-identical output to `1.2.0`
(test case 1), and no existing command, exit code, or skill changed behaviour.

## Verification

| Gate | Result | 1.2.0 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 94 warnings | pass, 92 warnings |
| `scripts/run-evals.py` | 59 files, 0 failures (once this file exists) | 59 files, 0 failures |
| `scripts/test-cli-install.sh` | 150 passed, 0 failed | 150 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 78 assertions | 78 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-lifecycle-fs.sh` | 62 passed, 0 failed | 62 |
| `scripts/test-secret-boundary.sh` | 46 passed, 0 failed | 46 |
| `scripts/test-adaptive-execution.sh` | 81 passed, 0 failed | 81 |
| `scripts/test-knowledge.sh` | 54 passed, 0 failed | 54 |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 43 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-meeting.py` | 22 passed, 0 failed, offline | 22 |
| `scripts/test-shared-knowledge.py` (new) | 36 passed, 0 failed, offline | — |
| `scripts/eval-shared-knowledge.py` (new) | all targets met | — |

Readiness: 88 of 92 checks passed in the clean-worktree run. The four failures had a single
cause: `eval-runs/v1.3.0/summary.md` (this file) did not exist yet. `run-evals.py`, its
`--strict-sections` run, and the front-door "eval corpus resolves every named skill" assertion
all require it. They were re-run after this file was written; see "After this file" below.

The warning count rose by two, both on one line of `scripts/knowledge_git.py`: the host
committer identities (`noreply@` addresses of GitHub and GitLab) that approval derivation must
name, read by the validator as email addresses. Every other warning is unchanged from `1.2.0`
(compared line by line against a `v1.2.0` worktree).

Two existing suites changed, and neither lost an assertion. `test-knowledge.sh` and
`test-secret-boundary.sh` copy runtime modules into a sandbox for their mutation probes, and now
copy every script, because `knowledge.py` reaches the Resolver.

### Upgrade and rollback

`test-release-readiness.sh` §6 installs `v1.2.0`, upgrades to this release, records a local fact
with it, rolls back, and runs `v1.2.0`'s own `verify` and `doctor`. All pass, and the
shared-knowledge state is byte-identical afterwards ("rolling back to v1.2.0 leaves
shared-knowledge state untouched"). Test case 16 adds the file-level half: `v1.2.0`'s
`knowledge.py` gives identical output before and after this release's first-run migration, and
no committed file is rewritten.

### Mutation probes

| Probe | Property removed | Weakened build |
| --- | --- | --- |
| shared: isolation | binding-pattern matching | client B's repository reads client A's fact |
| shared: personal | the personal-category rule | a `preference` reaches a proposal branch |
| shared: approval | the unreviewed downgrade | a CONFIRMED file pushed directly reads as CONFIRMED |
| shared: content scan | redaction + content findings | a hand-edited token reaches a proposal branch |
| shared: symlinks | symlink skipping | the client scans a fact planted as a link to a file outside the clone |

The option-injection case is not a mutation probe: it was observed failing against the pre-fix
commit, where a planted pointer file made `sources add` execute a program (see the security
review).

### Evals 18-19

`scripts/eval-shared-knowledge.py` — [scores](shared-knowledge/scores.md),
[results](shared-knowledge/results.json). Three simulated installations (https, ssh, and
no-`.git` https remotes) share one bare-repository source. **What is measured is what each agent
is given** by `knowledge read --brief` at task start, not how a model phrases its answer. The CLI
never calls a model.

| Eval | Property | Result | Target |
| --- | --- | --- | --- |
| 18 | before approval, the proposer sees it labelled `local, unshared` | yes | yes |
| 18 | before approval, the other two do not see it | 2/2 | 2/2 |
| 18 | after approval + sync, the same CONFIRMED shared top answer | 3/3 (100%) | 100% |
| 19 | superseded decision never presented as current | 18/18 (100%) | 100% |
| 19 | engineer B, who held the old decision locally, is told on sync | yes | yes |

## Security review

[docs/security-review-v1.3.0.md](../../docs/security-review-v1.3.0.md). Five findings, all fixed
before release, none ever published. Two came up during implementation: redaction erased commit
SHAs, and the history-rewrite purge was ineffective. Three came up in review: an option-shaped
pointer URL that **executed a program** through `git ls-remote` (the most serious), symlinked fact
files read from outside the clone, and recorded facts visible across repositories on one machine.
The three review findings each have a regression case that was run against the pre-fix commit
(`1bc7888`) and failed there: local isolation, pointer option, symlinks, and the symlink probe.

## Diff review

The release checklist asks for review by something that did not write the code. **That did not
happen for this release.** The diff review was done by the same session that wrote it, reading
the complete diff against `main` after the suites were green. It found the local-isolation, pointer-option, and symlink
defects above. The owner should read the diff (`git diff main...feature/shared-knowledge`), or have it
reviewed, before merging; this record does not claim an independent review.

## Telemetry review

`python3 scripts/telemetry.py report --all`, verbatim from the clean-worktree run. Telemetry is
local to a checkout, so a fresh worktree has none:

```text
{ "total_events": 0, "skills": {}, "unknown_events": {}, "performance": { "runs": 0, "median_minutes_to_first_artifact": null, "median_minutes_to_verified_result": null, "profiles": {}, "dispatches": 0, "context_loads": 0, "review_rounds": 0, "parallel_runs": 0, "no_output_runs": 0, "dispatches_per_run": null, "context_loads_per_run": null }}
```

No skill change this release traces to telemetry. The one skill change (`meeting-intelligence`
may suggest sharing) comes from the brief. `knowledge doctor` passes on a fresh base.

## Not done in this certification

- **CI and the private-source stage** did not run: this machine's active GitHub account cannot
  read the repository, so nothing was pushed. Both must be green on the release PR before
  tagging, as the checklist requires.
- **Publishing** (tag, GitHub release, npm) is left to the owner, with the commands recorded in
  the hand-off.
- **Host CLI adapters:** `gh` was exercised through a fake; `glab` only by reasoning.
