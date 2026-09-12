# Release signing and verification

How a release proves it is the one the publisher built, and what the installer refuses.

This is the mechanism for the private registry described in the
[commercial plan](commercial-roadmap.md), section 8. It is additive: an unsigned install from the
`git` or `local` provider behaves exactly as it did in `1.x`, and nothing here is on that path.

## Where verification happens, and why there

In **Node**, in the npm bootstrap, in [`npm/lib/verify.js`](../npm/lib/verify.js) — before the
Python install engine is started, and therefore before anything opens the archive.

That placement is the whole point. Verification has to happen upstream of the component that
treats the archive as structured input, because a tar parser is a parser and a parser is an attack
surface. Node is already running, already the first thing on the path, and has had native Ed25519
in `node:crypto` since Node 12; the package has declared `engines.node >= 18` since `1.0.0`. So
this adds **no dependency on either side**: no `cryptography`, no `PyNaCl`, no npm package. The
Python engine keeps doing its own SHA-256 and payload-tree verification afterwards; the two checks
are independent and both must pass.

## The canonical form

A signature is over bytes, not over an object, so "the manifest" has to mean exactly one byte
string. The rule:

- the top level is a JSON **object**, encoded **UTF-8**, with **no whitespace** outside strings;
- object keys are sorted ascending by their **UTF-8 byte sequence** — the order Python's `sorted()`
  and Go's `sort.Strings()` already produce, and the reason JavaScript's default string sort is not
  used: it compares UTF-16 code units and reorders astral characters;
- values may be objects, arrays, strings, `true`, `false`, `null`, and **integers** in the safe
  range;
- the manifest file on disk must be **byte-identical** to this encoding of the object it parses to.

Everything else is rejected rather than normalised: floating-point and out-of-range numbers,
`undefined`, functions, symbols, class instances, array holes, cycles, unpaired surrogates, and
duplicate keys. Two reasons, both narrow:

1. **Nothing that cannot round-trip can be signed.** No two languages agree on how to print a
   double, so a float in a signed manifest is a signature that verifies on the machine that made it
   and nowhere else. There is no floating-point quantity in a release manifest, so this costs
   nothing.
2. **The file a human reviews is the file that was signed.** Accepting a pretty-printed manifest
   and re-canonicalising it would create a gap between the bytes on disk and the bytes under the
   signature, and every such gap is somewhere to hide a second value. `JSON.parse` keeps the last
   of a repeated key and says nothing, so a duplicate key is exactly that gap; it is detected and
   named.

## What is signed

```json
{"archiveBytes":4096,"archiveSha256":"<64 hex>","channel":"stable","createdAt":"2026-09-12T09:00:00Z",
 "manifestSchema":"agent-skills.manifest/v1","minimumBootstrapVersion":"2.0.0","payloadTreeHash":"<64 hex>",
 "platform":"any","signingKeyId":"ed25519-<16 hex>","sourceCommit":"<40 hex>","version":"2.0.0"}
```

Every field is required and shape-checked: semantic versions, a 40-character commit, lowercase hex
digests, an RFC 3339 UTC timestamp, a channel of `stable` or `rc`, and a platform identifier that
cannot contain a path separator. `minimumBootstrapVersion` lets a release refuse an older bootstrap
rather than being half-understood by one. Unknown fields are allowed and are covered by the
signature, so a later release may add one without a new schema; a change to what an existing field
*means* is a new `manifestSchema`.

## Verification order

Fixed, and each step is skipped if an earlier one failed:

```text
parse the manifest bytes -> re-canonicalise and compare
                         -> verify the Ed25519 signature against the trust bundle
                         -> validate the fields, and what the caller asked for
                         -> check the archive's byte size, then stream its SHA-256
                         -> (Python) extract under bounds -> payload tree hash -> self-test
                         -> activate
```

