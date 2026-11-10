#!/usr/bin/env node
"use strict";
/*
 * Release signing and verification tests.
 *
 * Everything here runs against real Ed25519 keys generated in the process and
 * destroyed with it. No private key is committed, written to the repository,
 * or printed — one test asserts the last of those about the signing script
 * itself, because a signing tool that echoes its key is the failure that
 * cannot be undone.
 *
 * The cases are the ones from the plan's test matrix: bad signature, wrong
 * key, unknown key ID, tampered archive, wrong version or platform, and the
 * two-key rotation. Each asserts a specific error code rather than "it threw",
 * because a verifier that rejects everything passes a suite that only checks
 * for failure.
 *
 * Run: node scripts/test-release-signing.js
 */

const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const REPO_ROOT = path.resolve(__dirname, "..");
const VERIFY_PATH = path.join(REPO_ROOT, "npm", "lib", "verify.js");
const BOOTSTRAP = path.join(REPO_ROOT, "npm", "bin", "agent-skills-bootstrap.js");
const SIGN_SCRIPT = path.join(REPO_ROOT, "scripts", "sign-release.js");
const SHIPPED_BUNDLE = path.join(REPO_ROOT, "npm", "lib", "trust-bundle.json");

const verify = require(VERIFY_PATH);
const CODES = verify.CODES;

const TESTS = [];
const PASSED = [];
const FAILED = [];

function check(name, fn) {
  TESTS.push({ name: name, fn: fn });
}

function box() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "as-signing-"));
}

/** Assert that `fn` fails with exactly this verification code. */
async function expectCode(code, fn) {
  let error = null;
  try {
    await fn();
  } catch (caught) {
    error = caught;
  }
  assert.ok(error, "expected " + code + ", nothing was thrown");
  assert.strictEqual(
    error.code,
    code,
    "expected " + code + ", got " + error.code + ": " + error.message
  );
  return error;
}

function newKey() {
  const pair = crypto.generateKeyPairSync("ed25519");
  const spki = pair.publicKey.export({ format: "der", type: "spki" });
  return {
    privateKey: pair.privateKey,
    publicKey: pair.publicKey,
    spki: spki,
    keyId: verify.deriveKeyId(spki),
    entry: function (state) {
      return {
        keyId: verify.deriveKeyId(spki),
        algorithm: "ed25519",
        state: state || "active",
        publicKey: spki.toString("base64"),
      };
    },
  };
}

function baseManifest(overrides) {
  const manifest = {
    manifestSchema: "agent-skills.manifest/v1",
    version: "2.0.0",
    channel: "stable",
    sourceCommit: "a".repeat(40),
    platform: "any",
    archiveSha256: "0".repeat(64),
    archiveBytes: 1,
    payloadTreeHash: "b".repeat(64),
    createdAt: "2026-09-12T09:00:00Z",
    minimumBootstrapVersion: "1.0.0",
    signingKeyId: "ed25519-" + "0".repeat(16),
  };
  return Object.assign(manifest, overrides || {});
}

/**
 * Write a complete, signed release into `dir`: an archive, a manifest whose
 * digest and size describe it, a detached signature, and a trust bundle.
 */
function makeRelease(dir, options) {
  options = options || {};
  const key = options.key || newKey();
  const archivePath = path.join(dir, "release.tar.gz");
  const content = Buffer.from(options.archive || "a release payload, near enough");
  fs.writeFileSync(archivePath, content);

  const manifest = baseManifest(
    Object.assign(
      {
        archiveSha256: crypto.createHash("sha256").update(content).digest("hex"),
        archiveBytes: content.length,
        signingKeyId: key.keyId,
      },
      options.manifest || {}
    )
  );
  const manifestBytes = verify.canonicalize(manifest);
  const signingKey = options.signWith || key;
  const signature = crypto.sign(null, options.signOver || manifestBytes, signingKey.privateKey);

  const manifestPath = path.join(dir, "manifest.json");
  const signaturePath = path.join(dir, "manifest.sig");
  const bundlePath = path.join(dir, "trust-bundle.json");
  fs.writeFileSync(manifestPath, manifestBytes);
  fs.writeFileSync(signaturePath, signature.toString("base64") + "\n");
  fs.writeFileSync(
    bundlePath,
    JSON.stringify({ schema: "agent-skills.trust-bundle/v1", keys: options.keys || [key.entry()] })
  );
  return {
    key: key,
    manifest: manifest,
    manifestBytes: manifestBytes,
    manifestPath: manifestPath,
    signaturePath: signaturePath,
    archivePath: archivePath,
    bundlePath: bundlePath,
    args: {
      manifestPath: manifestPath,
      signaturePath: signaturePath,
      archivePath: archivePath,
      trustBundle: bundlePath,
      bootstrapVersion: "1.0.0",
    },
  };
}

