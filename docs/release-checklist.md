# Release Checklist

Use this before tagging a release.

## Validation

One command runs the mechanical half of this list, so the evidence recorded in
`eval-runs/<release>/summary.md` is reproducible rather than asserted:

```bash
bash scripts/test-release-readiness.sh
```

It covers the structural validators, syntax across every shipped artifact, all four test suites,
the CLI surface, a clean-`HOME` install with drift and uninstall, an upgrade from the previous
release tag in both the legacy-workspace and global-install shapes, cloud/in-repo mode, the
public-safety sweep, README and link integrity, the telemetry report, and version consistency.
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

## Release Publication

- [ ] Create GitHub release notes from the changelog entries.
- [ ] Verify sponsor and funding links still render, including
      [.github/FUNDING.yml](../.github/FUNDING.yml).
- [ ] Tag the release with the `v` prefix, for example `v0.8.0`.
- [ ] Verify `./setup.init --check-updates` reports `up to date` against the new tag.
- [ ] Verify the release page links to the correct tag, changelog, docs, and skill files.
