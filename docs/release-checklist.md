# Release Checklist

Use this before tagging a release.

## Validation

One command runs the mechanical half of this list, so the evidence recorded in
`eval-runs/<release>/summary.md` is reproducible rather than asserted:

```bash
bash scripts/test-release-readiness.sh
```

It covers the structural validators, syntax across every shipped artifact, all ten shell test suites plus the Python suites,
the CLI surface, a clean-`HOME` install with drift and uninstall, an upgrade from the previous
release tag in both the legacy-workspace and global-install shapes, cloud/in-repo mode, the
public-safety sweep, README and link integrity, the telemetry report, and version consistency.
Section 3 runs all ten shell test suites, the release engine, and
[`test-meeting.py`](../scripts/test-meeting.py) (added in `1.2.0`), including
[`test-knowledge.sh`](../scripts/test-knowledge.sh) (added in `1.0.0`: observation integrity,
contradiction and decay, budget accounting, lock serialisation, `dod-check`, the idempotent
stop-hook fallback, and promotion provenance, with three mutation probes),
[`test-context-optimizer.sh`](../scripts/test-context-optimizer.sh) and its five mutation probes,
[`test-guard.sh`](../scripts/test-guard.sh) with its adversarial corpus, false-positive
corpus, host-adapter checks, and seven mutation probes, and the three added in `1.0.0-rc.2`:
[`test-lifecycle-fs.sh`](../scripts/test-lifecycle-fs.sh),
[`test-secret-boundary.sh`](../scripts/test-secret-boundary.sh), and
[`test-adaptive-execution.sh`](../scripts/test-adaptive-execution.sh), carrying nine further
mutation probes between them.
Everything is sandboxed under `mktemp`; it never touches your real home directory, host skill
directories, or credential store. It is not in CI because it builds a
worktree of the previous tag and performs several full installs.

- [ ] Run `bash scripts/test-release-readiness.sh` and confirm it exits `0`.
- [ ] Run `python3 scripts/validate-repo.py` from the repository root.
- [ ] If this release renames or removes a skill, confirm
      `bash scripts/test-front-door-skill.sh` passes with the routing-equivalence cases running
      rather than skipped — they need the previous release tag fetched.
- [ ] Confirm validator line-readability checks pass for Markdown, YAML, and Python source.
- [ ] Confirm validator file-density and minification checks pass for Markdown, YAML, and Python.
- [ ] Inspect warnings and decide whether they are acceptable. Compare the count against the
      previous release and account for any increase by category.
- [ ] Confirm GitHub Actions validation passes on the release PR or branch. **Never publish a
      release while CI is failing.**

## Execution Guard

Required whenever this release changes `scripts/guard*.py`, `lib/guard.registry`, the host
adapters, or any rule the guard enforces.

- [ ] Run `bash scripts/test-guard.sh` and confirm it exits `0`. Record the pass count and the
      corpus sizes in `eval-runs/<release>/summary.md`.
- [ ] Confirm every mutation probe reports that the weakened build gives the weaker answer. A
      probe that passes without the property removed proves nothing; see the probe-discipline
      note below.
- [ ] Run `bash scripts/test-guard.sh --bench-only` and record p50/p95/p99. This hook runs before
      every shell command; a regression here is a correctness problem, not a nicety.
- [ ] Account for any change in the false-positive corpus. A benign case moving from `ALLOW` to
      `ASK` is a regression against usability, and an unusable guard gets switched off.
- [ ] Confirm no rule was added without a safe alternative — `guard rules --format json` carries
      the field and the suite asserts it.
- [ ] Re-verify the host contracts against each host's **current** published documentation.
      Hook schemas change. Never leave a host at `enforced` in `lib/guard.registry` on the
      strength of an older reading.
- [ ] Confirm `agent-skills guard install` still preserves unrelated hooks, is idempotent, and
      that `uninstall` removes only agent-skills-owned entries. The suite covers all three; read
      the assertions rather than trusting the summary line.
- [ ] Grep the release diff for any new output path that could carry a raw command line into a
      log, an error message, or telemetry.

## Adaptive Execution, Watchdog, Secret Boundary, and Memory Integrity

Required whenever this release changes `scripts/execution-profile.py`,
`scripts/execution-watchdog.py`, `scripts/redact.py`, `scripts/guard_audit.py`'s pattern set,
`scripts/durable.py`, `scripts/knowledge.py`, `scripts/dod-check.py`, the lifecycle wrappers, or
the durable write paths that redact.

- [ ] Run `bash scripts/test-adaptive-execution.sh` and confirm it exits `0`. Record the pass
      count in `eval-runs/<release>/summary.md`.
