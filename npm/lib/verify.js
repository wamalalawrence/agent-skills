"use strict";
/*
 * Ed25519 release verification for the Agent Skills bootstrap.
 *
 * This runs in Node, before the Python install engine is started, so a release
 * archive that is not exactly what the publisher signed never reaches the
 * extractor at all. It uses `node:crypto`, which has had native Ed25519 since
 * Node 12; the package engine floor is already `>=18`. There are no
 * dependencies here and there must never be any: this file is the thing that
 * decides whether foreign bytes may become executable code on the machine, and
 * a supply-chain dependency inside it would defeat the point of signing.
 *
 * Verification order is fixed and is the order the functions are written in:
 *
 *   1. parse the manifest bytes            (strictly, duplicate keys rejected)
 *   2. re-canonicalise and compare bytes    (one manifest has one encoding)
 *   3. verify the signature over those bytes against the trust bundle
 *   4. validate the manifest's own fields, and what the caller expected
 *   5. verify the archive's byte size, then stream it for its SHA-256
 *
 * Nothing later is attempted once something earlier has failed, and every
 * failure is a `VerificationError` carrying a distinct `code` from `CODES`.
 * A boolean would collapse "this is an attack" and "this build is old" into
 * the same fact, and the operator needs to tell them apart.
 *
 * Canonical form — the exact bytes that are signed:
 *
 *   * a JSON object at the top level, UTF-8 encoded, with no whitespace
 *     anywhere outside string values;
 *   * object keys sorted ascending by their UTF-8 byte sequence, which is the
 *     same order Python's `sorted()` and Go's `sort.Strings()` produce, and
 *     unlike JavaScript's default string comparison does not reorder astral
 *     characters;
 *   * values limited to objects, arrays, strings, `true`, `false`, `null`, and
 *     integers within the safe-integer range.
 *
 * Rejected rather than normalised: floating-point and out-of-range numbers
 * (no two languages agree on how to print them), `undefined`, functions,
 * symbols, bigints, class instances, cycles, lone surrogates, and duplicate
 * keys. Anything that is not exactly round-trippable is not signable, because
 * a verifier that guesses is a verifier that can be made to guess wrong.
 */

const crypto = require("crypto");
const fs = require("fs");