// ---------------------------------------------------------------------------
// Canonical serialisation
// ---------------------------------------------------------------------------

check("canonical: key order and whitespace do not depend on how the object was built", () => {
  const one = verify.canonicalize({ b: 1, a: { d: [1, 2], c: "x" } });
  const two = verify.canonicalize({ a: { c: "x", d: [1, 2] }, b: 1 });
  assert.strictEqual(one.toString("utf8"), '{"a":{"c":"x","d":[1,2]},"b":1}');
  assert.strictEqual(Buffer.compare(one, two), 0);
});

check("canonical: keys sort by UTF-8 bytes, not by UTF-16 code units", () => {
  // U+1D400 is above U+FFFD in code-point order but below it in UTF-16 order,
  // because its surrogate pair starts at 0xD835. A verifier in another
  // language sorts by code point; JavaScript's default sort does not.
  const astral = "\u{1D400}";
  const replacement = "\uFFFD";
  const out = verify.canonicalize({ [astral]: 1, [replacement]: 2 }).toString("utf8");
  assert.ok(out.indexOf(replacement) < out.indexOf(astral), out);
});

check("canonical: a float cannot be signed", () => {
  return expectCode(CODES.CANONICAL_NON_INTEGER_NUMBER, () =>
    verify.canonicalize({ archiveBytes: 1.5 })
  );
});

check("canonical: NaN and Infinity cannot be signed", async () => {
  await expectCode(CODES.CANONICAL_NON_INTEGER_NUMBER, () => verify.canonicalize({ a: NaN }));
  await expectCode(CODES.CANONICAL_NON_INTEGER_NUMBER, () =>
    verify.canonicalize({ a: Infinity })
  );
});

check("canonical: an integer outside the safe range cannot be signed", () => {
  return expectCode(CODES.CANONICAL_UNSAFE_INTEGER, () =>
    verify.canonicalize({ a: Number.MAX_SAFE_INTEGER + 2 })
  );
});

check("canonical: undefined, a function, and a class instance are refused", async () => {
  await expectCode(CODES.CANONICAL_UNSUPPORTED_TYPE, () => verify.canonicalize({ a: undefined }));
  await expectCode(CODES.CANONICAL_UNSUPPORTED_TYPE, () =>
    verify.canonicalize({ a: function () {} })
  );
  await expectCode(CODES.CANONICAL_UNSUPPORTED_TYPE, () =>
    verify.canonicalize({ a: new Date(0) })
  );
});

check("canonical: an unpaired surrogate has no UTF-8 encoding and is refused", () => {
  return expectCode(CODES.CANONICAL_LONE_SURROGATE, () =>
    verify.canonicalize({ a: "bad\uD800end" })
  );
});

check("canonical: a cycle is refused rather than recursed", () => {
  const value = { a: 1 };
  value.self = value;
  return expectCode(CODES.CANONICAL_CYCLE, () => verify.canonicalize(value));
});

check("canonical: the top level must be an object", async () => {
  await expectCode(CODES.CANONICAL_NOT_AN_OBJECT, () => verify.canonicalize([1, 2]));
  await expectCode(CODES.CANONICAL_NOT_AN_OBJECT, () => verify.canonicalize("manifest"));
});

check("manifest: a pretty-printed manifest is not the manifest that was signed", () => {
  const pretty = Buffer.from(JSON.stringify(baseManifest(), null, 2), "utf8");
  return expectCode(CODES.MANIFEST_NOT_CANONICAL, () => verify.parseManifestBytes(pretty));
});

check("manifest: a repeated key is reported, not silently resolved", () => {
  const bytes = Buffer.from('{"a":"one","b":{"c":1},"a":"two"}', "utf8");
  assert.strictEqual(verify.findDuplicateKey(bytes.toString("utf8")), "a");
  return expectCode(CODES.MANIFEST_DUPLICATE_KEY, () => verify.parseManifestBytes(bytes));
});

