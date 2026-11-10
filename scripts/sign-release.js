#!/usr/bin/env node
"use strict";
/*
 * Sign a release manifest with the Ed25519 release key.
 *
 * Run from the release workflow, on a protected environment, with the key in
 * the environment and nowhere else:
 *
 *   AGENT_SKILLS_SIGNING_KEY="$PRIVATE_KEY" node scripts/sign-release.js sign \
 *     --manifest build/manifest.input.json \
 *     --archive  build/agent-skills-1.2.3.tar.gz \
 *     --out-dir  build/release
 *
 * The key is read from `AGENT_SKILLS_SIGNING_KEY` and from nothing else. There
 * is deliberately no `--key`, no `--key-file`, and no default path:
 *
 *   * a command line is visible to every process on the host through `ps`, and
 *     is echoed by `set -x`, by CI log collectors, and by shell history;
 *   * a key file is a key at rest, with a mode, an owner, a backup, and a
 *     lifetime nobody tracks.
 *
 * The key is never printed, never included in an error message, and never
 * written anywhere. What this script emits is two files:
 *
 *   manifest.json   the canonical bytes that were signed, exactly
 *   manifest.sig    base64 of the 64-byte Ed25519 signature over them
 *
 * `manifest.json` has no trailing newline. That is not an oversight: the
 * verifier requires the file to be byte-identical to the canonical encoding of
 * the object it parses, so that the file a human reviews and the bytes the
 * signature covers cannot differ.
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..");
const verify = require(path.join(REPO_ROOT, "npm", "lib", "verify.js"));

const KEY_ENV = "AGENT_SKILLS_SIGNING_KEY";
const DEFAULT_BUNDLE = path.join(REPO_ROOT, "npm", "lib", "trust-bundle.json");

function die(message) {
  process.stderr.write("sign-release: " + message + "\n");
  process.exit(2);
}

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token.indexOf("--") !== 0) {
      die("unexpected argument " + token);
    }
    const name = token.slice(2);
    const value = argv[index + 1];
    if (value === undefined || value.indexOf("--") === 0) {
      die("--" + name + " needs a value");
    }
    options[name] = value;
    index += 1;
  }
  return options;
}

/**
 * Load the private key from the environment.
 *
 * Accepts a PKCS#8 PEM block or the base64 of the same key in DER, because a
 * CI secret store that mangles newlines is a real thing and re-encoding is
 * cheaper than debugging it at release time.
 */
function loadPrivateKey() {
  const raw = process.env[KEY_ENV];
  if (!raw || !raw.trim()) {
    die(KEY_ENV + " is not set; this is the only way this script accepts a key");
  }
  const value = raw.trim();
  let key;
  try {
    if (value.indexOf("-----BEGIN") === 0) {
      key = crypto.createPrivateKey({ key: value, format: "pem" });
    } else {
      key = crypto.createPrivateKey({
        key: Buffer.from(value, "base64"),
        format: "der",
        type: "pkcs8",
      });
    }
  } catch (error) {
    // Deliberately not `error.message`: it can quote the input it failed on.
    die(KEY_ENV + " is not a readable PKCS#8 private key");
  }
  if (key.asymmetricKeyType !== "ed25519") {
    die(KEY_ENV + " holds a " + key.asymmetricKeyType + " key; releases are signed with Ed25519");
  }
  const spki = crypto.createPublicKey(key).export({ format: "der", type: "spki" });
  return { key: key, spki: spki, keyId: verify.deriveKeyId(spki) };
}

function readJson(file, label) {
  let text;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch (error) {
    die("cannot read " + label + " at " + file);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    die(label + " at " + file + " is not valid JSON");
  }
}

function digestArchive(file) {
  let stat;
  try {
    stat = fs.statSync(file);
  } catch (error) {
    die("cannot read the archive at " + file);
  }
  const hash = crypto.createHash("sha256");
  const handle = fs.openSync(file, "r");
  const buffer = Buffer.alloc(1024 * 1024);
  try {
    for (;;) {
      const read = fs.readSync(handle, buffer, 0, buffer.length, null);
      if (read <= 0) {
        break;
      }
      hash.update(buffer.subarray(0, read));
    }
  } finally {
    fs.closeSync(handle);
  }
  return { sha256: hash.digest("hex"), bytes: stat.size };
}