/** Every distinct reason verification can fail. Frozen: callers branch on it. */
const CODES = Object.freeze({
  // Canonical serialisation.
  CANONICAL_NOT_AN_OBJECT: "CANONICAL_NOT_AN_OBJECT",
  CANONICAL_UNSUPPORTED_TYPE: "CANONICAL_UNSUPPORTED_TYPE",
  CANONICAL_NON_INTEGER_NUMBER: "CANONICAL_NON_INTEGER_NUMBER",
  CANONICAL_UNSAFE_INTEGER: "CANONICAL_UNSAFE_INTEGER",
  CANONICAL_LONE_SURROGATE: "CANONICAL_LONE_SURROGATE",
  CANONICAL_DEPTH_EXCEEDED: "CANONICAL_DEPTH_EXCEEDED",
  CANONICAL_CYCLE: "CANONICAL_CYCLE",

  // The manifest as it arrived.
  MANIFEST_UNREADABLE: "MANIFEST_UNREADABLE",
  MANIFEST_NOT_JSON: "MANIFEST_NOT_JSON",
  MANIFEST_DUPLICATE_KEY: "MANIFEST_DUPLICATE_KEY",
  MANIFEST_NOT_CANONICAL: "MANIFEST_NOT_CANONICAL",
  MANIFEST_TOO_LARGE: "MANIFEST_TOO_LARGE",

  // The manifest's own fields.
  MANIFEST_FIELD_MISSING: "MANIFEST_FIELD_MISSING",
  MANIFEST_FIELD_TYPE: "MANIFEST_FIELD_TYPE",
  MANIFEST_FIELD_FORMAT: "MANIFEST_FIELD_FORMAT",
  MANIFEST_SCHEMA_UNSUPPORTED: "MANIFEST_SCHEMA_UNSUPPORTED",
  MANIFEST_BOOTSTRAP_TOO_OLD: "MANIFEST_BOOTSTRAP_TOO_OLD",

  // What the caller asked for versus what the manifest describes.
  MANIFEST_VERSION_MISMATCH: "MANIFEST_VERSION_MISMATCH",
  MANIFEST_CHANNEL_MISMATCH: "MANIFEST_CHANNEL_MISMATCH",
  MANIFEST_PLATFORM_MISMATCH: "MANIFEST_PLATFORM_MISMATCH",

  // The trust bundle.
  TRUST_BUNDLE_UNREADABLE: "TRUST_BUNDLE_UNREADABLE",
  TRUST_BUNDLE_MALFORMED: "TRUST_BUNDLE_MALFORMED",
  TRUST_BUNDLE_EMPTY: "TRUST_BUNDLE_EMPTY",
  TRUST_BUNDLE_DUPLICATE_KEY_ID: "TRUST_BUNDLE_DUPLICATE_KEY_ID",
  TRUST_KEY_MALFORMED: "TRUST_KEY_MALFORMED",
  TRUST_KEY_ID_MISMATCH: "TRUST_KEY_ID_MISMATCH",

  // The signature.
  SIGNING_KEY_UNKNOWN: "SIGNING_KEY_UNKNOWN",
  SIGNING_KEY_NOT_ACCEPTED: "SIGNING_KEY_NOT_ACCEPTED",
  SIGNATURE_ALGORITHM_UNSUPPORTED: "SIGNATURE_ALGORITHM_UNSUPPORTED",
  SIGNATURE_UNREADABLE: "SIGNATURE_UNREADABLE",
  SIGNATURE_MALFORMED: "SIGNATURE_MALFORMED",
  SIGNATURE_INVALID: "SIGNATURE_INVALID",

  // The archive.
  ARCHIVE_UNREADABLE: "ARCHIVE_UNREADABLE",
  ARCHIVE_SIZE_MISMATCH: "ARCHIVE_SIZE_MISMATCH",
  ARCHIVE_TOO_LARGE: "ARCHIVE_TOO_LARGE",
  ARCHIVE_DIGEST_MISMATCH: "ARCHIVE_DIGEST_MISMATCH",
});

/** The only manifest schema this bootstrap understands. */
const MANIFEST_SCHEMA = "agent-skills.manifest/v1";

/** The only signature algorithm. Not a parameter; a constant with a check. */
const ALGORITHM = "ed25519";

/** Ed25519 signatures are exactly 64 bytes. Anything else is not one. */
const SIGNATURE_BYTES = 64;

/** DER prefix of a SubjectPublicKeyInfo wrapping a raw Ed25519 public key. */
const SPKI_ED25519_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

/** Trust-bundle states. `reserved` exists so a slot can be published empty. */
const ACCEPTED_STATES = Object.freeze(["active", "retiring"]);

const MAX_MANIFEST_BYTES = 64 * 1024;
const MAX_ARCHIVE_BYTES = 512 * 1024 * 1024;
const MAX_CANONICAL_DEPTH = 32;

const SEMVER_RE = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const HEX40_RE = /^[0-9a-f]{40}$/;
const PLATFORM_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const KEY_ID_RE = /^ed25519-[0-9a-f]{16}$/;
const RFC3339_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const CHANNELS = ["stable", "rc"];

class VerificationError extends Error {
  constructor(code, message, detail) {
    super(message);
    this.name = "VerificationError";
    this.code = code;
    if (detail !== undefined) {
      this.detail = detail;
    }
  }
}

function fail(code, message, detail) {
  throw new VerificationError(code, message, detail);
}

// ---------------------------------------------------------------------------
// Canonical serialisation
// ---------------------------------------------------------------------------

function compareKeys(left, right) {
  return Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));
}

