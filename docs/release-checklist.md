# Release Checklist

Use this before tagging a release.

## Validation

- [ ] Run `python3 scripts/validate-repo.py` from the repository root.
- [ ] Confirm validator line-readability checks pass for Markdown, YAML, and Python source.
- [ ] Confirm validator file-density and minification checks pass for Markdown, YAML, and Python.
- [ ] Inspect warnings and decide whether they are acceptable.
- [ ] Confirm GitHub Actions validation passes on the release PR or branch.

## Telemetry Review

The counters exist so "the skills are improving" can be checked rather than asserted. Before
`v0.36.0` this step did not exist, and no skill change had ever traced to a telemetry finding.

- [ ] Run `python3 scripts/telemetry.py report --all` and paste the output into
      `eval-runs/<release>/summary.md`.
- [ ] Compare per-skill `completed` versus `stopped` counts against the previous release's
      recorded report. A skill whose `stopped` share is rising is the release's first
      investigation target.
- [ ] Check whether any skill shows zero `invoked` events. Either it is unused and should be
      reconsidered, or its lifecycle wrappers are not running.
- [ ] Run `python3 scripts/knowledge.py doctor` in any repository that has a committed
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

## Release Publication

- [ ] Create GitHub release notes from the changelog entries.
- [ ] Verify sponsor and funding links still render, including
      [.github/FUNDING.yml](../.github/FUNDING.yml).
- [ ] Tag the release with the `v` prefix, for example `v0.8.0`.
- [ ] Verify `./setup.init --check-updates` reports `up to date` against the new tag.
- [ ] Verify the release page links to the correct tag, changelog, docs, and skill files.