The signature comes first because everything after it reads values out of the manifest, and a
value nobody signed is not evidence. The archive size is checked before the digest because it is a
`stat` call and a file of the wrong length cannot be the right file. The archive is **streamed**
through the hash rather than buffered.

## Error codes

Every failure is a distinct code, never a boolean, because "it did not verify" is not actionable:
an unknown key ID, an old bootstrap, and a tampered archive need three different answers. The
bootstrap prints the code and exits `5` (`integrity-failure`).

| Group | Codes |
| --- | --- |
| Canonical form | `CANONICAL_NOT_AN_OBJECT`, `CANONICAL_UNSUPPORTED_TYPE`, `CANONICAL_NON_INTEGER_NUMBER` |
| Canonical form | `CANONICAL_UNSAFE_INTEGER`, `CANONICAL_LONE_SURROGATE`, `CANONICAL_DEPTH_EXCEEDED`, `CANONICAL_CYCLE` |
| Manifest on the wire | `MANIFEST_UNREADABLE`, `MANIFEST_NOT_JSON`, `MANIFEST_DUPLICATE_KEY`, `MANIFEST_NOT_CANONICAL`, `MANIFEST_TOO_LARGE` |
| Manifest fields | `MANIFEST_FIELD_MISSING`, `MANIFEST_FIELD_TYPE`, `MANIFEST_FIELD_FORMAT`, `MANIFEST_SCHEMA_UNSUPPORTED`, `MANIFEST_BOOTSTRAP_TOO_OLD` |
| Wrong release | `MANIFEST_VERSION_MISMATCH`, `MANIFEST_CHANNEL_MISMATCH`, `MANIFEST_PLATFORM_MISMATCH` |
| Trust bundle | `TRUST_BUNDLE_UNREADABLE`, `TRUST_BUNDLE_MALFORMED`, `TRUST_BUNDLE_EMPTY`, `TRUST_BUNDLE_DUPLICATE_KEY_ID`, `TRUST_KEY_MALFORMED`, `TRUST_KEY_ID_MISMATCH` |
| Signature | `SIGNING_KEY_UNKNOWN`, `SIGNING_KEY_NOT_ACCEPTED`, `SIGNATURE_ALGORITHM_UNSUPPORTED`, `SIGNATURE_UNREADABLE`, `SIGNATURE_MALFORMED`, `SIGNATURE_INVALID` |
| Archive | `ARCHIVE_UNREADABLE`, `ARCHIVE_SIZE_MISMATCH`, `ARCHIVE_TOO_LARGE`, `ARCHIVE_DIGEST_MISMATCH` |

## The trust bundle

[`npm/lib/trust-bundle.json`](../npm/lib/trust-bundle.json) ships inside the npm package and holds
**two** slots:

```json
{ "keyId": "ed25519-<16 hex>", "algorithm": "ed25519", "state": "active", "publicKey": "<base64 SPKI>" }
```

A key ID is **derived** from the key — the first 16 hex characters of the SHA-256 of its SPKI DER —
and the bundle's declared ID is checked against that derivation. Swapping key material under a
trusted ID is therefore a detected edit, not a silent one.

`state` is what makes rotation a procedure rather than a flag day:

| State | Signs | Verifies |
| --- | --- | --- |
| `active` | yes | yes |
| `retiring` | no | yes — releases signed before the rotation keep installing |
| `reserved` | no | no — a published slot with no live key behind it |

### Rotation

1. Generate the successor key **inside the protected release environment**. Nothing leaves it but
   the public half: `AGENT_SKILLS_SIGNING_KEY=… node scripts/sign-release.js key-id` prints the
   entry to paste into the bundle.
2. Publish a bootstrap version carrying **both** keys: the current one `active`, the successor
   `reserved`.
3. **Wait for adoption.** Until a machine has that bootstrap, it cannot verify anything the new key
   signs. This is the step that cannot be hurried; it is why the bundle has two slots at all.
4. Flip the successor to `active` and the predecessor to `retiring`, publish that bootstrap, and
   start signing with the successor.