check("manifest: a string value that looks like a key is not mistaken for one", () => {
  assert.strictEqual(verify.findDuplicateKey('{"a":"a","b":["a","a"]}'), null);
});

check("manifest: bytes that are not JSON are reported as such", () => {
  return expectCode(CODES.MANIFEST_NOT_JSON, () => verify.parseManifestBytes(Buffer.from("{,")));
});

// ---------------------------------------------------------------------------
// Signature verification
// ---------------------------------------------------------------------------

check("signature: a correctly signed release verifies", async () => {
  const dir = box();
  const release = makeRelease(dir);
  const result = await verify.verifyRelease(release.args);
  assert.strictEqual(result.signingKeyId, release.key.keyId);
  assert.strictEqual(result.manifest.version, "2.0.0");
  assert.strictEqual(result.archiveSha256, release.manifest.archiveSha256);
});

check("signature: one changed byte in the manifest invalidates it", async () => {
  const dir = box();
  const release = makeRelease(dir);
  // Still canonical JSON, still a well-formed digest — only a different one.
  const tampered = release.manifestBytes
    .toString("utf8")
    .replace(release.manifest.payloadTreeHash, "c" + release.manifest.payloadTreeHash.slice(1));
  fs.writeFileSync(release.manifestPath, Buffer.from(tampered, "utf8"));
  await expectCode(CODES.SIGNATURE_INVALID, () => verify.verifyRelease(release.args));
});

check("signature: a signature made over a different manifest does not transfer", async () => {
  const dir = box();
  const key = newKey();
  const other = verify.canonicalize(baseManifest({ version: "2.0.1", signingKeyId: key.keyId }));
  const release = makeRelease(dir, { key: key, signOver: other });
  await expectCode(CODES.SIGNATURE_INVALID, () => verify.verifyRelease(release.args));
});

check("signature: a signature from a key the bundle does not hold is refused", async () => {
  const dir = box();
  const trusted = newKey();
  const attacker = newKey();
  // The manifest names the trusted key; the signature is the attacker's.
  const release = makeRelease(dir, { key: trusted, signWith: attacker });
  await expectCode(CODES.SIGNATURE_INVALID, () => verify.verifyRelease(release.args));
});

check("signature: an unknown signingKeyId is refused before any key is tried", async () => {
  const dir = box();
  const key = newKey();
  const stranger = newKey();
  const release = makeRelease(dir, {
    key: key,
    manifest: { signingKeyId: stranger.keyId },
    signWith: stranger,
  });
  await expectCode(CODES.SIGNING_KEY_UNKNOWN, () => verify.verifyRelease(release.args));
});

check("signature: an algorithm that is not Ed25519 is refused", async () => {
  const dir = box();
  const release = makeRelease(dir, { manifest: { signatureAlgorithm: "rsa-pss-sha256" } });
  await expectCode(CODES.SIGNATURE_ALGORITHM_UNSUPPORTED, () =>
    verify.verifyRelease(release.args)
  );
});

check("signature: a trust bundle entry naming another algorithm is refused", async () => {
  const key = newKey();
  const entry = key.entry();
  entry.algorithm = "ed448";
  await expectCode(CODES.SIGNATURE_ALGORITHM_UNSUPPORTED, () =>
    verify.loadTrustBundle({ keys: [entry] })
  );
});

check("signature: an RSA key wearing an Ed25519 label is refused", async () => {
  const pair = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
  const spki = pair.publicKey.export({ format: "der", type: "spki" });
  await expectCode(CODES.TRUST_KEY_MALFORMED, () =>
    verify.loadTrustBundle({
      keys: [
        {
          keyId: verify.deriveKeyId(spki),
          algorithm: "ed25519",
          state: "active",
          publicKey: spki.toString("base64"),
        },
      ],
    })
  );
});

check("signature: a malformed or truncated signature is not a verification attempt", async () => {
  const dir = box();
  const release = makeRelease(dir);
  fs.writeFileSync(release.signaturePath, "this is not base64 !!\n");
  await expectCode(CODES.SIGNATURE_MALFORMED, () => verify.verifyRelease(release.args));

  const good = crypto.sign(null, release.manifestBytes, release.key.privateKey);
  fs.writeFileSync(release.signaturePath, good.subarray(0, 63).toString("base64") + "\n");
  await expectCode(CODES.SIGNATURE_MALFORMED, () => verify.verifyRelease(release.args));
});