function encodeString(value) {
  // JSON.stringify escapes control characters and quotes exactly as RFC 8259
  // requires, and leaves every other code point literal. What it does not do
  // is refuse a lone surrogate, which has no UTF-8 encoding and would be
  // silently replaced with U+FFFD on the way to bytes — changing the signed
  // content without anyone noticing.
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        fail(CODES.CANONICAL_LONE_SURROGATE, "string contains an unpaired surrogate");
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      fail(CODES.CANONICAL_LONE_SURROGATE, "string contains an unpaired surrogate");
    }
  }
  return JSON.stringify(value);
}

function encodeValue(value, depth, seen, pathLabel) {
  if (depth > MAX_CANONICAL_DEPTH) {
    fail(CODES.CANONICAL_DEPTH_EXCEEDED, "manifest nests deeper than " + MAX_CANONICAL_DEPTH, {
      path: pathLabel,
    });
  }
  if (value === null) {
    return "null";
  }
  const type = typeof value;
  if (type === "boolean") {
    return value ? "true" : "false";
  }
  if (type === "string") {
    return encodeString(value);
  }
  if (type === "number") {
    if (!Number.isFinite(value)) {
      fail(CODES.CANONICAL_NON_INTEGER_NUMBER, "number is not finite", { path: pathLabel });
    }
    if (!Number.isInteger(value)) {
      fail(CODES.CANONICAL_NON_INTEGER_NUMBER, "number is not an integer", { path: pathLabel });
    }
    if (!Number.isSafeInteger(value)) {
      fail(CODES.CANONICAL_UNSAFE_INTEGER, "integer is outside the safe range", {
        path: pathLabel,
      });
    }
    return String(value === 0 ? 0 : value);
  }
  if (type !== "object") {
    fail(CODES.CANONICAL_UNSUPPORTED_TYPE, "value of type " + type + " cannot be signed", {
      path: pathLabel,
    });
  }
  if (seen.has(value)) {
    fail(CODES.CANONICAL_CYCLE, "manifest contains a cycle", { path: pathLabel });
  }
  seen.add(value);
  let out;
  if (Array.isArray(value)) {
    const parts = [];
    for (let index = 0; index < value.length; index += 1) {
      // A hole in a sparse array reads as `undefined`, which is not a JSON
      // value; it must not silently become `null`.
      if (!(index in value)) {
        fail(CODES.CANONICAL_UNSUPPORTED_TYPE, "array has a hole", {
          path: pathLabel + "[" + index + "]",
        });
      }
      parts.push(encodeValue(value[index], depth + 1, seen, pathLabel + "[" + index + "]"));
    }
    out = "[" + parts.join(",") + "]";
  } else {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      fail(CODES.CANONICAL_UNSUPPORTED_TYPE, "only plain objects can be signed", {
        path: pathLabel,
      });
    }
    const keys = Object.keys(value).sort(compareKeys);
    const parts = [];
    for (const key of keys) {
      const child = value[key];
      if (child === undefined) {
        fail(CODES.CANONICAL_UNSUPPORTED_TYPE, "value is undefined", {
          path: pathLabel + "." + key,
        });
      }
      parts.push(
        encodeString(key) + ":" + encodeValue(child, depth + 1, seen, pathLabel + "." + key)
      );
    }
    out = "{" + parts.join(",") + "}";
  }
  seen.delete(value);
  return out;
}

/**
 * Serialise a manifest object to the exact bytes that are signed.
 * Returns a Buffer; throws VerificationError with a CANONICAL_* code.
 */
function canonicalize(manifest) {
  if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) {
    fail(CODES.CANONICAL_NOT_AN_OBJECT, "a manifest must be a JSON object");
  }
  return Buffer.from(encodeValue(manifest, 0, new Set(), "$"), "utf8");
}

// ---------------------------------------------------------------------------
// Reading a manifest off the wire
// ---------------------------------------------------------------------------

/**
 * Report the first key that appears twice in the same JSON object, or null.
 *
 * `JSON.parse` keeps the last of a repeated key and says nothing, so a
 * manifest could carry one `archiveSha256` for a human reading the file and
 * another for the parser. The scan below only needs to know which string
 * tokens are keys, so it tracks nothing else.
 */