- [ ] Run `bash scripts/test-secret-boundary.sh` and confirm it exits `0`.
- [ ] Run `bash scripts/test-lifecycle-fs.sh` and confirm it exits `0`.
- [ ] Run `bash scripts/test-knowledge.sh` and confirm it exits `0`. Confirm its three mutation
      probes report the weakened build giving the weaker answer: repeated evidence must inflate
      confirmations, a contradiction must refresh `verified_at`, and payload-only accounting
      must overrun the budget.
- [ ] Confirm every mutation probe in all three reports that the weakened build gives the weaker
      answer. In particular: emptying the escalation table must drop a migration to `LIGHT`,
      removing the mutation-target overlap check must group two writers to one file, and marking
      every run stalled must kill work that was still producing.
- [ ] Confirm no escalating domain was removed from `ESCALATING_DOMAINS`, and that no new signal
      can lower a profile. Adding a relaxation condition is safe; removing an escalation is a
      breaking change to the safety posture.
- [ ] Confirm the `ALWAYS_REQUIRED` invariant set is unchanged and identical across all three
      profiles. A per-profile safety list is the thing this design exists to prevent.
- [ ] If the redaction pattern set changed, run `bash scripts/test-guard.sh` and account for any
      movement in the **false-positive** corpus. A benign command moving from `ALLOW` to `ASK`
      is a regression, and an over-eager redactor gets bypassed by the next person under
      pressure.
- [ ] Confirm the concurrency cap is still enforced and still clamps
      `AGENT_SKILLS_MAX_PARALLEL` rather than trusting it.
- [ ] Confirm a plan index written before the appended columns existed still parses and still
      defaults to `STANDARD`. Build one by hand; do not infer it.
- [ ] Confirm `parallel_group` still refuses a parent beside its child and a dot-segment alias
      beside its target, and still admits genuinely disjoint siblings. The suite asserts all
      three; read the assertions.

## Engineering Tool Capability Framework

Required whenever this release changes `scripts/tools.py`, `lib/tools/`, or the capability /
tool-definition contract.

- [ ] Run `bash scripts/test-tools.sh` and confirm it exits `0`. Record the pass count in
      `eval-runs/<release>/summary.md`.
- [ ] Run `agent-skills tools --include-fixtures doctor` and confirm it reports no integrity
      problems. `python3 scripts/validate-repo.py` runs the same check.
- [ ] Confirm every capability that reads large external output (`logs.read`, `query.read`,
      `message.sample`, `thread.read`, `document.read`, `errors.read`, `finding.read`,
      `timeline.read`, `traces.read`) is listed under `bounded_capabilities` on every tool that
      owns it.
- [ ] Confirm no reference or fixture tool id appears as a literal in `scripts/tools.py` —
      resolution stays data-driven.
- [ ] Confirm `tools status` and `tools resolve` print no secret value in any mode, only field
      names.
