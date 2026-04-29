# v0.19.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.19.0`. It scores the new
skill-source resolution contract and the self-update flow that together prevent agents
from loading two copies of the same skill or running indefinitely against a stale clone.

Category: maintainer-authored (illustrative).

## Scope of this release

- New `docs/skill-source-resolution.md` defining the six-step resolution order, the
  duplicate-handling rules (no merge / no load-all / warn on drift), and the mode-specific
  defaults that match what `setup.init` ships.
- New `docs/updates.md` documenting three update channels: `setup.init --check-updates`,
  `setup.init --update`, and the manual `git pull` path used by contributors.
- New `scripts/check-updates.py` (dependency-free) and the matching `setup.init`
  `--check-updates` / `--update` / `--branch` flags.
- New `<workspace>/.agent-skills.lock` advisory metadata file. JSON, gitignored, schema
  `agent-skills.lock/v1`. Every `setup.init` run writes it; `--verify` reports drift.
- New `skills:` block in `.agent-skills.example.yml` covering `canonical_dir`,
  `duplicate_policy`, `source_repo_dir`, `allow_source_repo_fallback`,
  `warn_on_version_drift`. All keys are optional.
- New `evals/skill-source-resolution-ambiguity.md` covering the exact failure mode the
  release targets (two distinct skill sources, version drift, no canonical configured).
- Validation extended: `REQUIRED_FILES` plus a new
  `check_agent_skills_yaml_skills_block` ensuring the example YAML keeps the documented
  keys.

## Scoring summary

- Resolution-order clarity: 5/5. The order is identical across the doc, the
  `.agent-skills.example.yml` comments, the `setup.init` ambiguity check, the lock-file
  schema, and the eval scenario. Each rule names which file it reads from and what wins.
- Symlink dedupe: 5/5. The ambiguity check resolves `realpath` before counting sources, so
  the expected `.skills -> agent-skills/skills` shape from `setup.init` does **not** trigger
  a false-positive warning. CI asserts this.
- Update mechanism: 5/5. Three channels, distinct exit codes (`0` / `10` / `2`), no auto-
  update, dirty-tree refusal, lock-file rewrite on success. Symmetric rollback.
- Secret hygiene: 5/5. `check-updates.py` reads `--token` and `GITHUB_TOKEN` but never
  prints them. The lock file contains no credentials. `setup.init --update` prints no
  secret values from the env block.
- Surgical-edit discipline: 5/5. One new doc pair (`skill-source-resolution.md`,
  `updates.md`), one new script, one new eval, three new `setup.init` subcommands, one
  new validator check, version bump. No new skills, no renames, no required env vars,
  no `.env.example` change.
- Public-good portability: 5/5. Every example uses placeholder paths and `wamalalawrence/
  agent-skills` (the canonical repo). No private hosts, no real ticket prefixes.

## Reviewer self-rebuttal

The most credible scenarios in which this release is wrong:

- **Vendored-copy users on cloud agents** still need a manual step (submodule update or
  re-vendor). `--update` only refreshes the source clone and the workspace symlink. The
  `docs/updates.md` "in-repo" section calls this out and `scripts/check-updates.py
  --vendored` works there, but a future release could ship a `make vendor-skills` recipe
  in the `agent-skills` source repo to make re-vendor a one-liner.
- **The lock file is advisory, not authoritative.** A skill loader that ignores both
  `.agent-skills.yml` and `.agent-skills.lock` will still happily load duplicates. The
  resolution doc is binding for our skills, but third-party loaders may not read it. We
  accept this — the lock file's job is to make drift visible to a cooperative agent, not
  to prevent a hostile one.
- **`semver_cmp` in `setup.init` uses `sort -V`.** Pre-release suffixes like `0.19.0-rc1`
  sort correctly under GNU sort but BSD sort treats them as equal. The script is
  documented as targeting release tags only; the eval and CI exercise plain semver.

## Pass / fail summary

The release passes maintainer review. Validation is green, `setup.init --update` and
`--check-updates` were exercised against the local clone and a synthetic vendored fixture,
the ambiguity check fires only on real drift (CI fixture verifies no false positive).