function findDuplicateKey(text) {
  const stack = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === "{") {
      stack.push({ object: true, keys: new Set(), expectKey: true });
      index += 1;
    } else if (char === "[") {
      stack.push({ object: false, keys: null, expectKey: false });
      index += 1;
    } else if (char === "}" || char === "]") {
      stack.pop();
      index += 1;
    } else if (char === ",") {
      const frame = stack[stack.length - 1];
      if (frame && frame.object) {
        frame.expectKey = true;
      }
      index += 1;
    } else if (char === '"') {
      let cursor = index + 1;
      let raw = "";
      while (cursor < text.length && text[cursor] !== '"') {
        if (text[cursor] === "\\") {
          raw += text[cursor] + text[cursor + 1];
          cursor += 2;
          continue;
        }
        raw += text[cursor];
        cursor += 1;
      }
      const frame = stack[stack.length - 1];
      if (frame && frame.object && frame.expectKey) {
        let key;
        try {
          key = JSON.parse('"' + raw + '"');
        } catch (error) {
          key = raw;
        }
        if (frame.keys.has(key)) {
          return key;
        }
        frame.keys.add(key);
        frame.expectKey = false;
      }
      index = cursor + 1;
    } else {
      index += 1;
    }
  }
  return null;
}

/**
 * Parse manifest bytes into an object, insisting that those bytes already are
 * the canonical encoding of that object.
 *
 * The alternative — parse loosely, re-canonicalise, verify the signature over
 * the result — would mean the file on disk and the bytes that were signed are
 * two different things, and every difference between them is somewhere an
 * attacker can hide a value that a human reviewer sees and the verifier does
 * not. One manifest has one encoding.
 */
function parseManifestBytes(bytes) {
  if (!Buffer.isBuffer(bytes)) {
    bytes = Buffer.from(bytes);
  }
  if (bytes.length === 0) {
    fail(CODES.MANIFEST_NOT_JSON, "the manifest is empty");
  }
  if (bytes.length > MAX_MANIFEST_BYTES) {
    fail(CODES.MANIFEST_TOO_LARGE, "the manifest is larger than " + MAX_MANIFEST_BYTES + " bytes");
  }
  const text = bytes.toString("utf8");
  if (Buffer.compare(Buffer.from(text, "utf8"), bytes) !== 0) {
    fail(CODES.MANIFEST_NOT_JSON, "the manifest is not valid UTF-8");
  }
  const duplicate = findDuplicateKey(text);
  if (duplicate !== null) {
    fail(CODES.MANIFEST_DUPLICATE_KEY, "the manifest repeats the key " + duplicate);
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail(CODES.MANIFEST_NOT_JSON, "the manifest is not valid JSON");
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    fail(CODES.CANONICAL_NOT_AN_OBJECT, "a manifest must be a JSON object");
  }
  const canonical = canonicalize(parsed);
  if (Buffer.compare(canonical, bytes) !== 0) {
    fail(CODES.MANIFEST_NOT_CANONICAL, "the manifest file is not in canonical form");
  }
  return parsed;
}

// ---------------------------------------------------------------------------
// The trust bundle
// ---------------------------------------------------------------------------

function decodeBase64Strict(value, code, what) {
  if (typeof value !== "string" || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    fail(code, what + " is not base64");
  }
  const decoded = Buffer.from(value, "base64");
  if (decoded.toString("base64") !== value) {
    fail(code, what + " is not canonical base64");
  }
  return decoded;
}

/**
 * The key ID of an Ed25519 public key: derived from the key, never asserted
 * beside it. A bundle that claims an ID the key does not have is malformed,
 * which makes "swap the key material under a trusted ID" a detected edit
 * rather than a silent one.
 */
function deriveKeyId(spkiDer) {
  const digest = crypto.createHash("sha256").update(spkiDer).digest("hex");
  return "ed25519-" + digest.slice(0, 16);
}

