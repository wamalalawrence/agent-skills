# Eval run — v0.43.1 (Private-source validation)

Release-scoped evidence for `v0.43.1`. Everything below was produced by running the commands
named, not by assertion.

## What this release is

A patch release. No skill structure, configuration shape, handoff artifact, output contract, CLI
command, or exit code changed. Two things did:

- the npm package identity was corrected from the unpublishable `@wamala/agent-skills` (tagged in
  `v0.43.0` but never actually publishable — see below) to `@wamalalawrence/agent-skills`, which is
  live;
- the repository's transition from public to private was validated end to end (Stage B), and two
  supporting defects found while doing that were fixed — both outside product code.

## Verification (pre-tag, against this checkout)

```bash
python3 scripts/validate-repo.py
python3 scripts/run-evals.py
bash scripts/test-cli-install.sh
python3 scripts/test-release-engine.py
bash scripts/test-global-install.sh
bash scripts/test-access-resolution.sh
bash scripts/test-front-door-skill.sh
bash scripts/test-guard.sh
bash scripts/test-context-optimizer.sh
bash scripts/audit-npm-package.sh
```

| Gate | Result |
| --- | --- |
| `validate-repo.py` | pass, 61 warnings |
| `run-evals.py` | pass — 47 files, 11 skills known, 0 failures, 0 warnings |
| `test-cli-install.sh` | pass — 104 assertions |
| `test-release-engine.py` | pass — 21 checks |
| `test-global-install.sh` | pass — 112 assertions |
| `test-access-resolution.sh` | pass — 100 assertions |
| `test-front-door-skill.sh` | pass — 63 assertions |
| `test-guard.sh` | pass — 108 assertions |
| `test-context-optimizer.sh` | pass — 105 assertions |
| `audit-npm-package.sh` | pass — 14 files, no product content, vendored engine byte-identical |

Every SKILL.md `metadata.version` and `VERSION` agree at `0.43.1`.

## Stage B, re-run against this exact release

Deferred to a post-tag verification, the same pattern `v0.43.0` used: Stage B compares the
installed release against the local `VERSION` file, so it cannot pass against a tag that does not
exist on the remote yet. Recorded once `v0.43.1` is tagged and pushed — see the "Post-tag
verification" section below, or if absent, the tag was not yet pushed when this file was written.

## What changed since v0.43.0

### Package identity corrected

`v0.43.0` was tagged naming `@wamala/agent-skills`. That scope was never publishable — an
authenticated publish, two-factor authentication satisfied, returned `404` on the registry `PUT`.
The actual published, verified package is `@wamalalawrence/agent-skills@0.43.0`, and `0.43.1` keeps
that identity. See [`docs/release-providers.md`](../../docs/release-providers.md#the-package-name).

### Stage B — private-source acceptance

Full account: [`eval-runs/v0.43.0/summary.md`](../v0.43.0/summary.md#stage-b--private-source-acceptance)
(the suite and its findings are recorded there, dated to when the repository was actually made
private; this release packages the fix and re-confirms it against the tagged release).

Two fixes, both outside product code:

- **Test harness:** the private-source acceptance suite's sandbox isolation broke macOS Keychain
  resolution for `gh`-stored credentials (Keychain Services keys its default search list to
  `$HOME`). Fixed by grafting in read-only symlinks to `~/Library/Preferences` and
  `~/Library/Keychains` — nothing else, nothing written.
- **CI:** the link checker started failing on the repository's own homepage URL, which now 404s to
  anonymous requests since the repository is private. One narrow ignore-pattern added.

`lib/asrelease/`, `scripts/install.py`, `bin/agent-skills`, and every host/guard registry are
unchanged from `v0.43.0`.