check("signature: an unreadable signature file is its own failure", async () => {
  const dir = box();
  const release = makeRelease(dir);
  fs.unlinkSync(release.signaturePath);
  await expectCode(CODES.SIGNATURE_UNREADABLE, () => verify.verifyRelease(release.args));
});

check("signature: the signature is checked before the manifest's own fields", async () => {
  const dir = box();
  const key = newKey();
  // Wrong version *and* a signature from a key nobody trusts. The signature
  // failure is the one that matters, and it is the one reported.
  const release = makeRelease(dir, { key: key, signWith: newKey() });
  const error = await expectCode(CODES.SIGNATURE_INVALID, () =>
    verify.verifyRelease(Object.assign({ expect: { version: "9.9.9" } }, release.args))
  );
  assert.ok(error.message.indexOf(key.keyId) !== -1);
});

// ---------------------------------------------------------------------------
// The trust bundle
// ---------------------------------------------------------------------------

check("bundle: a key ID that does not describe its own key material is refused", async () => {
  const key = newKey();
  const entry = key.entry();
  entry.keyId = "ed25519-" + "1".repeat(16);
  await expectCode(CODES.TRUST_KEY_ID_MISMATCH, () => verify.loadTrustBundle({ keys: [entry] }));
});

check("bundle: an empty bundle verifies nothing", async () => {
  await expectCode(CODES.TRUST_BUNDLE_EMPTY, () => verify.loadTrustBundle({ keys: [] }));
  await expectCode(CODES.TRUST_BUNDLE_MALFORMED, () => verify.loadTrustBundle({}));
  await expectCode(CODES.TRUST_BUNDLE_UNREADABLE, () =>
    verify.loadTrustBundle(path.join(os.tmpdir(), "as-signing-absent-bundle.json"))
  );
});

check("bundle: the same key ID twice is a malformed bundle", async () => {
  const key = newKey();
  await expectCode(CODES.TRUST_BUNDLE_DUPLICATE_KEY_ID, () =>
    verify.loadTrustBundle({ keys: [key.entry(), key.entry("retiring")] })
  );
});

check("bundle: rotation — the retiring key still verifies, the new key verifies", async () => {
  const outgoing = newKey();
  const incoming = newKey();
  const stranger = newKey();
  const keys = [outgoing.entry("retiring"), incoming.entry("active")];

  const oldDir = box();
  const oldRelease = makeRelease(oldDir, { key: outgoing, keys: keys });
  assert.strictEqual((await verify.verifyRelease(oldRelease.args)).signingKeyId, outgoing.keyId);

  const newDir = box();
  const newRelease = makeRelease(newDir, { key: incoming, keys: keys });
  assert.strictEqual((await verify.verifyRelease(newRelease.args)).signingKeyId, incoming.keyId);

  const thirdDir = box();
  const third = makeRelease(thirdDir, { key: stranger, keys: keys });
  await expectCode(CODES.SIGNING_KEY_UNKNOWN, () => verify.verifyRelease(third.args));
});

check("bundle: a reserved slot holds a place, it does not confer trust", async () => {
  const dir = box();
  const key = newKey();
  const release = makeRelease(dir, { key: key, keys: [key.entry("reserved")] });
  await expectCode(CODES.SIGNING_KEY_NOT_ACCEPTED, () => verify.verifyRelease(release.args));
});

check("bundle: the shipped bundle is well formed, holds two slots, and is not yet live", async () => {
  const trusted = verify.loadTrustBundle(SHIPPED_BUNDLE);
  assert.strictEqual(trusted.size, 2, "the rotation window needs exactly two slots");
  for (const entry of trusted.values()) {
    assert.strictEqual(entry.state, "reserved", entry.keyId + " claims to be live");
  }
  const raw = JSON.parse(fs.readFileSync(SHIPPED_BUNDLE, "utf8"));
  assert.ok(!/PRIVATE KEY/.test(fs.readFileSync(SHIPPED_BUNDLE, "utf8")));
  for (const entry of raw.keys) {
    const der = Buffer.from(entry.publicKey, "base64");
    assert.strictEqual(verify.deriveKeyId(der), entry.keyId);
  }
});

// ---------------------------------------------------------------------------
// The archive
// ---------------------------------------------------------------------------