function loadTrustBundle(source) {
  let bundle = source;
  if (typeof source === "string") {
    let raw;
    try {
      raw = fs.readFileSync(source);
    } catch (error) {
      fail(CODES.TRUST_BUNDLE_UNREADABLE, "cannot read the trust bundle");
    }
    try {
      bundle = JSON.parse(raw.toString("utf8"));
    } catch (error) {
      fail(CODES.TRUST_BUNDLE_MALFORMED, "the trust bundle is not valid JSON");
    }
  }
  if (bundle === null || typeof bundle !== "object" || Array.isArray(bundle)) {
    fail(CODES.TRUST_BUNDLE_MALFORMED, "the trust bundle must be a JSON object");
  }
  if (!Array.isArray(bundle.keys)) {
    fail(CODES.TRUST_BUNDLE_MALFORMED, "the trust bundle has no keys array");
  }
  if (bundle.keys.length === 0) {
    fail(CODES.TRUST_BUNDLE_EMPTY, "the trust bundle holds no keys");
  }
  const byId = new Map();
  for (const entry of bundle.keys) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      fail(CODES.TRUST_BUNDLE_MALFORMED, "a trust bundle entry is not an object");
    }
    if (typeof entry.keyId !== "string" || !KEY_ID_RE.test(entry.keyId)) {
      fail(CODES.TRUST_BUNDLE_MALFORMED, "a trust bundle entry has no well-formed keyId");
    }
    if (entry.algorithm !== ALGORITHM) {
      fail(
        CODES.SIGNATURE_ALGORITHM_UNSUPPORTED,
        "trust bundle entry " + entry.keyId + " is not " + ALGORITHM
      );
    }
    if (typeof entry.state !== "string") {
      fail(CODES.TRUST_BUNDLE_MALFORMED, "trust bundle entry " + entry.keyId + " has no state");
    }
    if (byId.has(entry.keyId)) {
      fail(CODES.TRUST_BUNDLE_DUPLICATE_KEY_ID, "trust bundle repeats " + entry.keyId);
    }
    const der = decodeBase64Strict(
      entry.publicKey,
      CODES.TRUST_KEY_MALFORMED,
      "the public key of " + entry.keyId
    );
    // An Ed25519 SPKI is 44 bytes: a 12-byte prefix naming the algorithm and
    // the 32-byte key. Checking the prefix is what stops a bundle from
    // carrying, say, an RSA key under an entry that claims to be Ed25519.
    const wellFormed =
      der.length === SPKI_ED25519_PREFIX.length + 32 &&
      der.subarray(0, SPKI_ED25519_PREFIX.length).equals(SPKI_ED25519_PREFIX);
    if (!wellFormed) {
      fail(CODES.TRUST_KEY_MALFORMED, "the public key of " + entry.keyId + " is not Ed25519 SPKI");
    }
    if (deriveKeyId(der) !== entry.keyId) {
      fail(CODES.TRUST_KEY_ID_MISMATCH, "trust bundle entry " + entry.keyId + " names another key");
    }
    let keyObject;
    try {
      keyObject = crypto.createPublicKey({ key: der, format: "der", type: "spki" });
    } catch (error) {
      fail(CODES.TRUST_KEY_MALFORMED, "the public key of " + entry.keyId + " cannot be loaded");
    }
    if (keyObject.asymmetricKeyType !== "ed25519") {
      fail(CODES.TRUST_KEY_MALFORMED, "the public key of " + entry.keyId + " is not Ed25519");
    }
    byId.set(entry.keyId, { keyId: entry.keyId, state: entry.state, key: keyObject });
  }
  return byId;
}

// ---------------------------------------------------------------------------
// The signature
// ---------------------------------------------------------------------------

