# Release Checklist

Use this before tagging a release.

## Validation

- [ ] Run `python3 scripts/validate-repo.py` from the repository root.
- [ ] Confirm validator line-readability checks pass for Markdown, YAML, and Python source.
- [ ] Confirm validator file-density and minification checks pass for Markdown, YAML, and Python.
- [ ] Inspect warnings and decide whether they are acceptable.
- [ ] Confirm GitHub Actions validation passes on the release PR or branch.

## Documentation

- [ ] Inspect README rendering on GitHub.
- [ ] Inspect raw README readability in GitHub source view or a local editor.
- [ ] Inspect Markdown tables for rendering and raw-source readability.
- [ ] Inspect [docs/README.md](README.md) and new or changed docs for readable Markdown.
- [ ] Inspect skill links from the README, docs index, and each changed `SKILL.md`.
- [ ] Confirm examples and eval scenarios still match the current output contracts.
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
- [ ] Verify the release page links to the correct tag, changelog, docs, and skill files.
