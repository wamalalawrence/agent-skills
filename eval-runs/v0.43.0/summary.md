# Eval run — v0.43.0 (CLI installation and distribution)

Release-scoped evidence for `v0.43.0`. Everything below was produced by running the commands
named, not by assertion.

## What this release changed

Installation stopped being an act of repository maintenance. `git clone && ./setup.init` is
replaced by `npx @wamala/agent-skills install`, backed by one installation engine, a release
provider abstraction, a versioned install root, and a transaction that either completes or leaves
the previous release running.

```text
npm bootstrap ─┐
agent-skills  ─┼─> lib/asrelease  ─> Release Provider ─> local | git | (future) registry
setup.init    ─┘        │
                        └─> RESOLVE > DOWNLOAD > VERIFY > STAGE > SELF-TEST
                                    > ACTIVATE > HOSTS > VERIFY
```

## Verification

```bash
bash scripts/test-release-readiness.sh
```

| Gate | Result |
| --- | --- |
| `validate-repo.py` | pass, 61 warnings |
| `run-evals.py` | pass — 47 files, 11 skills known, 0 failures, 0 warnings |
| `bash -n` across `setup.init`, `lib`, `bin`, `scripts`, `hooks` | pass |
| `ast.parse` across every `scripts/*.py` and `lib/asrelease/*.py` | pass |
| `test-cli-install.sh` | pass — 104 assertions |
| `test-release-engine.py` | pass — 21 checks |
| `test-global-install.sh` | pass — 112 assertions |
| `test-access-resolution.sh` | pass — 100 assertions |
| `test-front-door-skill.sh` | pass — 63 assertions |
| `test-context-optimizer.sh` | pass — 105 assertions |
| `test-guard.sh` | pass — 108 assertions |
| `audit-npm-package.sh` | pass — 14 files, no product content |
| clean-`HOME` install, verify, drift, update, rollback, uninstall | pass |
| upgrade from the previous release's installation | pass |
| upgrade across the front-door rename (`v0.38.0`) | pass |
| cloud / in-repo mode unaffected | pass |
| public-safety sweep | pass |
| README and documentation integrity | pass |
| version consistency | pass |

Total: 613 assertions across seven suites, plus the release-readiness gates.

## The installation contract, as exercised

`scripts/test-cli-install.sh` runs fourteen cases, each against a throwaway `HOME` whose path
contains a space. The suite is written around failure rather than success, because the property
worth proving is not that a good install works — it is that a bad one changes nothing.

| Case | What it proves |
| --- | --- |
| clean install | install, verify, PATH link, no credential requested or stored, unrelated user skills untouched, idempotent rerun |
| version coherence | manifest, `current`, payload `VERSION`, `release.json`, and `SKILL.md` metadata all agree; helpers resolve inside the active release |
| update and rollback | host registrations follow the active release in both directions without being rewritten |
| failed update (tampered payload) | exit `5`, previous release still active, nothing staged |
| failed update (broken runtime) | exit `6` at the self-test, previous release still active |
| interrupted update | no mixed installation; `current` and its payload still agree; staging cleaned up |
| downgrade | refused by `update` with the way back named; honoured by `rollback` and by `--allow-downgrade` |
| migration | a reconstructed pre-CLI installation upgrades; credential identities and project bindings survive |
| uninstall | releases, registrations, hooks, and launcher removed; user skills, user hooks, and identities kept; `--purge` is the only thing that removes identities |
| Execution Guard | the hook resolves through `current`, follows update and rollback, and uninstall leaves the user's own hook alone |
| Context Optimizer | skill and runtime installed together and runnable from the installed release |
| offline | `doctor`, `verify`, `versions --local`, and a runtime helper all work with no network |
| missing distribution access | exit `3`, `AUTHENTICATION_REQUIRED`, no token echoed, nothing installed, no hang |
| npm artifact | install and update from the **packed tarball** over a real git remote, with no clone anywhere in the flow |

## Threat probes

`scripts/test-release-engine.py`. Each is an assertion that the hostile input is refused, not that
the benign one is accepted.