function decodeSignature(signature) {
  let bytes;
  if (Buffer.isBuffer(signature)) {
    bytes = signature;
  } else if (typeof signature === "string") {
    bytes = decodeBase64Strict(signature.trim(), CODES.SIGNATURE_MALFORMED, "the signature");
  } else {
    fail(CODES.SIGNATURE_MALFORMED, "the signature is neither bytes nor base64 text");
  }
  if (bytes.length !== SIGNATURE_BYTES) {
    fail(
      CODES.SIGNATURE_MALFORMED,
      "an Ed25519 signature is " + SIGNATURE_BYTES + " bytes, this one is " + bytes.length
    );
  }
  return bytes;
}

/**
 * Verify `signature` over `manifestBytes` using the key the manifest names.
 *
 * The manifest chooses the key ID, the bundle decides whether that ID is
 * trusted, and only a key the bundle currently accepts can produce a pass.
 * An unknown ID and a reserved-but-not-yet-live slot are different failures
 * because they need different answers: one is an attack or a stale bootstrap,
 * the other is a release signed before its key was published.
 */
function verifyManifestSignature(options) {
  const manifestBytes = options.manifestBytes;
  const manifest = options.manifest;
  const trusted = options.trustedKeys;
  if (manifest.signatureAlgorithm !== undefined && manifest.signatureAlgorithm !== ALGORITHM) {
    fail(
      CODES.SIGNATURE_ALGORITHM_UNSUPPORTED,
      "the manifest asks for " + String(manifest.signatureAlgorithm) + ", not " + ALGORITHM
    );
  }
  if (typeof manifest.signingKeyId !== "string" || !KEY_ID_RE.test(manifest.signingKeyId)) {
    fail(CODES.MANIFEST_FIELD_FORMAT, "signingKeyId is not a key identifier", {
      field: "signingKeyId",
    });
  }
  const entry = trusted.get(manifest.signingKeyId);
  if (!entry) {
    fail(CODES.SIGNING_KEY_UNKNOWN, "no trusted key with id " + manifest.signingKeyId);
  }
  if (ACCEPTED_STATES.indexOf(entry.state) === -1) {
    fail(
      CODES.SIGNING_KEY_NOT_ACCEPTED,
      "key " + entry.keyId + " is " + entry.state + ", which does not verify releases"
    );
  }
  const signature = decodeSignature(options.signature);
  let ok = false;
  try {
    ok = crypto.verify(null, manifestBytes, entry.key, signature);
  } catch (error) {
    ok = false;
  }
  if (!ok) {
    fail(CODES.SIGNATURE_INVALID, "the signature does not verify against " + entry.keyId);
  }
  return entry.keyId;
}

// ---------------------------------------------------------------------------
// The manifest's own fields
// ---------------------------------------------------------------------------

function requireField(manifest, field, type, predicate, description) {
  if (!(field in manifest) || manifest[field] === null) {
    fail(CODES.MANIFEST_FIELD_MISSING, "the manifest has no " + field, { field: field });
  }
  const value = manifest[field];
  if (typeof value !== type) {
    fail(CODES.MANIFEST_FIELD_TYPE, field + " must be a " + type, { field: field });
  }
  if (!predicate(value)) {
    fail(CODES.MANIFEST_FIELD_FORMAT, field + " must be " + description, { field: field });
  }
  return value;
}

function comparableVersion(version) {
  const core = version.split("+")[0];
  const [release, pre] = core.split("-");
  const parts = release.split(".").map((piece) => Number(piece));
  return { parts: parts, pre: pre === undefined ? null : pre };
}

/** -1, 0 or 1. A pre-release sorts below the release of the same number. */
function compareVersions(left, right) {
  const a = comparableVersion(left);
  const b = comparableVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (a.parts[index] !== b.parts[index]) {
      return a.parts[index] < b.parts[index] ? -1 : 1;
    }
  }
  if (a.pre === b.pre) {
    return 0;
  }
  if (a.pre === null) {
    return 1;
  }
  if (b.pre === null) {
    return -1;
  }
  return a.pre < b.pre ? -1 : 1;
}

