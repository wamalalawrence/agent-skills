# Security review — v0.43.0 (CLI installation and distribution)

This release distributes executable developer tooling. The thing being installed runs with the
user's privileges, edits configuration that decides what their agent may do, and — from this release
on — is fetched over a network rather than read out of a repository the user cloned themselves and
could inspect.

That is a materially larger trust surface than v0.42.0 had, and this document is the threat-by-threat
account of it. Every claim is labelled **probed**, **reasoned**, or **unproven**. An unlabelled claim
reads as evidence when it is not, which is the failure mode
[the v0.37.0 review](security-review-v0.37.0.md) was written to stop repeating.

## Scope

In scope: how a release is resolved, fetched, verified, staged, activated, and rolled back; what the
installer writes and where; how distribution credentials are obtained and handled; what a published
npm package contains.

Out of scope, and covered elsewhere: what an agent is permitted to do at runtime
([Execution Guard](execution-guard.md), [destructive-action safety](destructive-action-safety.md)),
and how project credentials are resolved ([access resolution](access-resolution.md)).

## Threat table

| No. | Threat | Control | Status |
| --- | --- | --- | --- |
| 1 | Malicious release payload | Tree hash in `release.json`, verified after staging and before activation; four-way version agreement | **probed** |
| 2 | Archive path traversal | Explicit member validation; nothing written until every member passes | **probed** |
| 3 | Symlink escape from an archive | Link targets resolved against the extraction root and rejected if outside | **probed** |
| 4 | Compromised npm bootstrap | Bootstrap carries no product and no credentials; content audit in CI; no lifecycle scripts | **partially probed** |
| 5 | Compromised or moved git tag | Tag object compared against the delivered commit | **reasoned** |
| 6 | Command injection through a version or path | No shell interpolation anywhere in the engine | **probed** |
| 7 | Hostile cwd or project config influencing a global install | Providers by name only; `GIT_CEILING_DIRECTORIES` set | **probed** |
| 8 | Downgrade attack | `update` refuses an older release; `rollback` is explicit | **probed** |
| 9 | Credentials in installer logs | Redaction of every git message; synthetic token asserted absent | **probed** |
| 10 | Authentication confusion (distribution vs. project) | Separate mechanisms, separate storage, separate documentation | **reasoned** |
| 11 | Malicious npm lifecycle behaviour | No lifecycle scripts; asserted by the audit | **probed** |
| 12 | Partial install corruption | Staged transaction; automatic rollback after activation | **probed** |
| 13 | Security-hook downgrade | Hooks resolve through `current`; reconciled on every activation | **probed** |
| 14 | PATH hijacking | Launcher linked, never a shell rc file edited; npm bin name is distinct | **reasoned** |
| 15 | Update replacing a newer release with an older one | Same control as #8 | **probed** |
| 16 | Installer destroying user state | Ownership predicates; `--purge` gated | **probed** |
| 17 | Private source leaking through a public package | Package content audit; payload never enters the package | **probed** |

## 1. Malicious release payload — probed

Every release carries `release.json` with `tree_sha256`, a hash over each payload file's relative
path, executable bit, and content. `verify_payload` recomputes it after staging and before anything
points at the payload, and additionally requires that four things agree: the version requested, the
tag the provider resolved, the payload's own `VERSION`, and the manifest.

Probed by `test-release-engine.py`: an intact payload verifies; a payload tampered with *after* its
manifest was written is refused with exit `5`; a payload whose `VERSION` disagrees with its manifest
is refused; a payload that is not the release that was asked for is refused.

Probed end to end by `test-cli-install.sh` case 4: a tampered release is refused mid-update, exit
`5`, and the previously installed release is still the active one afterwards.

**Residual risk.** The hash is carried with the payload, so it proves internal consistency and
detects corruption or an in-transit substitution of file content — not that the release was produced
by the maintainer. That needs signing. The manifest reserves a `signature` field so signed releases
add a field rather than a schema, and no custom cryptography is used or planned. Until then, the
trust anchor is the git remote and the credentials used to reach it.

## 2–3. Archive traversal and symlink escape — probed

