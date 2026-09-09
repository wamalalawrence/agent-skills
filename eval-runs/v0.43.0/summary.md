# Eval run — v0.43.0 (CLI installation and distribution)

Release-scoped evidence for `v0.43.0`. Everything below was produced by running the commands
named, not by assertion.

## What this release changed

Installation stopped being an act of repository maintenance. `git clone && ./setup.init` is
replaced by `npx @wamalalawrence/agent-skills install`, backed by one installation engine, a release
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

## Stage B — private-source acceptance

Run after the repository was made private (2026-09-09), against the **real remote**, from a
genuinely clean sandbox HOME — never the source checkout, never the existing installation already
on this machine.

```bash
bash scripts/test-private-source.sh
```

41 assertions, 0 failures, across two independent runs.

```text
PRIVATE_REPOSITORY_ACCESS       PASS
CLEAN_PRIVATE_INSTALL           PASS
INSTALLED_VERSION               0.43.0 (expected 0.43.0)
AGENT_SKILLS_DOCTOR             PASS
AGENT_SKILLS_VERIFY             PASS
PRIVATE_UPDATE_PATH             PASS
RELEASE_PROVIDER                git (expected git)
HOST_REGISTRATION               PASS
EXECUTION_GUARD_COHERENCE       PASS
EXISTING_STATE_ISOLATION        PASS

PRIVATE_AUTHENTICATED_INSTALL: PASS
PRIVATE_UPDATE: PASS
AUTHENTICATION_REQUIRED_BEHAVIOR: PASS
PRIVATE_SOURCE_DISTRIBUTION_READY: YES
```

- **Authenticated case** — packed npm bootstrap, `install --all-hosts` against the private remote,
  `doctor`, `verify`, `versions --json`, `check-updates`, `update`, host registration into every
  supported host directory, and Execution Guard installed and confirmed to resolve through the
  release fetched from the private source. No token-shaped string in any log or written to disk.
- **Unauthenticated case** — every credential path removed (no git config, no gh config, no SSH
  agent, no Keychain access; a synthetic, invalid `GH_TOKEN` present throughout). Exits `3`,
  reports `AUTHENTICATION_REQUIRED`, leads with the classification rather than a raw git error,
  never reports the repository as "not found", never hangs (1–2s), installs nothing, and leaves no
  activation pointer or host registration behind.
- **Existing-state isolation** — the real installation already on this machine
  (`~/.agent-skills`, version `0.43.0`) was hashed before and after: manifest and active release
  identical. Every sandbox lived under a throwaway temp directory; none was cleaned up by touching
  real state, only its own.

### A macOS-specific finding, in the test harness only

The first run of the authenticated case failed — not because distribution access was actually
broken, but because the harness's own isolation was incomplete. `gh`'s token is commonly stored in
the macOS login Keychain, and Keychain Services resolves the *default keychain search list* through
`~/Library/Preferences`, keyed to `$HOME`. A throwaway sandbox `$HOME` (the isolation this suite
needs, so it never registers skills into the real host directories on this machine) has no matching
preference file, so `security`/`gh` silently saw no login keychain at all and reported "not
authenticated" — even though the developer plainly was, in every other respect.

Root-caused directly: `security list-keychains` under a real `$HOME` lists the login keychain;
under a substituted one, it lists only `System.keychain`, regardless of any other environment
variable (`GH_CONFIG_DIR`, `GIT_CONFIG_GLOBAL`) pointed at the real files. Confirmed independent of
`$HOME` entirely once `~/Library/Preferences` and `~/Library/Keychains` were reachable from the
sandbox (read-only symlinks, nothing under them ever written).

This is not a defect in the product: a real user's shell always has a `$HOME` that matches their own
Keychain, so `agent-skills install` run normally is unaffected, and `AGENT_SKILLS_HOME`/
`AGENT_SKILLS_CONFIG_DIR` (the paths a user can legitimately override, per `agent-skills dev
install --home`) were never involved. It was a gap in how the *test harness* simulated "a stranger
with the same git access, on a fresh machine" — fixed in `scripts/test-private-source.sh` by
grafting in exactly the two paths Keychain Services needs, nothing else. No product code changed.
Two overly strict assertions written alongside it were also corrected: a bare `ghp_` substring match
(which flagged the shipped source code that *documents* that prefix, not a leaked token — tightened
to the same token-shape regex every other check here uses) and a bare `fatal:` absence check (the
classified `AUTHENTICATION_REQUIRED` message is allowed to carry the raw git detail as trailing
supporting evidence; what must never happen — and does not — is a raw error appearing instead of,
or ahead of, the classification).


## Post-release verification

Run after `v0.43.0` was tagged and the GitHub release published, against the **real remote** rather
than a local fixture. This is the case the rest of the suite could not run before the tag existed.

```bash
npm install --prefix <sandbox> npm/wamala-agent-skills-0.43.0.tgz
<sandbox>/node_modules/.bin/agent-skills-bootstrap install
```

Clean `HOME` with a space in its path, no `AGENT_SKILLS_SOURCE`, no clone anywhere in the flow.

| Check | Result |
| --- | --- |
| install from the packed bootstrap against `github.com/wamalalawrence/agent-skills` | pass |
| resolved release | `0.43.0` (stable, via git) |
| payload verification and staged self-test | pass |
| host registration | pass |
| `agent-skills doctor` | pass — reports the git provider it came from, `install kind: release`, version coherence |
| `agent-skills verify` | pass |
| `agent-skills check-updates` | `up-to-date` |
| `agent-skills version` | `0.43.0` |

This closes the one Stage A gap the earlier run recorded: the git provider had been exercised
end to end only against a local bare remote, because no CLI-installable release had been tagged yet.

## Registry publication

`@wamalalawrence/agent-skills@0.43.0` is published publicly. `@wamala` was the first choice, but an
authenticated publish with two-factor authentication satisfied returned `404` on the `PUT` — npm's
way of reporting "you may not create a package in this scope". `npm view` and `npm org ls` had both
appeared to say otherwise; neither actually answers that question. See
[docs/release-providers.md](../../docs/release-providers.md#the-package-name).

The supported command, run against the public registry in a clean `HOME` with a space in its path
and no local checkout involved:

```bash
npx @wamalalawrence/agent-skills install
```

| Check | Result |
| --- | --- |
| published tarball shasum matches the audited one | `94b158f4…` — identical |
| `npx` resolves and installs from the registry | pass |
| release source recorded | git remote, not the npm package |
| skills installed | 9 |
| `agent-skills doctor` | pass — version coherence, Context Optimizer present |
| `agent-skills verify` | pass |
| `agent-skills check-updates` | `up-to-date` |
| `agent-skills version` | `0.43.0` |

## What this run does not prove

- **A second published version.** Only `0.43.0` exists on the registry, so `agent-skills update`
  was exercised against git tags and a local fixture remote, not against two published npm
  versions. That path is the same code either way — npm carries the bootstrap, not the payload.
- **Windows.** Tested on macOS. CI covers Linux. Windows is WSL or Git Bash, untested here.
- **Real host behaviour.** Registrations are asserted on the filesystem. Whether Cursor or Kiro
  then loads a skill is the host's business and is not observable from a test.