| Probe | Result |
| --- | --- |
| archive member containing `..` | rejected; **and no member written at all** |
| archive member with an absolute path | rejected |
| symlink escaping the extraction root | rejected |
| symlink to an absolute path | rejected |
| device or FIFO member | rejected |
| setuid member | rejected |
| tampered payload vs. its manifest hash | rejected, exit `5` |
| payload `VERSION` disagreeing with its manifest | rejected |
| payload not matching the release requested | rejected |
| payload symlink pointing outside the release | rejected |
| tree hash sensitivity | ignores mtime, notices an exec-bit change |
| git stderr carrying a token | redacted before it can be printed or logged |
| unknown provider name (`../../etc/evil`) | usage error; no path is ever loaded |
| exit-code table | unchanged |
| re-installing the active release | moved aside, never deleted in place |

## Provider independence

The claim "installation is not coupled to GitHub" is tested rather than asserted. The suite
registers an in-process `FakeRegistryProvider` — it synthesises a payload, has an entitlement
check, and can report `AUTHENTICATION_REQUIRED` — and runs the **real** `InstallTransaction`
through it end to end, into a home directory with a space in its path. The result is a working
installation with `provider.id == "fake-registry"` in the manifest.

If installation ever grows a hidden dependency on git, that test fails.

## Package content

```bash
bash scripts/audit-npm-package.sh
```

14 files, 28.4 KB packed. The audit inspects the packed tarball, not the `files` list, because
those two disagree the moment a glob is wrong.

```text
package/package.json          package/vendor/install.py
package/README.md             package/vendor/asrelease/*.py   (8 files)
package/LICENSE               package/vendor/asrelease/providers/*.py (3 files)
package/bin/agent-skills-bootstrap.js
```

| Check | Result |
| --- | --- |
| product content (skills, docs, evals, hooks) | none |
| credential-shaped files | none |
| repository internals (`.git`, `.github`, `.venv`) | none |
| absolute developer home paths | none |
| secret-shaped strings | none |
| npm lifecycle scripts | none |
| vendored engine identical to `lib/asrelease/` and `scripts/install.py` | identical |

## Telemetry

```bash
python3 scripts/telemetry.py report --all
```

```json
{"total_events": 2, "skills": {"software-engineer": {"completed": 1},
 "manual-tester": {"completed": 1}}, "unknown_events": {}}
```

Two completed events, no stops. The local counter is not a sample worth drawing conclusions from,
and it drove no skill change this release. Recording that it drove nothing is the point: an unread
counter is worse than no counter, because it looks like evidence.

## Stage A acceptance

While the repository is public, and before any visibility change:

```text
PUBLIC_SOURCE_INSTALL:         PASS
AUTH_REQUIRED_BEHAVIOR:        PASS
RELEASE_PROVIDER_ABSTRACTION:  PASS
PACKAGE_CONTENT_AUDIT:         PASS
PRIVATE_TRANSITION_READY:      YES
```

- **PUBLIC_SOURCE_INSTALL** — clean environment, packed npm bootstrap, git provider, real tagged
  remote, host registration, `doctor`, `verify`. No manual clone anywhere in the flow.
- **AUTH_REQUIRED_BEHAVIOR** — an unreadable remote exits `3` with `AUTHENTICATION_REQUIRED`, names
  distribution access, does not report the repository as missing, does not hang, echoes no token,
  and installs nothing.
- **RELEASE_PROVIDER_ABSTRACTION** — the real install transaction runs to completion through an
  in-process fake registry provider that has never heard of git.
- **PACKAGE_CONTENT_AUDIT** — 14 files, no product content, no credentials, no lifecycle scripts,
  vendored engine byte-identical to the repository's.

Stage B is `scripts/test-private-source.sh`. It refuses to run while the repository is public.

## What this run does not prove

- **Private-source installation.** The repository was public throughout. The git provider's
  authentication-required path was exercised against an unreadable remote, and its authenticated
  path against a local remote, but installing from an authenticated private GitHub repository is
  Stage B and requires the visibility change first. See
  [docs/security-review-v0.43.0.md](../../docs/security-review-v0.43.0.md).
- **Publication.** Nothing was published to npm. Installation was tested from the packed tarball,
  which exercises the `files` list and the real package layout, but not the registry round trip.
- **Windows.** Tested on macOS. CI covers Linux. Windows is WSL or Git Bash, untested here.
- **Real host behaviour.** Registrations are asserted on the filesystem. Whether Cursor or Kiro
  then loads a skill is the host's business and is not observable from a test.