/**
 * Check every field the plan says a manifest carries, then check the manifest
 * against what the caller asked for. A release that is correctly signed but
 * describes a different version or platform is still the wrong release, and
 * the signature is exactly what makes that worth saying out loud: someone
 * with a valid signed manifest tried to answer a question nobody asked.
 */
function validateManifest(manifest, options) {
  const expect = (options && options.expect) || {};
  const text = "string";
  requireField(manifest, "manifestSchema", text, (v) => v.length > 0, "a schema identifier");
  if (manifest.manifestSchema !== MANIFEST_SCHEMA) {
    fail(
      CODES.MANIFEST_SCHEMA_UNSUPPORTED,
      "this bootstrap understands " + MANIFEST_SCHEMA + ", not " + manifest.manifestSchema
    );
  }
  requireField(manifest, "version", text, (v) => SEMVER_RE.test(v), "a semantic version");
  requireField(manifest, "channel", text, (v) => CHANNELS.indexOf(v) !== -1, "stable or rc");
  requireField(manifest, "sourceCommit", text, (v) => HEX40_RE.test(v), "a 40-character commit");
  requireField(manifest, "platform", text, (v) => PLATFORM_RE.test(v), "a platform identifier");
  requireField(manifest, "archiveSha256", text, (v) => HEX64_RE.test(v), "64 lowercase hex chars");
  requireField(
    manifest,
    "archiveBytes",
    "number",
    (v) => Number.isSafeInteger(v) && v > 0 && v <= MAX_ARCHIVE_BYTES,
    "a byte count no larger than " + MAX_ARCHIVE_BYTES
  );
  requireField(manifest, "payloadTreeHash", text, (v) => HEX64_RE.test(v), "64 lowercase hex chars");
  requireField(
    manifest,
    "createdAt",
    text,
    (v) => RFC3339_UTC_RE.test(v) && !Number.isNaN(Date.parse(v)),
    "an RFC 3339 UTC timestamp"
  );
  requireField(manifest, "minimumBootstrapVersion", text, (v) => SEMVER_RE.test(v), "a version");
  requireField(manifest, "signingKeyId", text, (v) => KEY_ID_RE.test(v), "a key identifier");

  const bootstrapVersion = options && options.bootstrapVersion;
  if (bootstrapVersion && compareVersions(bootstrapVersion, manifest.minimumBootstrapVersion) < 0) {
    fail(
      CODES.MANIFEST_BOOTSTRAP_TOO_OLD,
      "release " +
        manifest.version +
        " needs bootstrap " +
        manifest.minimumBootstrapVersion +
        " or newer; this is " +
        bootstrapVersion
    );
  }
  if (expect.version !== undefined && expect.version !== manifest.version) {
    fail(
      CODES.MANIFEST_VERSION_MISMATCH,
      "asked for " + expect.version + ", the manifest describes " + manifest.version
    );
  }
  if (expect.channel !== undefined && expect.channel !== manifest.channel) {
    fail(
      CODES.MANIFEST_CHANNEL_MISMATCH,
      "asked for the " + expect.channel + " channel, the manifest says " + manifest.channel
    );
  }
  if (expect.platform !== undefined && expect.platform !== manifest.platform) {
    fail(
      CODES.MANIFEST_PLATFORM_MISMATCH,
      "asked for " + expect.platform + ", the manifest describes " + manifest.platform
    );
  }
  return manifest;
}

// ---------------------------------------------------------------------------
// The archive
// ---------------------------------------------------------------------------

/**
 * Check an archive's byte size and SHA-256 against the manifest.
 *
 * Streamed in chunks rather than read into a Buffer: a release archive is
 * bounded but not small, and the machine doing this is a developer laptop
 * that may also be running everything else. The size is checked first because
 * it is a stat call, and a file of the wrong length cannot be the right file.
 */