Python's `TarFile.extractall` was an unguarded file-write primitive until 3.12, and the interpreters
this has to run on are precisely the ones that predate the fix. `safe_extract_tar` therefore
validates explicitly and rejects: absolute paths, drive-qualified paths, any `..` component before or
after normalisation, any member resolving outside the destination, symlinks and hardlinks whose
target leaves the root, anything that is not a regular file, directory, or in-root link, and any
setuid or setgid bit. Modes are normalised rather than preserved.

Validation happens in a first pass over every member. **Nothing is written until all of them pass**,
so a hostile archive cannot half-extract and leave a partial payload behind. That property is
asserted directly: the traversal probe builds an archive with one benign member followed by one
`../../` member and asserts the benign file was *not* written.

Probed: six hand-built hostile archives in `test-release-engine.py`, plus one well-formed archive
asserting that executable bits survive and non-executable files do not become executable.

## 4. Compromised npm bootstrap — partially probed

The bootstrap is 14 files and 28 KB. It contains a Node entry point, the installation engine, and the
release providers. It contains no skills, no docs, no runtime, and no credentials.

Probed: `audit-npm-package.sh` inspects the packed tarball — not the `files` list, because those two
disagree the moment a glob is wrong — and fails on product content, credential-shaped files,
repository internals, absolute developer home paths, secret-shaped strings, npm lifecycle scripts, a
package version that disagrees with `VERSION`, or a vendored engine that has drifted from
`lib/asrelease/`. It runs in CI on every change and is a required release gate.

**Unproven.** Nothing here defends against a compromise of the npm registry account itself, or
against a malicious version published under the same name. That is an account-security and
provenance problem — 2FA on the publishing account, and eventually npm provenance attestation — not
something the package's own contents can answer. It is recorded rather than solved.

## 5. Compromised or moved git tag — reasoned

`resolve_latest` reads tags with `git ls-remote --tags` and prefers the peeled `^{}` entry, which is
the commit an annotated tag points at. `fetch_release` clones that tag and compares the commit it
received against the one that was resolved; a mismatch is an integrity failure with the message "the
tag moved between resolution and download".

**Reasoned, not probed.** The window this closes is narrow — a tag moved between two commands seconds
apart — and constructing it in a test would be testing the fixture. What *is* probed is the adjacent
bug it introduced: the first implementation compared the annotated tag's own object id against the
commit and flagged every annotated release as moved. That is now handled explicitly and covered by
the git-remote install case.

**Residual risk.** Someone who can move tags on the remote can publish a malicious release under a
version number that was previously good. Nothing short of signing detects that, and the installer's
refusal to downgrade limits but does not remove it.

## 6. Command injection through a version or path — probed

No part of the engine builds a shell command from a string. Every subprocess is an argument list
(`subprocess.run(["git", ...])`, `["bash", launcher, "self-test"]`), so a version, path, or remote URL
containing shell metacharacters is data.

Probed indirectly and continuously: every case in `test-cli-install.sh` and the provider-independence
test run under a `HOME` whose path contains a space. A quoting regression fails there rather than on
a user's machine.

Version strings that reach the filesystem as directory names are constrained by
`normalise_version` and the semver regex, and an unparseable version compares as *equal* to any
other rather than as newer — so garbage cannot present itself as an upgrade.

## 7. Hostile cwd or project config influencing a global install — probed

Two paths were considered and closed.

**Provider selection.** Providers are registered in-process under fixed names and looked up in a
dictionary. There is deliberately no environment variable that names a module, no plugin directory,
and no config file that can introduce one. A repository the user has merely opened cannot point the
global installer at code, or at credentials, of its choosing. Probed: `build_provider("../../etc/evil")`
is a usage error, and the message names the known providers rather than attempting a load.

**git configuration.** git reads configuration from the current directory upwards, so a repository
could otherwise supply a credential helper, an `insteadOf` rewrite, or an `http.extraheader` to an
installer invoked from inside it. `GIT_CEILING_DIRECTORIES` is set to the user's home directory for
every git invocation the provider makes.

**Residual risk.** A hostile `~/.gitconfig` is still in scope, but that is the user's own global
configuration and is outside any boundary this installer can meaningfully defend.

## 8, 15. Downgrade — probed

`update` refuses to replace the active release with an older one, and says how to do it deliberately.
Going backwards is `rollback`, or an explicit `--allow-downgrade`.

