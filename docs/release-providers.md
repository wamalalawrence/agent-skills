# Release providers and distribution

How a release gets from wherever it is published onto a machine, and why the installer does not
know or care which "wherever" that is.

## The problem this solves

Until v0.43.0, installing Agent Skills meant cloning this repository and running a script inside
it. That made the distribution channel and the product the same object: the installer was a file in
the thing being installed, updates were `git pull`, and "which version am I on" was answered by a
working tree. It worked while the repository was public and every user was also a contributor. It
stops working the moment either of those changes.

v0.43.0 separates the two. There is a product — skills, runtime, docs — and there is a way of
obtaining it. The second is a replaceable component.

## The abstraction

```text
agent-skills install
        |
        v
  Release Provider
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
GitReleaseProvider    LocalReleaseProvider    (future) PremiumRegistryProvider
   git tags,            a checkout or a          subscription entitlement,
   public or            fixture release          short-lived download
   authenticated                                 authorisation, signed bundle
```

A provider answers four questions and nothing else:

```text
resolve_latest(channel) -> which release should I install?
resolve_version(v)      -> where is this specific release?
fetch_release(ref, dir) -> put its payload here
verify_release(staged)  -> is this the release it claims to be?
```

Everything after `fetch_release` — staging, the self-test, activation, host reconciliation,
rollback — is identical no matter which provider produced the payload. The user-facing commands do
not change either:

```bash
agent-skills install
agent-skills update
```

The code lives in [`lib/asrelease/providers/`](../lib/asrelease/providers). The installer imports
`build_provider` and never mentions git again.

### Why this is not speculative generality

Two providers exist today and both are load-bearing. `local` is how the maintainer tests an
unreleased branch and how the entire acceptance suite runs without a network. `git` is how everyone
else installs. A third is proven rather than promised: `scripts/test-release-engine.py` registers an
in-process fake registry provider — one that synthesises a payload, has an entitlement check, and
can report `AUTHENTICATION_REQUIRED` — and runs the real install transaction through it. If
installation ever grows a hidden dependency on GitHub, that test fails.

### How providers are selected

By name, from a fixed registry, in-process:

```bash
agent-skills install                          # git, the default
agent-skills install --source ./checkout      # local
agent-skills install --repo <url>             # git, different remote
```

There is deliberately no environment variable or config file that loads a provider from a path. A
repository the user has merely opened must not be able to point the global installer at code, or at
credentials, of its choosing.

## Distribution access is not project access

Reading the release source may require authentication. That is **distribution access**: proof that
this machine may download the product. It is not, and is never mixed with, **project access** —
Jira, AWS, a database, a GitHub project API. The rule from v0.37.0 still holds:

> Installing Agent Skills does not configure project credentials.

The git provider uses credentials the developer already has, in the least intrusive order it can:

1. **native** — git's own credential helpers and ssh-agent. A configured Git Credential Manager, the
   macOS keychain, an ssh remote, or `gh auth setup-git` all land here. Agent Skills reads nothing.
2. **gh** — the GitHub CLI, when it is installed, already logged in, and the remote is a github.com
   https URL. The token reaches git through an askpass helper that shells out to `gh auth token`, so
   it never enters the installer's process, never appears in a command line visible to `ps`, and is
   never written to disk or into Agent Skills configuration.

There is no token prompt and no `GH_TOKEN` requirement. Interactive prompting is disabled outright
(`GIT_TERMINAL_PROMPT=0`, ssh `BatchMode=yes`), because an installer that blocks on an invisible
credential prompt inside an editor's integrated terminal is worse than one that fails.

If neither strategy works, the installer exits `3` and says so:

```text
agent-skills: AUTHENTICATION_REQUIRED: this machine is not authorised to read
  https://github.com/wamalalawrence/agent-skills.git
```

GitHub answers an unauthenticated request for a private repository with a 404, so "repository not
found" is treated as an access failure rather than reported as a missing repository. Reporting the
wrong one sends people to look for a typo that is not there.

Every git message is passed through a redactor before it is printed or logged.

## Integrity

Every release carries a manifest, `release.json`, written when the payload is assembled:

```json
{
  "schema": "agent-skills.release/v1",
  "version": "0.43.0",
  "channel": "stable",
  "provider": "git",
  "source": { "repo": "...", "ref": "refs/tags/v0.43.0", "commit": "..." },
  "payload": { "tree_sha256": "...", "file_count": 164, "algorithm": "sha256-tree/v1" },
  "signature": null
}
```

`tree_sha256` covers every payload file's relative path, whether it is executable, and its content —
and deliberately not its mtime or owner, so an ordinary copy does not invalidate it while a changed
byte or a newly executable file does.

Before a payload is allowed near activation, four things must agree: the version that was requested,
the tag the provider resolved, the `VERSION` file inside the payload, and the manifest. Any
disagreement is an integrity failure (exit `5`), not a warning.

`signature` is reserved. Signed releases will add a field, not a schema. No custom cryptography is
used or planned.

### Archive safety

Anything unpacked from an archive is treated as hostile input. Absolute paths, `..` components,
symlinks or hardlinks pointing outside the extraction root, device nodes, and setuid bits are all
rejected — and rejected before a single byte is written, so a hostile archive cannot half-extract.
The adversarial cases are in `scripts/test-release-engine.py`.

## Release channels

```bash
agent-skills update                  # stable, the default
agent-skills update --channel rc     # release candidates as well
```

`stable` never offers a pre-release. `rc` is a superset: someone tracking release candidates is
still offered the stable release that supersedes the last one, or they would be pinned to
pre-releases forever.

## What comes next

A subscription registry would implement the same four verbs:

```text
agent-skills login
        ↓
Agent Skills subscription service
        ↓
entitlement check
        ↓
short-lived download authorisation
        ↓
signed release bundle
```

None of that is built. What matters now is that building it later is a new file in
`lib/asrelease/providers/`, not a rewrite of installation — and that today's GitHub authentication
is not baked into the long-term product contract.

## See also

- [Installation](installation.md)
- [Updates, rollback, and channels](updates.md)
- [Versioning and exit codes](versioning.md)