function verifyArchive(archivePath, manifest, options) {
  const limit = (options && options.maxArchiveBytes) || MAX_ARCHIVE_BYTES;
  return new Promise((resolve, reject) => {
    let stat;
    try {
      stat = fs.statSync(archivePath);
    } catch (error) {
      reject(new VerificationError(CODES.ARCHIVE_UNREADABLE, "cannot read the archive"));
      return;
    }
    if (!stat.isFile()) {
      reject(new VerificationError(CODES.ARCHIVE_UNREADABLE, "the archive is not a regular file"));
      return;
    }
    if (stat.size > limit) {
      reject(
        new VerificationError(
          CODES.ARCHIVE_TOO_LARGE,
          "the archive is " + stat.size + " bytes, over the " + limit + " byte bound"
        )
      );
      return;
    }
    if (stat.size !== manifest.archiveBytes) {
      reject(
        new VerificationError(
          CODES.ARCHIVE_SIZE_MISMATCH,
          "the manifest says " + manifest.archiveBytes + " bytes, the archive is " + stat.size
        )
      );
      return;
    }
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(archivePath);
    stream.on("error", () => {
      reject(new VerificationError(CODES.ARCHIVE_UNREADABLE, "cannot read the archive"));
    });
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => {
      const digest = hash.digest("hex");
      // Constant-time on purpose: the comparison itself is not a secret, but
      // making digest comparison timing-safe everywhere costs nothing and
      // removes the question of which comparisons need it.
      const expected = Buffer.from(manifest.archiveSha256, "utf8");
      const actual = Buffer.from(digest, "utf8");
      if (expected.length !== actual.length || !crypto.timingSafeEqual(expected, actual)) {
        reject(
          new VerificationError(
            CODES.ARCHIVE_DIGEST_MISMATCH,
            "the archive does not have the SHA-256 the manifest names"
          )
        );
        return;
      }
      resolve(digest);
    });
  });
}

// ---------------------------------------------------------------------------
// The whole gate
// ---------------------------------------------------------------------------

function readFileOrFail(filePath, code, what) {
  try {
    return fs.readFileSync(filePath);
  } catch (error) {
    return fail(code, "cannot read " + what);
  }
}

/**
 * The one call the bootstrap makes. Resolves with what was verified; rejects
 * with a VerificationError. Nothing is extracted, copied, or executed here —
 * this function only answers whether the archive on disk is the release the
 * publisher signed.
 */
async function verifyRelease(options) {
  const manifestBytes =
    options.manifestBytes !== undefined
      ? options.manifestBytes
      : readFileOrFail(options.manifestPath, CODES.MANIFEST_UNREADABLE, "the manifest");
  const signature =
    options.signature !== undefined
      ? options.signature
      : readFileOrFail(options.signaturePath, CODES.SIGNATURE_UNREADABLE, "the signature")
          .toString("utf8")
          .trim();
  const trustedKeys =
    options.trustedKeys instanceof Map ? options.trustedKeys : loadTrustBundle(options.trustBundle);

  const manifest = parseManifestBytes(manifestBytes);
  const keyId = verifyManifestSignature({
    manifestBytes: Buffer.isBuffer(manifestBytes) ? manifestBytes : Buffer.from(manifestBytes),
    manifest: manifest,
    signature: signature,
    trustedKeys: trustedKeys,
  });
  validateManifest(manifest, {
    expect: options.expect,
    bootstrapVersion: options.bootstrapVersion,
  });
  const digest = await verifyArchive(options.archivePath, manifest, {
    maxArchiveBytes: options.maxArchiveBytes,
  });
  return { manifest: manifest, signingKeyId: keyId, archiveSha256: digest };
}

module.exports = {
  ACCEPTED_STATES,
  ALGORITHM,
  CODES,
  MANIFEST_SCHEMA,
  MAX_ARCHIVE_BYTES,
  MAX_MANIFEST_BYTES,
  VerificationError,
  canonicalize,
  compareVersions,
  deriveKeyId,
  findDuplicateKey,
  loadTrustBundle,
  parseManifestBytes,
  validateManifest,
  verifyArchive,
  verifyManifestSignature,
  verifyRelease,
};