5. In the version after, drop the `retiring` entry and add a fresh `reserved` successor.

A compromised key skips the waiting: halt publication, move the compromised entry out of the
bundle entirely, publish a bootstrap, and re-sign. There is no unsigned fallback at any point.

> **Both slots ship `reserved` today.** The key material in them is a well-formed placeholder; the
> private halves were never written anywhere and do not exist. Verification therefore fails closed
> with `SIGNING_KEY_NOT_ACCEPTED` until the first signing ceremony generates a real key in the
> protected environment and replaces slot one. The mechanism, including the two-key window, is
> exercised end to end in the tests with keys generated per run.

## Signing

```bash
AGENT_SKILLS_SIGNING_KEY="$SIGNING_KEY" node scripts/sign-release.js sign \
  --manifest build/manifest.input.json \
  --archive  build/agent-skills-2.0.0.tar.gz \
  --out-dir  build/release
```

It emits `manifest.json` (the canonical bytes, no trailing newline) and `manifest.sig` (base64 of
the 64-byte signature). With `--archive` it fills in `archiveSha256` and `archiveBytes` itself, and
refuses if the manifest already claims different ones.

The key is read from `AGENT_SKILLS_SIGNING_KEY` and from nowhere else. There is deliberately no
`--key` and no key file: a command line is visible to every process through `ps`, is echoed by
`set -x`, and lands in shell history, while a key file is a key at rest with a mode, an owner and a
backup nobody tracks. The key is never printed and never included in an error message — the script
reports "not a readable PKCS#8 private key" rather than quoting what it failed to read.

Two refusals are worth knowing about, and both fail closed:

- the key must be `active` **in the trust bundle** before it may sign, so a release cannot be
  signed with a key no installed bootstrap has heard of;
- the manifest is validated before it is signed, and the signature is checked against the public
  half before it is written.

## Extraction bounds

Signature and digest say the archive is the publisher's. They say nothing about whether unpacking
it is survivable, so [`lib/asrelease/archive.py`](../lib/asrelease/archive.py) bounds it as well.

Already enforced since `v0.43.0`: absolute paths, `..` components, any member resolving outside the
root, symlinks and hardlinks escaping the root, device nodes and FIFOs, and setuid/setgid bits —
all checked in a first pass that writes nothing, so a rejected archive cannot half-extract.

Added here:

| Bound | Default | Why |
| --- | --- | --- |
| Archive size | 512 MiB | Checked before the file is opened |
| Expanded size | 1 GiB | Measured by decompressing in bounded chunks and abandoning the stream at the bound, so measuring a bomb costs the bound and not the bomb |
| Compression ratio | 200x | Prose and source compress five or ten to one; nothing legitimate reaches this |
| File count | 20000 | |
| Path length / name component | 1024 / 255 | |
| Duplicate paths | rejected | The archive that was reviewed and the archive that is written must be the same |
| Case-colliding paths | rejected | On macOS and Windows the second write replaces the first; rejecting everywhere means one release, one tree, every platform |

The payload is a few megabytes of text, so every bound has at least two orders of magnitude of
headroom. Any failure leaves the previous installation and its host registrations exactly as they
were: nothing before `ACTIVATE` touches the machine.

## Tests

```bash
node scripts/test-release-signing.js      # signing, verification, rotation, the bootstrap gate
python3 scripts/test-release-engine.py    # archive safety and extraction bounds
```

Both run in CI on every pull request. Keys are generated per run and destroyed with the process:
no private key is committed, written into a fixture, or printed, and one test asserts the last of
those about the signing script itself.

## See also

- [Release providers](release-providers.md) - the seam a signed registry provider plugs into.
- [Commercial plan](commercial-roadmap.md) - section 8, the private registry.
- [Versioning and exit codes](versioning.md) - what exit `5` means.
- [The 1.0 contract](one-point-oh.md) - what signing may not change.