check("archive: a changed byte in the archive is caught by the digest", async () => {
  const dir = box();
  const release = makeRelease(dir);
  const content = fs.readFileSync(release.archivePath);
  content[0] = content[0] ^ 0xff;
  fs.writeFileSync(release.archivePath, content);
  await expectCode(CODES.ARCHIVE_DIGEST_MISMATCH, () => verify.verifyRelease(release.args));
});

check("archive: a different length fails before anything is hashed", async () => {
  const dir = box();
  const release = makeRelease(dir);
  fs.appendFileSync(release.archivePath, "x");
  await expectCode(CODES.ARCHIVE_SIZE_MISMATCH, () => verify.verifyRelease(release.args));
});

check("archive: a missing archive is not a verification pass", async () => {
  const dir = box();
  const release = makeRelease(dir);
  fs.unlinkSync(release.archivePath);
  await expectCode(CODES.ARCHIVE_UNREADABLE, () => verify.verifyRelease(release.args));
});

check("archive: a signed manifest cannot authorise an unbounded download", async () => {
  const dir = box();
  const release = makeRelease(dir);
  await expectCode(CODES.ARCHIVE_TOO_LARGE, () =>
    verify.verifyRelease(Object.assign({ maxArchiveBytes: 4 }, release.args))
  );
});

// ---------------------------------------------------------------------------
// Manifest fields and what the caller asked for
// ---------------------------------------------------------------------------

check("manifest: the wrong version is refused even when the signature is good", async () => {
  const dir = box();
  const release = makeRelease(dir);
  await expectCode(CODES.MANIFEST_VERSION_MISMATCH, () =>
    verify.verifyRelease(Object.assign({ expect: { version: "2.0.1" } }, release.args))
  );
});

check("manifest: the wrong platform and the wrong channel are refused", async () => {
  const dir = box();
  const release = makeRelease(dir);
  await expectCode(CODES.MANIFEST_PLATFORM_MISMATCH, () =>
    verify.verifyRelease(Object.assign({ expect: { platform: "darwin-arm64" } }, release.args))
  );
  await expectCode(CODES.MANIFEST_CHANNEL_MISMATCH, () =>
    verify.verifyRelease(Object.assign({ expect: { channel: "rc" } }, release.args))
  );
});

check("manifest: every required field is required", async () => {
  const required = [
    "manifestSchema",
    "version",
    "channel",
    "sourceCommit",
    "platform",
    "archiveSha256",
    "archiveBytes",
    "payloadTreeHash",
    "createdAt",
    "minimumBootstrapVersion",
    "signingKeyId",
  ];
  for (const field of required) {
    const manifest = baseManifest();
    delete manifest[field];
    const error = await expectCode(CODES.MANIFEST_FIELD_MISSING, () =>
      verify.validateManifest(manifest, {})
    );
    assert.strictEqual(error.detail.field, field);
  }
});

check("manifest: a field of the wrong shape is refused", async () => {
  await expectCode(CODES.MANIFEST_FIELD_TYPE, () =>
    verify.validateManifest(baseManifest({ archiveBytes: "12" }), {})
  );
  await expectCode(CODES.MANIFEST_FIELD_FORMAT, () =>
    verify.validateManifest(baseManifest({ archiveSha256: "NOTAHASH" }), {})
  );
  await expectCode(CODES.MANIFEST_FIELD_FORMAT, () =>
    verify.validateManifest(baseManifest({ archiveBytes: 0 }), {})
  );
  await expectCode(CODES.MANIFEST_FIELD_FORMAT, () =>
    verify.validateManifest(baseManifest({ channel: "nightly" }), {})
  );
  await expectCode(CODES.MANIFEST_FIELD_FORMAT, () =>
    verify.validateManifest(baseManifest({ createdAt: "yesterday" }), {})
  );
  await expectCode(CODES.MANIFEST_FIELD_FORMAT, () =>
    verify.validateManifest(baseManifest({ platform: "../../etc" }), {})
  );
});

check("manifest: a schema this bootstrap does not know is refused", () => {
  return expectCode(CODES.MANIFEST_SCHEMA_UNSUPPORTED, () =>
    verify.validateManifest(baseManifest({ manifestSchema: "agent-skills.manifest/v2" }), {})
  );
});