This matters twice. It blocks the attack — a compromised remote serving an older release whose
vulnerabilities are published — and it removes a bad surprise, which is the reason it is a refusal
rather than a warning.

Probed: `test-cli-install.sh` case 6 asserts the refusal, its exit code, that the message names
`rollback`, that the newer release is still active afterwards, and that `--allow-downgrade` is
honoured.

## 9. Credentials in installer logs — probed

Every message from git passes through `redact()` before it is shown, logged, or embedded in an error:
credentials in a URL userinfo, GitHub token shapes (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`,
`github_pat_`), Slack tokens, and generic `token=`/`secret=`/`password=` assignments.

Probed at two levels. Directly: `redact()` is asserted to remove a token from a realistic git failure
message. Indirectly and more usefully: the acceptance suite injects a synthetic `GH_TOKEN` and
`GITHUB_TOKEN` into the environment of **every** invocation, then asserts that value appears in no
install log, no bootstrap log, and no authentication-failure output — and that no token-*shaped*
string appears either.

The `gh` askpass helper is the reason the second assertion can hold: the token is read by a temporary
shell script that execs `gh auth token`, so it never enters the installer's process, never becomes a
command-line argument visible to `ps`, and is never written to a file.

## 10. Authentication confusion — reasoned

Distribution access proves this machine may download the product. Project access reaches Jira, AWS, a
database. Conflating them would be the single worst outcome of this release, because it would
re-establish exactly what v0.37.0 removed: an installer that collects credentials.

They are kept separate structurally, not by convention. Distribution access is never read by Agent
Skills — git holds it. It is never written into `~/.config/agent-skills`. Installation requests no
credential of any kind, which the suite asserts by grepping every install log for credential
vocabulary and by asserting no credential store is created.

**Reasoned.** "These are different things" is a design property, and the probes above show the
installer does not collect or store anything. What cannot be probed is a user's mental model. The
mitigation is that the authentication-required message says so in words, and the suite asserts that
sentence is present.

## 11. Malicious npm lifecycle behaviour — probed

`npm/package.json` declares no `preinstall`, `install`, `postinstall`, `prepare`, or `prepublish`
script. `npm install` of the bootstrap runs nothing; installation happens only when a human types a
command. Probed by the package audit and again in CI.

This is why the bootstrap is a bootstrap rather than a package that installs on fetch. A lifecycle
script would run arbitrary code on `npm install` in every CI job that happened to depend on it.

## 12. Partial install corruption — probed

The transaction is the control. Everything before `ACTIVATE` happens in a staging directory;
`ACTIVATE` is a single `os.replace` of a symlink, so no observer sees `current` missing; anything
that fails after it triggers re-activation of the previous release and re-reconciliation of hosts.

Probed: a tampered payload (fails at VERIFY), a payload whose runtime cannot answer (fails at
SELF-TEST), and an incomplete payload (fails before ACTIVATE). In every case the previous release is
still active, `current` and its payload still agree, and staging is cleaned up. `verify` is asserted
green after two consecutive failed updates.

## 13. Security-hook downgrade — probed

Execution Guard hooks are registered against `~/.agent-skills/bin/agent-skills`, which resolves
through `current`. An update or rollback therefore moves the guard with the skills it protects, in
the same atomic step. There is no state in which enforcement is on one release and the skills on
another.

After every activation the installer runs `guard reconcile`, which re-asserts only registrations the
user already had, rewrites only entries carrying this project's signature, and does nothing on a
machine with no guard installation.

Probed: `test-cli-install.sh` case 9 installs the guard, updates, and asserts the hook resolves to
the *new* release; rolls back and asserts it resolves to the old one; uninstalls and asserts the
agent-skills hook is gone while the user's own hook in the same file survives.

## 14. PATH hijacking — reasoned

The installer links its launcher into the first writable candidate on `PATH` (`~/.local/bin`, then
`~/bin`) and **never edits a shell startup file**. A silent rc-file write is a surprise, and it is
also the mechanism by which an installer could persist something the user cannot see.

The npm package's binary is named `agent-skills-bootstrap`, not `agent-skills`, so a global
`npm install -g` cannot shadow the real launcher from npm's own bin directory.

**Residual risk.** If an attacker can already write to a directory earlier on the user's `PATH`, they
can shadow `agent-skills` — but they can equally shadow `git`, and the machine is already lost.
Recorded, not defended.

## 16. Installer destroying user state — probed

The ownership predicates from v0.37.0 are unchanged and remain the most safety-critical code in the
project: only symlinks whose target resolves inside the install root are ever created, replaced, or
removed; a real directory is never deleted; a link pointing elsewhere is never touched.

`uninstall` removes the installed releases, the activation pointer, the launcher link, owned host
registrations, and owned guard hook entries. It does not remove credential identities, project
bindings, per-project memory, a repository's knowledge base, unrelated skills, or unrelated hooks.
`--purge` removes credential metadata and is the only thing that does; secrets in an OS keychain are
never removed implicitly.

Probed: the uninstall case asserts each of those, positively and negatively. The migration case
asserts that upgrading a pre-CLI installation preserves credential identities and project bindings.

## 17. Private source leaking through a public package — probed

A private git repository does not make a published npm tarball private. The bootstrap therefore
carries no payload at all: the product is fetched from the release source at install time, so the
package cannot leak it regardless of who can read the repository.

Probed by the content audit, which is a required release gate and runs in CI.

## Findings raised during this review

1. **An error could be lost between buffered streams.** Progress is written to stdout, failures to
   stderr. With stdout redirected to a file it is block-buffered, so a failure could appear before
   the steps that led to it, or be missed by a reader tailing the log. Fixed: stdout is flushed
   before the failure is written. Found while debugging a test, not by the test.

2. **Annotated tags were reported as moved.** `git ls-remote --refs` returns the tag object's id, not
   the commit, so the tag-identity check flagged every annotated release. Fixed by preferring the
   peeled `^{}` entry. This was a real availability bug: it would have blocked every install.

3. **A failed install created an empty install root.** `ensure_dirs()` ran before the release was
   resolved, so a failed authentication left `~/.agent-skills/versions/` behind and made the machine
   look installed. Fixed: nothing is created on disk until a release has been resolved. Found by the
   acceptance suite asserting "nothing was installed".

4. **`uninstall` left Execution Guard hooks behind.** The guard has its own uninstall, and
   `agent-skills uninstall` did not call it, so removing Agent Skills left hooks pointing at a
   runtime that no longer existed. Fixed: uninstall removes owned guard entries first, while the
   release that owns them is still reachable. Found by the acceptance suite.

5. **A test fixture manufactured a false integrity failure.** Two fixture releases shared a scratch
   directory, so the second inherited the first's `release.json` and failed verification for a reason
   that had nothing to do with the property under test. Fixed in the fixture. Recorded because it is
   the exact shape of a probe that would have "passed" for the wrong reason.

## Residual risks, and the control offered for each

| Risk | Control | Why it is not the default |
| --- | --- | --- |
| Releases are not signed | `signature` reserved in the manifest; signed releases add a field, not a schema | Key management is a commitment; doing it badly is worse than not yet doing it |
| npm account compromise | 2FA on the publishing account; provenance attestation later | Outside what package contents can defend |
| A moved tag on the remote | Tag-vs-commit check; downgrade refusal | Full defence requires signing |
| A hostile `~/.gitconfig` | None | The user's own global configuration is inside the trust boundary |
| PATH shadowing by an existing local attacker | None | The machine is already compromised at that point |
| Windows | Not supported natively; WSL or Git Bash | Untested, and claiming support without testing is worse than declining it |

## What has not been proven

**Private-source installation.** The repository was public for the whole of this work. The
authentication-required path was probed against an unreadable remote, and the authenticated fetch
path against a local git remote, but installing from an authenticated **private GitHub** repository
has not been run. That is Stage B, it requires the repository visibility change first, and it is a
precondition for `1.0.0-rc.1` — not for this release.

**Registry publication.** Nothing was published. Installation was tested from the packed tarball,
which exercises the real package layout and the `files` list, but not a registry round trip.

## See also

- [Release providers and distribution](release-providers.md)
- [Installation](installation.md)
- [Execution Guard](execution-guard.md)
- [The v0.42.0 review](security-review-v0.42.0.md)
