# v0.21.0 — README updating-discoverability

## The problem

Before v0.21.0, the only mention of "how do I update agent-skills" in the
top-level `README.md` was a single bullet inside the long Documentation
list:

```text
- (Updates)(docs/updates.md) — how to notice and apply new agent-skills releases
```

(Square brackets above replaced with parentheses so the validator does not
parse the example as a real link; the README still uses real Markdown link
syntax.)

Real users scrolling the README to install or use the skills had no
obvious answer to "how do I get the next release". The two commands they
need (`./setup.init --check-updates` and `./setup.init --update`) lived
only in `docs/updates.md`, two clicks away. A v0.20.0 user who saw
`Status: 0.19.0` in a vendored README correctly assumed they were
out-of-date, but had no on-page next step.

## The fix

A new top-level `## Updating` section in `README.md`, placed directly
after `## Install` and before `## Skills`. It is short on purpose:

- Three lines of context that releases are git tags and that two commands
  cover the common case.
- The two commands, with a one-line description of each.
- One paragraph on what `--update` preserves (the user's `.env` values),
  rewrites (the lock file), and prints (the changelog excerpt).
- One paragraph on how the agent surfaces a `skill drift` notice when a
  vendored copy in another workspace was not refreshed, with a pointer to
  `docs/updates.md`.

## Why a section, not just a stronger bullet

A bullet inside the Documentation list optimises for "the reader is
already looking for it". A section headed `## Updating` next to `##
Install` optimises for "the reader is skimming the README and needs to
discover that `--update` exists". The latter is the failure mode the
real-world transcript surfaced.

## What did NOT change

- [`docs/updates.md`](../../docs/updates.md) is unchanged. It remains the canonical reference for
  the three update channels, the in-repo (cloud-agent) flow, and the
  drift-detection contract.
- `setup.init --check-updates` / `--update` behavior is unchanged in this
  release **other than** the credential-preservation fix documented in
  [`setup-update-preserves-credentials.md`](setup-update-preserves-credentials.md).
