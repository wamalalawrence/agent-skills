# v0.19.0 Eval Run: Skill-Source Resolution

**Eval scenario:** `evals/skill-source-resolution-ambiguity.md`
**Skills under test:** `software-engineer` (primary), `issue-investigator` (secondary).
**Run date:** maintainer dry-run for the v0.19.0 release.
**Workspace fixture:** `.skills` symlink + vendored `.agent-skills/skills` at a stale
version + source clone, with `.agent-skills.lock` declaring the current version.

## Run notes

The eval was executed as a paper walkthrough plus a real run of `setup.init --verify`
against three synthetic fixtures: (1) only `.skills` present (the default after first-run
setup), (2) `.skills` plus a stale vendored copy, (3) two distinct sources with no
`skills.canonical_dir` configured.

The skills were exercised by reading their (unchanged) Required Workflow against the new
`docs/skill-source-resolution.md` resolution gate and asking: *"which directory does the
agent load from, and does the answer match the doc?"*. Where the answer would have been
"both" or "whichever the file lister returned first", the resolution gate's rule wording
was tightened.

## Findings

- Fixture 1 (`.skills` only): no ambiguity warning. The resolved realpath matches the
  source repo's `skills/`, so the dedupe step collapses both candidates into one source.
  CI exercises this exact fixture.
- Fixture 2 (`.skills` + stale vendored copy): ambiguity warning fires. Two distinct
  realpaths, no `skills.canonical_dir`. The agent (per the resolution doc) prefers the
  source whose `metadata.version` matches `.agent-skills.lock` and emits one drift
  warning naming both versions and the rejected path.
- Fixture 3 (two distinct sources, no canonical configured, no lock match): the agent
  reports ambiguity and asks the operator. It does not pick. The recommendation in chat
  links `docs/skill-source-resolution.md` and shows the exact YAML snippet to add.
- The lock file is gitignored; verification confirmed it does not appear in
  `git status` after `setup.init`. `--verify` warns when the lock is missing or its
  recorded version differs from `VERSION`.
- `setup.init --check-updates` returns `0` on a clean clone at the latest tag, and
  `10` against a synthetic fixture where the local `VERSION` was rewound to `0.17.0`.
- `setup.init --update --branch main` refuses on a dirty working tree (verified by
  touching a tracked file before invocation), then succeeds after `git stash`.

## Pass / fail

- [x] Resolution order is documented, deterministic, and matches the implemented
  ambiguity check.
- [x] No false-positive ambiguity warning on the default `.skills`-only layout.
- [x] Real ambiguity (two distinct sources) is surfaced once, with both paths named.
- [x] Drift warnings name the chosen and rejected versions explicitly.
- [x] Lock file is JSON, gitignored, and contains no secrets or private absolute paths
  beyond `source_repo_dir` (which is a local path the user already controls).
- [x] `--check-updates` and `--update` exit codes match the documented contract.
- [x] No secret value, no token, and no real ticket key appears in any output.

Result: **pass**. Maintainer-authored, illustrative.