- [ ] If the capability vocabulary or the tool-definition contract changed, say so in the
      changelog and re-check [versioning.md](versioning.md#contracts-under-consideration-for-a-10-freeze).
- [ ] Confirm every tool marked `reference_status: validated` was actually exercised through the
      framework this release; anything only represented by a fixture stays labelled a fixture and
      is not described as supported.

## Meeting Intelligence

Required whenever this release changes `scripts/meeting*.py`, the `meetings/` part of
`scripts/knowledge.py`, `window_items` in `scripts/context.py`, or the `meeting-intelligence` skill.

- [ ] Run `python3 scripts/test-meeting.py` and confirm it exits `0` with no network access.
      Confirm its four mutation probes report the weakened build giving the weaker answer.
- [ ] Re-render and re-score the model-dependent evals
      (`python3 scripts/eval-meeting-intelligence.py render|score --runs eval-runs/<release>/meeting-intelligence`)
      and the adversarial run; record both tables in `eval-runs/<release>/summary.md`.
- [ ] Re-verify the Recall contract (bot create fields, status codes, retention, webhook signing)
      against Recall's **current** reference at `https://docs.recall.ai/llms.txt`, and update
      `scripts/fixtures/meeting-recall/` with the adapter when it changed.
- [ ] If a Recall key is available, run `AGENT_SKILLS_MEETING_LIVE_SMOKE=1 python3 scripts/test-meeting.py`.
      It authenticates and lists bots; it never creates one.
- [ ] Confirm no meeting module other than `meeting_recall.py` names a Recall field (the boundary
      test asserts it; read the assertion).

## Shared Knowledge

Required whenever this release changes `scripts/knowledge_*.py`, the Resolver paths in
`scripts/knowledge.py`, the knowledge-binding section of `scripts/access.py`, or the source layout.

- [ ] Run `python3 scripts/test-shared-knowledge.py` with no network. Confirm case 1 still matches
      the `1.2.0` output byte for byte, and that its four mutation probes report the weakened build
      giving the weaker answer.
- [ ] Run `python3 scripts/eval-shared-knowledge.py --out eval-runs/<release>/shared-knowledge` and
      record both tables in `eval-runs/<release>/summary.md`.
- [ ] Confirm no push path can target the default branch or use `--force`: read `_push_and_review`
      in `knowledge_git.py`, not just the test.
- [ ] If the fact schema or the manifest changed, bump `SUPPORTED_SOURCE_SCHEMA` / `schema_version`
      and confirm an older client goes read-only against it (case 15).
- [ ] Re-check the `gh` / `glab` command lines against each CLI's current documentation.

## Distribution and Packaging

Required whenever a release changes `lib/asrelease/`, `scripts/install.py`, `bin/agent-skills`,
the host adapters, or the npm bootstrap.

- [ ] Run `bash scripts/test-cli-install.sh` and confirm it exits `0`. Record the assertion count in
      `eval-runs/<release>/summary.md`.
- [ ] Run `python3 scripts/test-release-engine.py` and confirm it exits `0`.
- [ ] Run `bash scripts/audit-npm-package.sh` and read the file listing it prints. Do not skim it. A
      published npm tarball is public permanently and cannot be recalled, so this is the last point
      at which anything protected can be kept out of it.
- [ ] Confirm the packed tarball contains no skills, docs, evals, hooks, credentials, `.env` files,
      or absolute developer paths, and that the vendored engine is byte-identical to
      `lib/asrelease/` and `scripts/install.py`. The audit asserts all of this; read the output
      rather than trusting the summary line.
- [ ] Confirm `npm/package.json` declares no `preinstall`, `install`, `postinstall`, or `prepare`
      script. Nothing may run on `npm install`; installation happens only when a human types a
      command.
- [ ] Install **from the packed tarball**, not from the source tree, and run `doctor` and `verify`
      against the result. `npm link` is not proof: it does not exercise the `files` list, which is
      what decides what a publish actually contains.
- [ ] Confirm the repository `VERSION`, `npm/package.json` version, the git tag, and the release
      manifest inside the payload all state the same version.
- [ ] Exercise the recovery path by hand at least once: install, update, break the new release,
      `rollback`, and confirm `verify` is green afterwards. A rollback nobody has run is not a
      recovery path.
- [ ] Confirm exit codes still match [docs/versioning.md](versioning.md#exit-codes). After `1.0.0`
      these are frozen; changing one is a breaking change.
- [ ] Confirm a release source that cannot be read reports `AUTHENTICATION_REQUIRED` and exits `3`,
      rather than reporting a missing repository, hanging on a credential prompt, or echoing a
      token. Run it with a synthetic `GH_TOKEN` in the environment and grep the output.

## Telemetry Review

The counters exist so "the skills are improving" can be checked rather than asserted. Before
`v0.36.0` this step did not exist, and no skill change had ever traced to a telemetry finding.

- [ ] Run `python3 scripts/telemetry.py report --all` from the repository root (or
      `agent-skills telemetry report --all` if installed) and paste the output into
      `eval-runs/<release>/summary.md`.
- [ ] Compare per-skill `completed` versus `stopped` counts against the previous release's
      recorded report. A skill whose `stopped` share is rising is the release's first
      investigation target.
- [ ] Check whether any skill shows zero `invoked` events. Either it is unused and should be
      reconsidered, or its lifecycle wrappers are not running.
- [ ] Run `agent-skills knowledge doctor` (or `python3 scripts/knowledge.py doctor`)
      in any repository that has a committed
      knowledge base, and record the result.
- [ ] If the report drove a skill change this release, say so in the changelog entry. If it
      drove nothing, say that too — an unread counter is worse than no counter, because it
      looks like evidence.

## Documentation

- [ ] Inspect README rendering on GitHub.
- [ ] Inspect raw README readability in GitHub source view or a local editor.
- [ ] Inspect Markdown tables for rendering and raw-source readability.
- [ ] Inspect [docs/README.md](README.md) and new or changed docs for readable Markdown.
- [ ] Inspect skill links from the README, docs index, and each changed `SKILL.md`.
- [ ] Confirm examples and eval scenarios still match the current output contracts.
- [ ] Confirm release-scoped eval runs exist under `eval-runs/<release>/` with a summary file.
- [ ] Confirm [known limitations](known-limitations.md) still describe what validation cannot prove.

## Deprecations

- [ ] Check the deprecated-name table in [docs/versioning.md](versioning.md). Remove any alias
      whose removal release is this one, and delete its row.
- [ ] If this release adds an alias, give it a removal release in that table rather than leaving
      it open-ended.

## Release Metadata

- [ ] Update `CHANGELOG.md` under `Unreleased` or move notes into the release section.
- [ ] Before tagging, move release entries out of `Unreleased` into the versioned release section.
- [ ] Update `VERSION`.
- [ ] Update each `SKILL.md` `metadata.version` when skill behavior or contracts changed.
- [ ] Confirm README status text matches `VERSION`.

## Public-Safety Review

- [ ] Confirm there are no secrets, private tokens, private hostnames, local absolute paths, or real
  customer data in tracked files.
- [ ] Confirm examples and evals use generic systems, placeholder users, and safe data.
- [ ] Confirm no internal ticket prefixes or company branch rules are described as universal rules.

## Security Review

Required when a release changes authentication, credential storage, global filesystem state, or the
trust boundary around repository-supplied content.

- [ ] Record a threat-by-threat review under `docs/security-review-<release>.md`, following
      [the v0.37.0 review](security-review-v0.37.0.md) as the shape.
- [ ] For each threat, state whether it was **probed**, **reasoned about**, or left **unproven**.
      An unlabelled claim reads as evidence when it is not.
- [ ] Record any finding raised during the review and its resolution, including a decision to accept
      the behaviour and correct the documentation instead.
- [ ] Record residual risks, the control offered for each, and why that control is not the default.
- [ ] Pin any behaviour the review decided is intentional with a test, so it cannot drift away from
      the documentation later.
- [ ] **Show each security probe failing when the property is removed.** A probe that asserts against
      a mechanism the code does not use passes regardless of whether the property holds. In v0.37.0
      the critical-criterion probe did exactly that — it targeted `.agent-skills.yml`, which the
      resolver never reads — and two real holes shipped past it. Revert the fix, watch the test fail,
      restore it.

## Diff Review

Run **after** validation is green and **before** merge. A release that passes every gate can still be
wrong; v0.37.0 passed all of them and a reading of its own diff found five live defects, two in the
criterion the release called critical.

- [ ] Review the complete diff against the base branch, not just the files you remember touching:
      `git diff main...HEAD`.
- [ ] Have the review done by something that did not write the code — a second person, or a review
      agent with no stake in the change being correct.
- [ ] Reproduce every claimed defect before fixing it, and record which ones reproduced. A finding
      that cannot be reproduced is a hypothesis.
- [ ] Add a regression test per accepted finding, and confirm it fails against the pre-fix code.
- [ ] Re-run the full validation section afterwards. Fixes are changes.
- [ ] Record what the review changed in `eval-runs/<version>/summary.md`, including the fact that the
      suites were green beforehand.

## Private-Source Acceptance (Stage B)

Required before `1.0.0-rc.1`, and only meaningful once the repository is private.

- [ ] Confirm the GitHub repository visibility is **private**. `scripts/test-private-source.sh`
      refuses to run against a public repository, because anonymous access would satisfy every
      case in it and nothing about authenticated distribution would be proven.
- [ ] Run `bash scripts/test-private-source.sh` and confirm it prints
      `PRIVATE_SOURCE_DISTRIBUTION_READY: YES`.
- [ ] Confirm it installed from the **remote**, not from this checkout, into a throwaway `HOME`.
- [ ] Confirm the unauthenticated half exits `3` with `AUTHENTICATION_REQUIRED`, does not report the
      repository as missing, names a way to fix it, and does not hang.
- [ ] Record the result in `eval-runs/<release>/summary.md`.

## Release Publication

- [ ] Create GitHub release notes from the changelog entries.
- [ ] Verify sponsor and funding links still render, including
      [.github/FUNDING.yml](../.github/FUNDING.yml).
- [ ] Tag the release with the `v` prefix, for example `v0.8.0`.
- [ ] Verify `agent-skills check-updates` reports `up to date` against the new tag.
- [ ] Verify the release page links to the correct tag, changelog, docs, and skill files.
- [ ] If this release publishes the npm bootstrap: run `bash scripts/audit-npm-package.sh` one final
      time against the exact tarball being published, then `npm publish` it, then install **from the
      registry** on a machine with no source checkout and run `doctor` and `verify`.
- [ ] If publication is deliberately deferred, say so explicitly in the changelog and record what
      remains outstanding. A deferred publish that nobody wrote down becomes a release nobody can
      install.
