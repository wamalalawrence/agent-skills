# Security review — v1.0.0-rc.3 (release-candidate certification)

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

This candidate changes one thing, and it is a thing a security review has to look at closely: how
the installer decides *which release to install* when the caller did not say. That decision now
reads a file on disk. A file that influences what code gets installed is, by definition, part of
the supply chain.

## Scope of this review

`v1.0.0-rc.3` changes: `resolve_channel` in `scripts/install.py` (now consults the install
manifest); a new `recorded_channel` helper there; `FOLLOWABLE_CHANNELS` in
`lib/asrelease/release.py`; a `follow_channel` field written by
`lib/asrelease/transaction.py`; the `check-updates` `--channel` default and `apply:` hint; a
`requested_channel` field in `check-updates --json`; `follow_channel` surfaced by
`agent-skills provider` and `agent-skills doctor`; and the corresponding documentation.

No change to the release provider, tag resolution, the archive-safety or integrity checks, the
payload self-test, the activation sequence, the downgrade guard, the Access Resolver, the
Execution Guard, the credential model, or the installation layout. The threat model is the union
of the prior reviews plus the surface below.

## Threat: the manifest widens a machine's channel and delivers a pre-release

**Probed.** `scripts/test-cli-install.sh` section 15 — 28 assertions, one mutation probe.

The frozen contract says `stable` never offers a pre-release. Resolution now reads
`install.json` to decide the channel when `--channel` is absent, so the question is whether a
manifest can cause a candidate to reach a machine that never asked for one.

It cannot, for two reasons that are separately asserted:

- **The set is closed.** `recorded_channel` accepts a value only if it is in
  `FOLLOWABLE_CHANNELS` — `stable`, `rc`, `any`. Everything else is ignored and resolution falls
  through to `stable`. A manifest holding `"../../etc"`, `"nonsense"`, a number, a list, or
  nothing at all resolves to `stable`. Fail closed is the default path, not an error path.
- **The only widening it can do is one the machine already chose.** `follow_channel` is written
  by the transaction from the channel the invocation requested, which reaches it only from an
  explicit `--channel` or `--dev`. A machine that has never passed either has `stable` recorded
  and stays there.

Asserted in both directions: an rc machine is offered candidates, and a stable machine is
offered none and has none named in its output.

**Trust boundary.** `install.json` lives in the install root (`~/.agent-skills`, mode `0644`,
owned by the user) and is written only by this engine. An attacker who can write it can already
replace the launcher, the activation symlink, and the payload itself — the manifest is the least
of what they control. This change does not extend the trust placed in the install root; it reads
one more field from a file the engine already reads for `version`, `current`, and the provider
it installs from.

**What it does not touch.** The channel gate itself is in the provider
(`lib/asrelease/providers/git.py:resolve_latest`), unchanged. `channel_of` still decides what a
version is, so a pre-release cannot be reclassified as stable by anything in this change.

## Threat: the change weakens the downgrade guard

**Reasoned about**, with the guard itself unchanged.

`_guard_downgrade` in `lib/asrelease/transaction.py` is untouched, and still refuses to replace
an active release with an older one unless `--allow-downgrade` is passed.

The change strictly *reduces* exposure here. Before it, a bare `update` on an rc machine resolved
`stable`, which on a machine running `1.0.0-rc.2` meant resolving `0.44.0` — an older release —
and the guard's hint told the user to pass `--allow-downgrade`. Following that advice would have
moved an RC tester backwards onto a release whose successor they were testing. That is not an
attack, but it is the shape of one: correct-looking tooling advising a downgrade. After the
change the bare `update` resolves the machine's own line and no downgrade is proposed.

The `apply:` hint is now asserted by executing it verbatim and checking it performs the update it
described, so the class of "the tool suggests a command that does something else" is closed for
this path rather than argued about.

## Threat: the superset rule is used to move a machine off its line

**Probed.** Same section — the `2.0.0` case.

`rc` is a superset, so an rc machine legitimately installs stable releases. Before this change
that act rewrote the recorded channel to `stable` and the machine never saw a candidate again.
That is a silent loss of an opt-in, and the reason it matters for security rather than only for
convenience is that an RC line is how a candidate gets tested before it becomes the release
everyone runs. A mechanism that quietly empties the RC population degrades the evidence behind
every subsequent stable release.

`follow_channel` is now separate from `channel`, and the test installs `2.0.0` onto an rc machine
and asserts the machine is still offered `2.0.1-rc.1` afterwards.

## Threat: a downgrade of the *field* — an old engine reading a new manifest

**Reasoned about.**

A `1.0.0-rc.2` engine reading a manifest containing `follow_channel` ignores it, which is the
pre-change behaviour: no crash, no misresolution beyond what that release already did. A
`1.0.0-rc.3` engine reading a pre-field manifest falls back to `channel`, which for those
installs was the requested channel in every case that could produce `rc` — asserted by a test
that strips the field and checks `rc` still resolves.

Rollback does not choose a channel, so it carries the recorded one forward rather than
inventing one; asserted.

## Threat: the new fields disclose something

**Reasoned about.** The added fields carry one of three literal strings — `stable`, `rc`, `any`.
They are not derived from user input, repository content, credentials, or the environment. No
secret, path, host, or identity is added to any output. The redaction rules in
[the secret boundary](secret-boundary.md) are unaffected.

## Residual risk

- **Unproven:** behaviour against the real private release source under an authenticated fetch
  is exercised by `scripts/test-private-source.sh`, not by section 15, which uses a local git
  fixture. The channel logic is provider-independent, but "the real remote, the real tags, the
  real auth" is proven by the other suite, not this one.
- **Accepted:** a user who deliberately edits `install.json` to `follow_channel: "rc"` opts
  themselves into candidates without passing a flag. This is equivalent to running
  `agent-skills update --channel rc`, which they can already do, and requires write access to
  their own install root.

## Verdict

No new externally reachable surface. One decision input added, sourced from a file already
trusted to name the active release, constrained to a closed set of three values, failing closed
to the narrowest one. The change removes a path on which the tool advised a downgrade, and
restores an opt-in the superset rule was silently discarding.

Certification results for this candidate are in
[`eval-runs/v1.0.0-rc.3/summary.md`](../eval-runs/v1.0.0-rc.3/summary.md).