function requireActiveKey(bundlePath, keyId) {
  let trusted;
  try {
    trusted = verify.loadTrustBundle(bundlePath);
  } catch (error) {
    die("the trust bundle at " + bundlePath + " is unusable: " + error.code);
  }
  const entry = trusted.get(keyId);
  if (!entry) {
    die(
      "key " +
        keyId +
        " is not in " +
        bundlePath +
        ".\n" +
        "  Publish a bootstrap carrying this key before signing with it, or nothing\n" +
        "  already installed will be able to verify the release."
    );
  }
  if (entry.state !== "active") {
    die("key " + keyId + " is '" + entry.state + "' in the trust bundle; only 'active' may sign");
  }
}

function sign(options) {
  if (!options.manifest) {
    die("sign needs --manifest <file>");
  }
  if (!options["out-dir"]) {
    die("sign needs --out-dir <dir>");
  }
  const bundlePath = options["trust-bundle"] || DEFAULT_BUNDLE;
  const identity = loadPrivateKey();
  requireActiveKey(bundlePath, identity.keyId);

  const manifest = readJson(options.manifest, "the manifest");
  if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) {
    die("the manifest must be a JSON object");
  }
  if (manifest.signingKeyId === undefined) {
    manifest.signingKeyId = identity.keyId;
  } else if (manifest.signingKeyId !== identity.keyId) {
    die(
      "the manifest names key " +
        manifest.signingKeyId +
        " but " +
        KEY_ENV +
        " holds " +
        identity.keyId
    );
  }
  if (options.archive) {
    const measured = digestArchive(options.archive);
    for (const [field, value] of [
      ["archiveSha256", measured.sha256],
      ["archiveBytes", measured.bytes],
    ]) {
      if (manifest[field] !== undefined && manifest[field] !== value) {
        die("the manifest says " + field + "=" + manifest[field] + ", the archive says " + value);
      }
      manifest[field] = value;
    }
  }

  // Validate before signing. A signature over a malformed manifest is a
  // signature that says the publisher meant it.
  try {
    verify.validateManifest(manifest, {});
  } catch (error) {
    die("the manifest is not signable: " + error.code + ": " + error.message);
  }

  const bytes = verify.canonicalize(manifest);
  const signature = crypto.sign(null, bytes, identity.key);

  // Self-check with the public half, so a corrupted key or a mangled secret
  // fails here rather than on a user's machine.
  const publicKey = crypto.createPublicKey(identity.key);
  if (!crypto.verify(null, bytes, publicKey, signature)) {
    die("the signature did not verify against its own public key; refusing to write it");
  }

  const outDir = options["out-dir"];
  fs.mkdirSync(outDir, { recursive: true });
  const manifestPath = path.join(outDir, "manifest.json");
  const signaturePath = path.join(outDir, "manifest.sig");
  fs.writeFileSync(manifestPath, bytes);
  fs.writeFileSync(signaturePath, signature.toString("base64") + "\n");

  process.stdout.write(
    [
      "signed " + manifest.version + " (" + manifest.platform + ", " + manifest.channel + ")",
      "  key        " + identity.keyId,
      "  manifest   " + manifestPath + " (" + bytes.length + " bytes)",
      "  signature  " + signaturePath,
      "",
    ].join("\n")
  );
}

/**
 * Print the key ID and public key of whatever is in the environment, so the
 * rotation procedure can put the public half into the trust bundle without
 * anyone copying the private half anywhere.
 */
function keyId() {
  const identity = loadPrivateKey();
  process.stdout.write(
    JSON.stringify(
      {
        keyId: identity.keyId,
        algorithm: "ed25519",
        publicKey: identity.spki.toString("base64"),
        state: "active",
      },
      null,
      2
    ) + "\n"
  );
}

function usage() {
  process.stdout.write(
    [
      "Sign an Agent Skills release manifest.",
      "",
      "  " + KEY_ENV + "=<pkcs8 pem or base64 der> \\",
      "    node scripts/sign-release.js sign --manifest <in.json> --out-dir <dir> \\",
      "      [--archive <file>] [--trust-bundle <file>]",
      "",
      "  " + KEY_ENV + "=<key> node scripts/sign-release.js key-id",
      "",
      "The key is read from " + KEY_ENV + " only. It is never accepted on the",
      "command line, never read from a file, and never printed.",
      "",
    ].join("\n")
  );
}

function main() {
  const argv = process.argv.slice(2);
  const command = argv[0];
  if (!command || command === "help" || command === "--help" || command === "-h") {
    usage();
    process.exit(command ? 0 : 2);
  }
  const options = parseArgs(argv.slice(1));
  if (command === "sign") {
    sign(options);
    return;
  }
  if (command === "key-id") {
    keyId();
    return;
  }
  die("unknown command " + command + "; expected sign or key-id");
}

main();
