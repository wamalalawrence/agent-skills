#!/usr/bin/env node
/*
 * Agent Skills distribution bootstrap.
 *
 * This is the only thing the npm package does: check that the machine can run
 * the installer, then hand over to it. Every decision about what a release is,
 * where it comes from, how it is verified, and how it is activated belongs to
 * the installation engine in `vendor/`, which is the same code the installed
 * product runs. There is one installer; this file is a doorway to it.
 *
 * Deliberately absent:
 *   - any npm lifecycle script. Nothing runs on `npm install`; the user has to
 *     ask for an installation by typing one.
 *   - any product content. Skills, docs, and runtime arrive from the release
 *     source, not from this package, so publishing the package publicly does
 *     not publish the product.
 *   - any credential handling. If the release source needs authentication, the
 *     engine reports that and exits; nothing here reads, prompts for, or
 *     stores a token.
 *
 * One thing does happen here rather than in the engine: Ed25519 verification
 * of a signed release, in `lib/verify.js`. It runs in Node because Node is
 * what is already running, has Ed25519 in its standard library, and is earlier
 * in the chain than Python — the signature is checked before the archive is
 * handed to anything that will open it. See `docs/release-signing.md`.
 */

"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const ENGINE = path.join(PACKAGE_ROOT, "vendor", "install.py");
const TRUST_BUNDLE = path.join(PACKAGE_ROOT, "lib", "trust-bundle.json");

// Matches lib/asrelease/exits.py. Keep in step; the test suite asserts it.
const EXIT = { OK: 0, USAGE: 2, AUTH_REQUIRED: 3, INTEGRITY: 5 };

function fail(message, code) {
  process.stderr.write("agent-skills: " + message + "\n");
  process.exit(code === undefined ? EXIT.USAGE : code);
}

function findPython() {
  const candidates = process.env.AGENT_SKILLS_PYTHON
    ? [process.env.AGENT_SKILLS_PYTHON]
    : ["python3", "python3.13", "python3.12", "python3.11", "python3.10", "python3.9"];
  for (const candidate of candidates) {
    const probe = spawnSync(
      candidate,
      ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"],
      { stdio: "ignore" }
    );
    if (probe.status === 0) {
      return candidate;
    }
  }
  return null;
}

function usage() {
  process.stdout.write(
    [
      "Agent Skills installer",
      "",
      "  npx " + require("../package.json").name + " install",
      "",
      "Installs Agent Skills on this machine and registers it with every",
      "supported agent host it finds. After that, use the durable command:",
      "",
      "  agent-skills doctor      what this environment can actually do",
      "  agent-skills update      move to the latest release",
      "  agent-skills rollback    return to the previous release",
      "  agent-skills uninstall   remove it again",
      "",
      "One command is answered here rather than by the installer:",
      "",
      "  verify-release --manifest M --signature S --archive A",
      "                           check a signed release without installing it",
      "",
      "Options are passed straight through to the installer:",
      "  --version X        install this exact release",
      "  --channel rc       follow the release-candidate line",
      "  --source DIR       install from a local source tree",
      "  --hosts a,b        register only these hosts",
      "  --no-path-link     do not link the launcher onto PATH",
      "",
      "No credential is requested. If the release source is private, the",
      "installer uses the git access you already have and never stores it.",
      "",
    ].join("\n")
  );
}

function flags(argv) {
  const out = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index].indexOf("--") !== 0) {
      continue;
    }
    const value = argv[index + 1];
    if (value === undefined || value.indexOf("--") === 0) {
      fail(argv[index] + " needs a value", EXIT.USAGE);
    }
    out[argv[index].slice(2)] = value;
    index += 1;
  }
  return out;
}

/*
 * Verify a signed release and say so. Exits 5 — the frozen integrity code —
 * on any verification failure, and prints the failure's code, because "it did
 * not verify" is not actionable and an unknown key ID, an old bootstrap, and a
 * tampered archive need three different answers.
 */
function verifyRelease(argv) {
  const given = flags(argv);
  for (const required of ["manifest", "signature", "archive"]) {
    if (!given[required]) {
      fail("verify-release needs --" + required + " <file>", EXIT.USAGE);
    }
  }
  let verifier;
  try {
    verifier = require(path.join(PACKAGE_ROOT, "lib", "verify.js"));
  } catch (error) {
    fail("this package is incomplete: lib/verify.js is missing", EXIT.USAGE);
  }
  verifier
    .verifyRelease({
      manifestPath: given.manifest,
      signaturePath: given.signature,
      archivePath: given.archive,
      trustBundle: given["trust-bundle"] || TRUST_BUNDLE,
      bootstrapVersion: require("../package.json").version,
      expect: {
        version: given.version,
        channel: given.channel,
        platform: given.platform,
      },
    })
    .then((result) => {
      process.stdout.write(
        "verified " +
          result.manifest.version +
          " (" +
          result.manifest.platform +
          ", " +
          result.manifest.channel +
          ") signed by " +
          result.signingKeyId +
          "\n"
      );
      process.exit(EXIT.OK);
    })
    .catch((error) => {
      const code = error && error.code ? error.code : "VERIFICATION_FAILED";
      fail("INTEGRITY: " + code + ": " + error.message, EXIT.INTEGRITY);
    });
}

function main() {
  const argv = process.argv.slice(2);
  const command = argv[0];

  if (!command || command === "help" || command === "--help" || command === "-h") {
    usage();
    process.exit(command ? EXIT.OK : EXIT.USAGE);
  }

  if (command === "verify-release") {
    verifyRelease(argv.slice(1));
    return;
  }

  // The bootstrap exists to get a first release onto the machine. Everything
  // else is the job of the installed CLI, and saying so is more useful than
  // silently forwarding a command that would work differently here.
  const supported = ["install", "update", "check-updates", "versions", "provider"];
  if (supported.indexOf(command) === -1) {
    fail(
      "the bootstrap only runs: " +
        supported.join(", ") +
        "\n  Once installed, use the agent-skills command itself for " +
        command +
        ".",
      EXIT.USAGE
    );
  }

  if (!fs.existsSync(ENGINE)) {
    fail("this package is incomplete: " + ENGINE + " is missing", EXIT.USAGE);
  }

  const python = findPython();
  if (!python) {
    fail(
      "python3 3.8 or newer is required and was not found on PATH.\n" +
        "  macOS:  xcode-select --install   (or install Python from python.org)\n" +
        "  Debian: sudo apt install python3",
      EXIT.USAGE
    );
  }

  const bash = spawnSync("bash", ["-c", "exit 0"], { stdio: "ignore" });
  if (bash.status !== 0) {
    fail(
      "bash is required and was not found.\n" +
        "  On Windows, run this from WSL or Git Bash; native PowerShell is not supported.",
      EXIT.USAGE
    );
  }

  const result = spawnSync(python, [ENGINE].concat(argv), { stdio: "inherit" });
  if (result.error) {
    fail("could not start the installer: " + result.error.message, EXIT.USAGE);
  }
  process.exit(result.status === null ? EXIT.USAGE : result.status);
}

main();