check("manifest: a bootstrap below the release's minimum is told so", async () => {
  const manifest = baseManifest({ minimumBootstrapVersion: "2.1.0" });
  await expectCode(CODES.MANIFEST_BOOTSTRAP_TOO_OLD, () =>
    verify.validateManifest(manifest, { bootstrapVersion: "2.0.0" })
  );
  verify.validateManifest(manifest, { bootstrapVersion: "2.1.0" });
  verify.validateManifest(manifest, { bootstrapVersion: "2.2.0" });
  // A pre-release is below the release of the same number.
  await expectCode(CODES.MANIFEST_BOOTSTRAP_TOO_OLD, () =>
    verify.validateManifest(manifest, { bootstrapVersion: "2.1.0-rc.1" })
  );
});

// ---------------------------------------------------------------------------
// The signing script
// ---------------------------------------------------------------------------

function runSigner(args, env) {
  return spawnSync(process.execPath, [SIGN_SCRIPT].concat(args), {
    env: Object.assign({}, process.env, env || {}),
    encoding: "utf8",
  });
}

check("signing: the script signs a manifest that then verifies end to end", async () => {
  const dir = box();
  const key = newKey();
  const pem = key.privateKey.export({ format: "pem", type: "pkcs8" });
  const archivePath = path.join(dir, "release.tar.gz");
  fs.writeFileSync(archivePath, "payload bytes");
  const bundlePath = path.join(dir, "trust-bundle.json");
  fs.writeFileSync(bundlePath, JSON.stringify({ keys: [key.entry("active")] }));

  const input = baseManifest();
  delete input.signingKeyId;
  delete input.archiveSha256;
  delete input.archiveBytes;
  const inputPath = path.join(dir, "manifest.input.json");
  fs.writeFileSync(inputPath, JSON.stringify(input, null, 2));

  const outDir = path.join(dir, "out");
  const run = runSigner(
    [
      "sign",
      "--manifest",
      inputPath,
      "--archive",
      archivePath,
      "--out-dir",
      outDir,
      "--trust-bundle",
      bundlePath,
    ],
    { AGENT_SKILLS_SIGNING_KEY: pem }
  );
  assert.strictEqual(run.status, 0, run.stderr);

  const result = await verify.verifyRelease({
    manifestPath: path.join(outDir, "manifest.json"),
    signaturePath: path.join(outDir, "manifest.sig"),
    archivePath: archivePath,
    trustBundle: bundlePath,
    bootstrapVersion: "1.0.0",
  });
  assert.strictEqual(result.signingKeyId, key.keyId);
  assert.strictEqual(result.manifest.archiveBytes, 13);

  // The key reached the script through the environment and left no trace of
  // itself in the output, in the emitted files, or in the output directory.
  const secret = key.privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
  const emitted = fs.readdirSync(outDir).map((name) => fs.readFileSync(path.join(outDir, name)));
  for (const text of [run.stdout, run.stderr].concat(emitted.map((b) => b.toString("utf8")))) {
    assert.ok(text.indexOf(secret) === -1, "private key material was written out");
    assert.ok(text.indexOf("PRIVATE KEY") === -1, "private key material was written out");
  }
});

check("signing: no key in the environment means no signature", () => {
  const dir = box();
  const inputPath = path.join(dir, "manifest.input.json");
  fs.writeFileSync(inputPath, JSON.stringify(baseManifest()));
  const run = runSigner(["sign", "--manifest", inputPath, "--out-dir", path.join(dir, "out")], {
    AGENT_SKILLS_SIGNING_KEY: "",
  });
  assert.strictEqual(run.status, 2);
  assert.ok(/AGENT_SKILLS_SIGNING_KEY is not set/.test(run.stderr), run.stderr);
  assert.ok(!fs.existsSync(path.join(dir, "out", "manifest.sig")));
});

check("signing: a key the shipped bundle does not list as active cannot sign", () => {
  const dir = box();
  const key = newKey();
  const inputPath = path.join(dir, "manifest.input.json");
  fs.writeFileSync(inputPath, JSON.stringify(baseManifest()));
  const run = runSigner(
    ["sign", "--manifest", inputPath, "--out-dir", path.join(dir, "out")],
    { AGENT_SKILLS_SIGNING_KEY: key.privateKey.export({ format: "pem", type: "pkcs8" }) }
  );
  assert.strictEqual(run.status, 2);
  assert.ok(/is not in/.test(run.stderr), run.stderr);
});

check("signing: a manifest that would not validate is never signed", () => {
  const dir = box();
  const key = newKey();
  const bundlePath = path.join(dir, "trust-bundle.json");
  fs.writeFileSync(bundlePath, JSON.stringify({ keys: [key.entry("active")] }));
  const inputPath = path.join(dir, "manifest.input.json");
  const input = baseManifest({ channel: "nightly" });
  delete input.signingKeyId;
  fs.writeFileSync(inputPath, JSON.stringify(input));
  const run = runSigner(
    [
      "sign",
      "--manifest",
      inputPath,
      "--out-dir",
      path.join(dir, "out"),
      "--trust-bundle",
      bundlePath,
    ],
    { AGENT_SKILLS_SIGNING_KEY: key.privateKey.export({ format: "pem", type: "pkcs8" }) }
  );
  assert.strictEqual(run.status, 2);
  assert.ok(/not signable/.test(run.stderr), run.stderr);
});

check("signing: a non-Ed25519 key in the environment is refused", () => {
  const dir = box();
  const pair = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
  const inputPath = path.join(dir, "manifest.input.json");
  fs.writeFileSync(inputPath, JSON.stringify(baseManifest()));
  const run = runSigner(["sign", "--manifest", inputPath, "--out-dir", path.join(dir, "out")], {
    AGENT_SKILLS_SIGNING_KEY: pair.privateKey.export({ format: "pem", type: "pkcs8" }),
  });
  assert.strictEqual(run.status, 2);
  assert.ok(/Ed25519/.test(run.stderr), run.stderr);
});

// ---------------------------------------------------------------------------
// The bootstrap entry point
// ---------------------------------------------------------------------------

function runBootstrap(args) {
  return spawnSync(process.execPath, [BOOTSTRAP].concat(args), { encoding: "utf8" });
}

check("bootstrap: verify-release reports a good release and exits 0", () => {
  const dir = box();
  const release = makeRelease(dir);
  const run = runBootstrap([
    "verify-release",
    "--manifest",
    release.manifestPath,
    "--signature",
    release.signaturePath,
    "--archive",
    release.archivePath,
    "--trust-bundle",
    release.bundlePath,
  ]);
  assert.strictEqual(run.status, 0, run.stderr);
  assert.ok(run.stdout.indexOf("verified 2.0.0") === 0, run.stdout);
  assert.ok(run.stdout.indexOf(release.key.keyId) !== -1, run.stdout);
});

check("bootstrap: a tampered release exits 5 with the failing code named", () => {
  const dir = box();
  const release = makeRelease(dir);
  fs.appendFileSync(release.archivePath, "x");
  const run = runBootstrap([
    "verify-release",
    "--manifest",
    release.manifestPath,
    "--signature",
    release.signaturePath,
    "--archive",
    release.archivePath,
    "--trust-bundle",
    release.bundlePath,
  ]);
  assert.strictEqual(run.status, 5, run.stdout + run.stderr);
  assert.ok(/INTEGRITY: ARCHIVE_SIZE_MISMATCH/.test(run.stderr), run.stderr);
});

check("bootstrap: verify-release without its arguments is a usage error", () => {
  const run = runBootstrap(["verify-release", "--manifest", "m.json"]);
  assert.strictEqual(run.status, 2);
  assert.ok(/--signature/.test(run.stderr), run.stderr);
});

check("bootstrap: the unsigned install path is untouched", () => {
  // Signing is additive. The bootstrap still forwards every command it forwarded
  // before, and still refuses the ones it refused.
  const help = runBootstrap(["--help"]);
  assert.strictEqual(help.status, 0);
  assert.ok(/verify-release/.test(help.stdout));
  const refused = runBootstrap(["doctor"]);
  assert.strictEqual(refused.status, 2);
  assert.ok(/the bootstrap only runs/.test(refused.stderr), refused.stderr);
});

// ---------------------------------------------------------------------------

async function main() {
  for (const test of TESTS) {
    try {
      await test.fn();
      PASSED.push(test.name);
    } catch (error) {
      FAILED.push([test.name, error && error.stack ? error.stack : String(error)]);
    }
  }
  for (const name of PASSED) {
    process.stdout.write("  ok    " + name + "\n");
  }
  for (const [name, detail] of FAILED) {
    process.stdout.write("  FAIL  " + name + "\n" + detail + "\n");
  }
  process.stdout.write("\n" + PASSED.length + " passed, " + FAILED.length + " failed\n");
  process.exit(FAILED.length ? 1 : 0);
}

main();
