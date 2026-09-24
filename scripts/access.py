#!/usr/bin/env python3
"""Resolve access to an external service, lazily and generically.

This is the general-purpose access-resolution mechanism, and the documented path
for any service the project has no bespoke support for. It replaces a per-skill
scramble through `.env`, `.jira-config.yml`, and ad-hoc prompting.

Adoption is partial as of v0.37.0, and saying otherwise would be a lie an auditor
could check: skills reach it through `docs/auth-discovery.md`, and `doctor.sh`
reports on secret storage through it, but the tracker preflight still runs
`auth-preflight.py`. Migrating that is tracked as a follow-up in
`eval-runs/v0.37.0/summary.md`.

Three properties matter more than any feature here:

1. **Generic.** Nothing about Jira, Confluence, Sonar, GitHub, a database, or an
   internal HTTP API is compiled in. The caller supplies the service name and
   the field names it needs, so a skill can ask for a service that did not exist
   when this file was written.
2. **Capability-first.** The resolver prefers an authenticated tool or session
   that already exists over storing another secret. A logged-in `gh`, an MCP
   server the host already has, an existing cloud CLI profile — all of those
   beat writing a token to disk.
3. **Credentials are identities, not projects.** A profile is an account on a
   service (`work-jira`, `personal-github`, `production-readonly-db`). Several
   repositories share one; one repository may use several.

Security boundaries, which are the reason several things here look pedantic:

* **A committed file may never name a credential profile.** `.agent-skills.yml`
  is checked into a repository, so from this file's point of view it is
  attacker-controlled. It may declare *what* a service is; it may not select
  *which* identity to unlock. Profile selection comes from the user-global
  binding registry or from an untracked `.agent-skills.local.yml`, and
  untrackedness is verified with git rather than assumed from the filename.
* **Resolution is not authorization.** Answering "can I authenticate?" says
  nothing about "may I perform destructive action X?". See
  docs/destructive-action-safety.md.
* **Secret values are never printed.** Not by `resolve`, not by `profiles`, not
  by `backend`, not in JSON, not in an error. Presence is reported; values are
  not. `--json` output is safe to paste into a chat.
* **Secrets are never requested in chat.** Interactive entry uses hidden
  terminal input. With no TTY the resolver explains where to put the value and
  exits, rather than asking an agent to relay it.

Exit codes:
  0  access resolved (or the requested management action succeeded)
  1  access not resolved; the report names what is missing
  2  usage or environment error

The Access Discovery subcommands (`scan`, `check`, `classify-error`, ...) live in
`access_discovery_cli.py` and add three codes from the CLI-wide contract in
`lib/asrelease/exits.py`: 3 authentication required, 4 network failure during a
probe, and 11 capability unavailable (the route works; this operation does not).
"""
from __future__ import annotations

import argparse
import getpass
import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PROFILES = "agent-skills.credentials/v1"
SCHEMA_BINDINGS = "agent-skills.bindings/v1"

# A profile name is an identifier the user chose. It ends up in a keychain
# service string and a filename, so it is constrained.
#
# The only transformation applied is case-folding to lowercase, which is done
# before validation so `Work-Jira` and `work-jira` are the same identity rather
# than two. Case-folding cannot introduce a path separator or a shell
# metacharacter, so it does not widen the charset. Everything else is rejected
# rather than rewritten: turning a bad name into a different valid one is how
# you end up writing to the wrong place.
PROFILE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")
SERVICE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")
FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

# Field names that are secret unless the caller says otherwise. A caller that
# forgets `--secret` should still not get a token echoed back.
SECRET_FIELD_HINTS = (
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "key",
    "passphrase",
    "credential",
    "client_secret",
    "private_key",
    "session_token",
)

REDACTED = "set (hidden)"


# ----------------------------------------------------------------------------
# Locations
# ----------------------------------------------------------------------------
def config_dir() -> Path:
    override = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "agent-skills"
    return Path.home() / ".config" / "agent-skills"


def profiles_path() -> Path:
    return config_dir() / "credentials.json"


def bindings_path() -> Path:
    return config_dir() / "bindings.json"


def fallback_secrets_dir() -> Path:
    return config_dir() / "secrets"


def ensure_config_dir() -> Path:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def is_secret_field(name: str, declared_secrets: set) -> bool:
    if name in declared_secrets:
        return True
    lowered = name.lower()
    return any(hint in lowered for hint in SECRET_FIELD_HINTS)


# ----------------------------------------------------------------------------
# JSON state helpers
# ----------------------------------------------------------------------------
def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path: Path, payload: object, mode: int = 0o600) -> None:
    ensure_config_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(tmp, mode)
    tmp.replace(path)


def load_profiles() -> dict:
    data = read_json(profiles_path(), {})
    if not isinstance(data, dict):
        return {"schema": SCHEMA_PROFILES, "profiles": {}}
    data.setdefault("schema", SCHEMA_PROFILES)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        data["profiles"] = {}
    return data


def save_profiles(data: dict) -> None:
    write_json(profiles_path(), data)


def load_bindings() -> dict:
    data = read_json(bindings_path(), {})
    if not isinstance(data, dict):
        return {"schema": SCHEMA_BINDINGS, "projects": {}}
    data.setdefault("schema", SCHEMA_BINDINGS)
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    return data


def save_bindings(data: dict) -> None:
    write_json(bindings_path(), data)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------
# Secret backends
#
# Each backend is a small adapter over an OS credential store. `FileBackend` is
# the explicit fallback: permission-restricted, outside every repository, and
# always reported so it is never mistaken for secure storage.
# ----------------------------------------------------------------------------
class BackendError(RuntimeError):
    pass


class KeychainBackend:
    """macOS Keychain via `security`."""

    name = "macos-keychain"
    label = "macOS Keychain"
    secure = True

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin" and shutil.which("security") is not None

    @staticmethod
    def _service(profile: str, field: str) -> str:
        return "agent-skills:%s:%s" % (profile, field)

    def store(self, profile: str, field: str, value: str) -> None:
        # The value is passed in argv, so it is visible to a same-user `ps` for
        # the duration of this call. That is a known and accepted exposure, not an
        # oversight — the two alternatives are worse:
        #
        #   * `-w` with no value and the secret piped on stdin exits 0 and stores
        #     an EMPTY secret (measured on macOS 15). Silent credential loss.
        #   * `security -i` does read commands from stdin, but it parses them as a
        #     command stream, so a secret containing a newline would inject a
        #     second `security` command. Trading a local timing window for an
        #     injection vector is not an improvement.
        #
        # There is no stdlib Keychain API, and adding a dependency to a
        # zero-dependency installer costs more than it buys. Recorded in
        # docs/known-limitations.md and docs/security-review-v0.37.0.md.
        #
        # `-U` updates in place, so re-running set does not stack entries.
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", self._service(profile, field),
                "-a", profile,
                "-l", "agent-skills %s %s" % (profile, field),
                "-U", "-w", value,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise BackendError("keychain write failed (exit %d)" % result.returncode)

    def fetch(self, profile: str, field: str):
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", self._service(profile, field),
                "-a", profile, "-w",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", "replace").rstrip("\n")

    def delete(self, profile: str, field: str) -> bool:
        result = subprocess.run(
            [
                "security", "delete-generic-password",
                "-s", self._service(profile, field), "-a", profile,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


class SecretServiceBackend:
    """Linux Secret Service via `secret-tool` (libsecret)."""

    name = "secret-service"
    label = "Linux Secret Service (libsecret)"
    secure = True

    @staticmethod
    def available() -> bool:
        if shutil.which("secret-tool") is None:
            return False
        # A headless session has secret-tool but no unlocked collection. Probe
        # rather than assume, so we do not promise secure storage that fails on
        # first write.
        probe = subprocess.run(
            ["secret-tool", "search", "application", "agent-skills-probe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return probe.returncode in (0, 1)

    def store(self, profile: str, field: str, value: str) -> None:
        result = subprocess.run(
            [
                "secret-tool", "store", "--label",
                "agent-skills %s %s" % (profile, field),
                "application", "agent-skills",
                "profile", profile,
                "field", field,
            ],
            input=value.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise BackendError("secret-service write failed (exit %d)" % result.returncode)

    def fetch(self, profile: str, field: str):
        result = subprocess.run(
            [
                "secret-tool", "lookup",
                "application", "agent-skills",
                "profile", profile,
                "field", field,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.decode("utf-8", "replace")
        return value or None

    def delete(self, profile: str, field: str) -> bool:
        result = subprocess.run(
            [
                "secret-tool", "clear",
                "application", "agent-skills",
                "profile", profile,
                "field", field,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


class FileBackend:
    """Permission-restricted file fallback, used only when no OS store works.

    Deliberately plain JSON. Encrypting a file with a key stored beside it is
    theatre, and pretending otherwise would be worse than being honest that this
    tier is only as strong as the filesystem permissions.
    """

    name = "file"
    label = "restricted file (no OS credential store available)"
    secure = False

    @staticmethod
    def available() -> bool:
        return True

    @staticmethod
    def _path(profile: str) -> Path:
        # Names are validated before they reach here, so no separator can appear.
        return fallback_secrets_dir() / ("%s.json" % profile)

    def _load(self, profile: str) -> dict:
        data = read_json(self._path(profile), {})
        return data if isinstance(data, dict) else {}

    def _save(self, profile: str, data: dict) -> None:
        directory = fallback_secrets_dir()
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        write_json(self._path(profile), data)

    def store(self, profile: str, field: str, value: str) -> None:
        data = self._load(profile)
        data[field] = value
        self._save(profile, data)

    def fetch(self, profile: str, field: str):
        return self._load(profile).get(field)

    def delete(self, profile: str, field: str) -> bool:
        data = self._load(profile)
        if field not in data:
            return False
        del data[field]
        if data:
            self._save(profile, data)
        else:
            try:
                self._path(profile).unlink()
            except OSError:
                return False
        return True


BACKENDS = (KeychainBackend, SecretServiceBackend, FileBackend)


def select_backend(preferred: str = ""):
    """Return the best available backend, honouring an explicit preference.

    `AGENT_SKILLS_SECRET_BACKEND` forces a choice, which is how the test suite
    exercises the fallback path on a machine that has a working keychain.
    """
    preferred = preferred or os.environ.get("AGENT_SKILLS_SECRET_BACKEND", "")
    if preferred:
        for backend in BACKENDS:
            if backend.name == preferred:
                if not backend.available():
                    raise BackendError(
                        "requested secret backend %r is not available here" % preferred
                    )
                return backend()
        raise BackendError("unknown secret backend %r" % preferred)
    for backend in BACKENDS:
        if backend.available():
            return backend()
    return FileBackend()


def _backend_named(recorded: str, entry: dict):
    """Resolve a recorded backend name to an instance, refusing downgrades.

    A profile written to the keychain must not silently start reading from the
    file fallback: that is how a "working" credential quietly becomes a
    different, weaker one. Downgrades are reported, never assumed.
    """
    for backend in BACKENDS:
        if backend.name == recorded:
            if backend.available():
                return backend(), None
            return None, (
                "profile %r was stored in %s, which is not available right now. "
                "Refusing to fall back to weaker storage."
                % (entry.get("name", "?"), backend.label)
            )
    return select_backend(), None


def backend_for_field(entry: dict, field: str):
    """Backend one specific secret field was stored in.

    Storage is recorded per field, not per profile. A single `backend` scalar
    could not describe a profile whose `token` went to the Keychain and whose
    later `client_secret` was written with `--backend file`: the second write
    overwrote the scalar, so the Keychain value became unreadable *and*
    undeletable — `forget` looked for it in the wrong store, and the secret
    outlived the identity that owned it.
    """
    per_field = entry.get("secret_backends")
    recorded = ""
    if isinstance(per_field, dict):
        recorded = str(per_field.get(field, "") or "")
    if not recorded:
        # Profiles written before per-field records existed carry one scalar.
        recorded = str(entry.get("backend", "") or "")
    return _backend_named(recorded, entry)


def backend_for_profile(entry: dict):
    """Backend for a profile as a whole. Prefer `backend_for_field`."""
    return _backend_named(str(entry.get("backend", "") or ""), entry)


def profile_secret_backends(entry: dict):
    """Every distinct backend holding a secret for this profile, with its fields."""
    grouped = {}
    for field in entry.get("secret_fields", []) or []:
        per_field = entry.get("secret_backends")
        recorded = ""
        if isinstance(per_field, dict):
            recorded = str(per_field.get(field, "") or "")
        if not recorded:
            recorded = str(entry.get("backend", "") or "")
        grouped.setdefault(recorded, []).append(field)
    return grouped


# ----------------------------------------------------------------------------
# Repository identity and trust
# ----------------------------------------------------------------------------
def run_git(args, cwd: Path):
    state, output, _ = run_git_checked(args, cwd)
    return output if state == "ok" else None


def run_git_checked(args, cwd: Path):
    """Run git and report whether git itself was able to answer.

    Returns `(state, stdout, stderr)` where state is one of:

      "ok"        git ran and exited 0 — the output is an answer.
      "refused"   git ran and exited non-zero — also an answer ("no").
      "unusable"  git could not answer: no binary, unreadable cwd, dubious
                  ownership, a broken GIT_DIR, a permissions error on .git.

    The third state exists because "git says this file is not tracked" and "git
    could not tell me whether this file is tracked" must not collapse into the
    same value. Collapsing them is what makes a tracked-file check fail open.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return "unusable", "", ""
    if result.returncode == 0:
        return "ok", result.stdout.strip(), result.stderr.strip()
    return "refused", result.stdout.strip(), result.stderr.strip()


# git exits non-zero both for "this is not a repository" and for conditions that
# mean "I refuse to operate here". Only the first is an answer.
_GIT_NOT_A_REPO = re.compile(
    r"not a git repository|does not appear to be a git repository", re.I
)
_GIT_DID_NOT_MATCH = re.compile(r"did not match any file", re.I)


def git_root(cwd: Path):
    top = run_git(["rev-parse", "--show-toplevel"], cwd)
    return Path(top) if top else None


def normalise_remote(url: str) -> str:
    """Reduce a git remote to a stable host/path key.

    `git@github.com:acme/api.git` and `https://github.com/acme/api` describe the
    same repository and must produce the same binding key, or a user would have
    to bind the same repo twice.
    """
    url = url.strip()
    url = re.sub(r"\.git$", "", url)
    url = re.sub(r"^[a-z0-9+]+://", "", url, flags=re.I)
    url = re.sub(r"^[^@/]+@", "", url)
    url = url.replace(":", "/", 1) if "/" not in url.split(":")[0] else url
    url = re.sub(r"/{2,}", "/", url)
    return url.lower().rstrip("/")


def project_identity(cwd: Path) -> dict:
    """Identify the repository for binding purposes.

    The remote is preferred because it survives the repo being moved or
    re-cloned. The realpath is the fallback and is recorded as lower confidence.
    """
    root = git_root(cwd)
    if root is None:
        return {"kind": "path", "key": "path:%s" % os.path.realpath(str(cwd)),
                "root": str(cwd), "remote": None}
    remote = run_git(["config", "--get", "remote.origin.url"], root)
    if remote:
        return {
            "kind": "remote",
            "key": "remote:%s" % normalise_remote(remote),
            "root": str(root),
            "remote": remote,
        }
    return {
        "kind": "path",
        "key": "path:%s" % os.path.realpath(str(root)),
        "root": str(root),
        "remote": None,
    }


# ----------------------------------------------------------------------------
# Knowledge-source bindings (1.3.0)
#
# Which shared knowledge source a repository reads from and proposes to is an
# access decision, so it lives beside the credential bindings and is keyed by
# the same identity. The rule that matters most: a repository binds to AT MOST
# one source. Two matching sources is a configuration error the caller reports;
# it never picks one. A path-keyed repository (no origin remote) has no
# identity another machine could reproduce, so it never binds.
#
# The file holds URLs and glob patterns only. It is `machine_binding` data and
# never leaves this machine.
# ----------------------------------------------------------------------------
KNOWLEDGE_SOURCES_SCHEMA = "agent-skills.knowledge-sources/v1"


class AccessError(Exception):
    """A binding or source configuration problem: a usage error, never a crash."""


KNOWLEDGE_SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
DEFAULT_SYNC_INTERVAL_MINUTES = 15


def knowledge_sources_path() -> Path:
    return config_dir() / "knowledge-sources.json"


def load_knowledge_sources() -> dict:
    """The configured sources and settings. A missing file is no sources."""
    empty = {"schema": KNOWLEDGE_SOURCES_SCHEMA, "sources": {}, "settings": {}}
    path = knowledge_sources_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty
    except (OSError, ValueError):
        # Unreadable is not "no sources": the caller must not silently fall
        # back to unbound and hide a configuration the user believes exists.
        raise AccessError("knowledge source configuration is unreadable: %s" % path)
    if not isinstance(data, dict) or data.get("schema") != KNOWLEDGE_SOURCES_SCHEMA:
        raise AccessError("knowledge source configuration has an unknown schema: %s" % path)
    data.setdefault("sources", {})
    data.setdefault("settings", {})
    return data


def save_knowledge_sources(data: dict) -> None:
    ensure_config_dir()
    data["schema"] = KNOWLEDGE_SOURCES_SCHEMA
    write_json(knowledge_sources_path(), data)


def binding_pattern(value: str) -> str:
    """Normalise a binding pattern the way a remote is normalised.

    `git@example.com:acme/*` and `https://example.com/acme/*` are one pattern.
    """
    pattern = normalise_remote(value)
    if not pattern or "/" not in pattern:
        raise AccessError("a binding pattern needs a host and a path: %r" % value)
    return pattern


def _identity_remote_key(identity: dict) -> str:
    key = str(identity.get("key") or "")
    return key[len("remote:"):] if key.startswith("remote:") else ""


def resolve_knowledge_binding(identity: dict, data: dict = None) -> dict:
    """Which configured source this repository identity binds to.

    Returns {"status": "none" | "bound" | "ambiguous", "source": name | None,
    "candidates": [names]}. Only "bound" names a source.
    """
    data = load_knowledge_sources() if data is None else data
    remote = _identity_remote_key(identity)
    if not remote:
        return {"status": "none", "source": None, "candidates": [],
                "reason": "repository has no origin remote"}
    matches = []
    for name, source in sorted(data.get("sources", {}).items()):
        for pattern in source.get("binds") or []:
            if fnmatch.fnmatchcase(remote, pattern):
                matches.append(name)
                break
    if not matches:
        return {"status": "none", "source": None, "candidates": []}
    if len(matches) > 1:
        return {"status": "ambiguous", "source": None, "candidates": matches,
                "reason": "several knowledge sources bind this repository"}
    return {"status": "bound", "source": matches[0], "candidates": matches}


def knowledge_binding_conflicts(data: dict = None) -> list:
    """Configuration errors `doctor` reports: shared org, overlapping binds."""
    data = load_knowledge_sources() if data is None else data
    sources = data.get("sources", {})
    problems = []
    names = sorted(sources)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            a, b = sources[first], sources[second]
            active = a.get("status", "active") == "active" and b.get("status", "active") == "active"
            if active and a.get("org") and a.get("org") == b.get("org"):
                problems.append("sources %s and %s both claim org %r" % (first, second, a["org"]))
            for pa in a.get("binds") or []:
                for pb in b.get("binds") or []:
                    if pa == pb or fnmatch.fnmatchcase(pa, pb) or fnmatch.fnmatchcase(pb, pa):
                        problems.append("sources %s and %s overlap on %s / %s" % (first, second, pa, pb))
    return problems


def tracked_state(path: Path) -> str:
    """Whether git tracks this path: "tracked", "untracked", or "unknown".

    Enforces the rule that a committed file cannot select a credential profile
    or supply credential values. Asked of git rather than inferred from the
    filename, because `.agent-skills.local.yml` is only trustworthy if it really
    is untracked.

    "unknown" is a distinct answer on purpose. An earlier version returned a
    plain bool and mapped every git failure to False — "not tracked", therefore
    trusted — so removing git from PATH, or a `detected dubious ownership`
    error, or a restricted-PATH agent container was enough to make a *committed*
    file authoritative. Callers must treat "unknown" as untrusted.
    """
    state, output, stderr = run_git_checked(
        ["rev-parse", "--show-toplevel"], path.parent
    )
    if state == "unusable":
        return "unknown"
    if state == "refused":
        # A genuine "there is no repository here" is an answer: nothing can have
        # committed this file. Anything else means git declined to operate.
        return "untracked" if _GIT_NOT_A_REPO.search(stderr) else "unknown"
    if not output:
        return "unknown"
    root = Path(output)
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        # Outside the work tree git just reported, so that repository cannot be
        # tracking it. Reached via symlinked paths.
        return "untracked"
    state, _, stderr = run_git_checked(
        ["ls-files", "--error-unmatch", str(relative)], root
    )
    if state == "ok":
        return "tracked"
    if state == "refused":
        return "untracked" if _GIT_DID_NOT_MATCH.search(stderr) else "unknown"
    return "unknown"


def path_is_trusted_untracked(path: Path):
    """`(trusted, reason)` for a file that is only credible when not committed.

    `reason` is None when the file may be used, and a user-facing explanation
    when it may not.
    """
    state = tracked_state(path)
    if state == "untracked":
        return True, None
    if state == "tracked":
        return False, (
            "%s is tracked by git and was ignored. A committed file must not "
            "carry credentials or name a credential profile. Remove it from git "
            "and add it to .gitignore." % path.name
        )
    return False, (
        "%s was ignored because git could not confirm it is untracked. This "
        "file is only trusted when it is provably not committed, so it is "
        "refused when that cannot be checked (git missing, or refusing to read "
        "this repository)." % path.name
    )


# ----------------------------------------------------------------------------
# Minimal YAML reading
#
# Only the shapes this repository documents are supported: top-level scalars and
# one level of nesting. PyYAML is not a dependency, and a full parser is not
# needed to read a handful of keys.
# ----------------------------------------------------------------------------
def read_simple_yaml(path: Path) -> dict:
    result = {}
    if not path.is_file():
        return result
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    current_key = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            key, sep, value = raw.partition(":")
            if not sep:
                continue
            current_key = key.strip()
            value = strip_inline_comment(value.strip())
            if value:
                result[current_key] = value
            else:
                result[current_key] = {}
            continue
        if current_key is None or not isinstance(result.get(current_key), dict):
            continue
        key, sep, value = raw.strip().partition(":")
        if not sep:
            continue
        result[current_key][key.strip()] = strip_inline_comment(value.strip())
    return result


def strip_inline_comment(value: str) -> str:
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    value = re.sub(r"\s+#.*$", "", value)
    return value.strip().strip("'\"")


def read_env_file(path: Path) -> dict:
    """Parse a `.env` file without shell interpolation or command substitution."""
    values = {}
    if not path.is_file():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


# ----------------------------------------------------------------------------
# Capability detection — step 1 of the resolution order
#
# Table-driven so a new "already authenticated" path is one row. Each probe is
# read-only, fast, and must never mutate a session.
# ----------------------------------------------------------------------------
def probe_cli(command, args, needle: str = "") -> bool:
    if shutil.which(command) is None:
        return False
    try:
        result = subprocess.run(
            [command] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    if needle and needle.lower() not in (result.stdout or "").lower():
        return False
    return True


# service-name substring -> (kind, description, probe)
CAPABILITY_PROBES = (
    (
        ("github", "gh"),
        "authenticated-cli",
        "the `gh` CLI is logged in; it holds its own credential",
        lambda: probe_cli("gh", ["auth", "status"]),
    ),
    (
        ("gitlab",),
        "authenticated-cli",
        "the `glab` CLI is logged in; it holds its own credential",
        lambda: probe_cli("glab", ["auth", "status"]),
    ),
    (
        ("aws", "s3", "dynamodb", "cloudwatch"),
        "authenticated-cli",
        "an AWS CLI session resolves; no stored secret is needed",
        lambda: probe_cli("aws", ["sts", "get-caller-identity"]),
    ),
    (
        ("gcp", "google", "bigquery"),
        "authenticated-cli",
        "an active gcloud account is configured",
        lambda: probe_cli("gcloud", ["auth", "list", "--filter=status:ACTIVE",
                                     "--format=value(account)"]),
    ),
    (
        ("azure", "azuredevops", "azure-devops"),
        "authenticated-cli",
        "an Azure CLI session resolves",
        lambda: probe_cli("az", ["account", "show"]),
    ),
    (
        ("kubernetes", "k8s", "kubectl"),
        "authenticated-cli",
        "a kubectl context is configured",
        lambda: probe_cli("kubectl", ["config", "current-context"]),
    ),
    (
        ("jira", "confluence", "atlassian", "bitbucket"),
        "authenticated-cli",
        "the `jira` CLI is installed and reports a usable configuration",
        lambda: probe_cli("jira", ["me"]),
    ),
)

# The host(s) a successful probe can be trusted to speak for, keyed by the first
# needle of each group above.
#
# A probe answers "is this tool logged in", not "is this tool logged in to the
# host the caller asked about". Without this, a `gh` session for github.com
# resolved a GitHub Enterprise request and a `jira` CLI configured for one tenant
# resolved another. An empty tuple means the host cannot be determined from the
# probe at all, so a request naming a specific resource is never short-circuited
# on that tool alone.
CAPABILITY_SERVED_HOSTS = {
    "github": ("github.com",),
    "gitlab": ("gitlab.com",),
    "aws": (),
    "gcp": (),
    "azure": (),
    "kubernetes": (),
    "jira": (),
}

def detect_mcp(service: str, cwd: Path):
    """Report an MCP server in the current host that serves this service.

    Asks Access Discovery (`access_ladder.mcp_servers_for`), which reads every
    host's MCP configuration into routes, instead of searching config text for
    the service name. It says which server, in which host, and in what mode,
    because a server that exists is not a server that can write: before a write,
    `agent-skills access check` answers for the operation. No tool is called.
    """
    try:
        import access_ladder
        found = access_ladder.mcp_servers_for(service, cwd)
    except Exception as exc:  # noqa: BLE001 - discovery must not break resolution
        return {"kind": "mcp-present", "detail": "MCP configuration could not be read (%s)" % exc,
                "source": "", "serves_resource": False}
    if found["matches"]:
        match = found["matches"][0]
        more = len(found["matches"]) - 1
        detail = "%s serves %s%s; before a write run `agent-skills access check --system <id> --op <op>`" % (
            access_ladder.describe_match(match), service, " (and %d more)" % more if more > 0 else "")
        return {"kind": "mcp", "detail": detail, "source": match["file"], "mode": match["mode"],
                "base_url": match["base_url"]}
    if found["servers"]:
        return {
            "kind": "mcp-present",
            "detail": "host has %d MCP server(s), none recognised for %s; `agent-skills access scan` lists them"
                      % (found["servers"], service),
            "source": "",
        }
    return None


def detect_capability(service: str, cwd: Path, resource: str = ""):
    """Report an already-authenticated tool that could serve this request.

    `serves_resource` in the result says whether the probe can be trusted for the
    resource the caller named. False means "this tool is logged in, but not
    provably to the host you asked about" — worth telling the user about, not
    worth treating as a resolution.
    """
    lowered = service.lower()
    wanted = resource_host(resource) if resource else ""
    for needles, kind, detail, probe in CAPABILITY_PROBES:
        if not any(needle in lowered for needle in needles):
            continue
        try:
            if not probe():
                continue
        except Exception:
            continue
        served = CAPABILITY_SERVED_HOSTS.get(needles[0], ())
        if not wanted:
            serves = True
        elif served and wanted in served:
            serves = True
        else:
            serves = False
        result = {"kind": kind, "detail": detail, "source": "cli", "serves_resource": serves}
        if not serves:
            result["detail"] = (
                "%s, but it could not be confirmed to serve %s, so it was not "
                "treated as resolving this request" % (detail, resource)
            )
        return result
    found = detect_mcp(service, cwd)
    if found is not None and "serves_resource" not in found:
        # A route whose base URL names a host can be matched to the request;
        # one that names none cannot be trusted to serve a specific resource.
        route_host = resource_host(found.get("base_url", ""))
        found["serves_resource"] = (not wanted) or (bool(route_host) and route_host == wanted)
    return found


# ----------------------------------------------------------------------------
# Environment-variable naming
#
# Generic and predictable: a caller does not have to tell the resolver which
# variables to read, and a user can override any field without editing state.
# ----------------------------------------------------------------------------
def env_candidates(service: str, field: str):
    service_token = re.sub(r"[^A-Za-z0-9]+", "_", service).strip("_").upper()
    field_token = re.sub(r"[^A-Za-z0-9]+", "_", field).strip("_").upper()
    names = [
        "AGENT_SKILLS_%s_%s" % (service_token, field_token),
        "%s_%s" % (service_token, field_token),
    ]
    # Long-standing spellings this project shipped before v0.37.0.
    legacy = {
        ("JIRA", "TOKEN"): ["JIRA_API_TOKEN"],
        ("JIRA", "HOST"): ["JIRA_HOST"],
        ("JIRA", "LOGIN"): ["JIRA_LOGIN"],
        ("JIRA", "AUTH_TYPE"): ["JIRA_AUTH_TYPE"],
        ("CONFLUENCE", "TOKEN"): ["CONFLUENCE_API_TOKEN"],
        ("CONFLUENCE", "HOST"): ["CONFLUENCE_HOST"],
        ("CONFLUENCE", "LOGIN"): ["CONFLUENCE_LOGIN"],
        ("SONAR", "TOKEN"): ["SONAR_TOKEN"],
        ("SONAR", "HOST"): ["SONAR_HOST_URL"],
        ("GITHUB", "TOKEN"): ["GITHUB_TOKEN", "GH_TOKEN"],
    }
    names.extend(legacy.get((service_token, field_token), []))
    return names


# ----------------------------------------------------------------------------
# Project-scoped sources
# ----------------------------------------------------------------------------
def local_override_path(root: Path) -> Path:
    return root / ".agent-skills.local.yml"


def read_local_overrides(root: Path):
    """Read `.agent-skills.local.yml`, refusing it when git tracks it.

    A tracked file is a committed file, and a committed file may not carry
    credentials or select an identity.
    """
    path = local_override_path(root)
    if not path.is_file():
        return {}, None
    trusted, reason = path_is_trusted_untracked(path)
    if not trusted:
        return {}, reason
    return read_simple_yaml(path), None


def legacy_config_candidates(root: Path, cwd: Path):
    """Directories that may hold a pre-v0.37.0 `.env`.

    Includes the parent of the repository because `setup.init` used to write
    into the workspace folder above every repo. Walking up is bounded to keep
    the search predictable and cheap.
    """
    seen = []
    current = cwd.resolve()
    for _ in range(6):
        if current not in seen:
            seen.append(current)
        if current.parent == current:
            break
        current = current.parent
    root_resolved = root.resolve()
    for extra in (root_resolved, root_resolved.parent):
        if extra not in seen:
            seen.append(extra)
    workspace = os.environ.get("WORKSPACE_ROOT")
    if workspace:
        candidate = Path(workspace)
        if candidate.is_dir() and candidate.resolve() not in seen:
            seen.insert(0, candidate.resolve())
    return seen


def read_legacy_sources(root: Path, cwd: Path):
    """Collect values from legacy `.env`, `.env.local`, and `.jira-config.yml`.

    Later files win, matching the documented layering. Returns the merged values
    plus the files they came from, so the report can say where a value was found
    without printing it.
    """
    values = {}
    sources = []
    refusals = []
    repo_supplied = set()
    root_resolved = root.resolve()

    def inside_repo(path: Path) -> bool:
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError:
            return False
        return True

    def usable(path: Path) -> bool:
        """A legacy config file is only credible when it is not committed.

        The tracked-file rule was written for `.agent-skills.local.yml`, but the
        legacy files are the ones that carry the actual values, so it has to
        apply here too. Without it a committed `.env` inside a repository is read
        on the same footing as one a user wrote by hand in their own workspace.
        """
        if not inside_repo(path):
            return True
        trusted, reason = path_is_trusted_untracked(path)
        if not trusted:
            refusals.append(reason)
        return trusted

    for directory in legacy_config_candidates(root, cwd):
        for name in (".env", ".env.local"):
            path = directory / name
            if path.is_file():
                if not usable(path):
                    continue
                found = read_env_file(path)
                if found:
                    values.update(found)
                    sources.append(str(path))
                    if inside_repo(path):
                        repo_supplied.update(found)
        jira_config = directory / ".jira-config.yml"
        if jira_config.is_file():
            if not usable(jira_config):
                continue
            parsed = read_simple_yaml(jira_config)
            mapped = {}
            if isinstance(parsed.get("server"), str):
                mapped["JIRA_HOST"] = parsed["server"]
            if isinstance(parsed.get("login"), str):
                mapped["JIRA_LOGIN"] = parsed["login"]
            if isinstance(parsed.get("auth_type"), str):
                mapped["JIRA_AUTH_TYPE"] = parsed["auth_type"]
            # Unresolved ${VAR} placeholders are incomplete configuration, not
            # values. Dropping them here is what stops an agent reporting
            # "no access" when the real problem is an unloaded .env.
            mapped = {
                key: value
                for key, value in mapped.items()
                if value and not re.search(r"\$\{[A-Z_][A-Z0-9_]*\}", value)
            }
            if mapped:
                values.update(mapped)
                sources.append(str(jira_config))
                if inside_repo(jira_config):
                    repo_supplied.update(mapped)
    return values, sources, refusals, repo_supplied


# ----------------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------------
def compatible_profiles(profiles: dict, service: str, resource: str):
    """Profiles that could serve this request.

    Matching is on service first, then resource host when the caller gave one.
    A profile for a different host is not compatible, which is what keeps a
    customer's identity out of another customer's repository.
    """
    matches = []
    wanted_host = resource_host(resource) if resource else ""
    for name, entry in sorted(profiles.items()):
        if not isinstance(entry, dict):
            continue
        if entry.get("service") != service:
            continue
        if wanted_host:
            entry_host = resource_host(entry.get("resource", ""))
            if entry_host and entry_host != wanted_host:
                continue
        matches.append((name, entry))
    return matches


def strict_binding_enabled() -> bool:
    """True when an identity may only be used via an explicit binding.

    Set `AGENT_SKILLS_STRICT_BINDING=1` when one machine holds identities for
    several customers or environments and "the only compatible one" is not a
    safe default. It removes the last path by which a repository could benefit
    from an identity nobody bound to it.
    """
    value = os.environ.get("AGENT_SKILLS_STRICT_BINDING", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def resource_host(resource: str) -> str:
    if not resource:
        return ""
    value = re.sub(r"^[a-z0-9+]+://", "", resource.strip(), flags=re.I)
    value = value.split("/")[0]
    return value.split("@")[-1].lower()


# Fields that name where a credential will be sent. Treated as one class because
# a wrong value in any of them redirects the request.
HOST_FIELDS = ("host", "base_url", "url", "server", "resource")


class Resolution:
    """The answer to one access request. Never holds a secret value."""

    def __init__(self, service: str, resource: str):
        self.service = service
        self.resource = resource
        self.status = "unresolved"
        self.via = None
        self.profile = None
        self.fields_present = []
        self.fields_missing = []
        self.sources = {}
        self.notes = []
        self.candidates = []
        self.next_steps = []
        # Things a caller should surface to the user rather than just log: a
        # repository tried to influence credential selection or routing.
        self.security_findings = []

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "resource": self.resource or None,
            "status": self.status,
            "via": self.via,
            "profile": self.profile,
            "fields_present": self.fields_present,
            "fields_missing": self.fields_missing,
            "field_sources": self.sources,
            "candidates": self.candidates,
            "notes": self.notes,
            "security_findings": self.security_findings,
            "next_steps": self.next_steps,
            "authorization": (
                "Resolution answers authentication only. It grants no "
                "permission to perform destructive actions. See "
                "docs/destructive-action-safety.md."
            ),
        }


def resolve_access(service, resource, required, secrets, cwd, allow_capability=True,
                   values_out=None):
    """Walk the documented precedence order once, top to bottom.

    `values_out`, when a dict is passed, receives the resolved field values.
    It exists for in-process callers that must send a credential themselves
    (the meeting capture provider sends its key as an HTTP header), so the value
    never crosses a process boundary, an argv, or stdout. The returned
    `Resolution` still holds no value, and the CLI never passes this.
    """
    resolution = Resolution(service, resource)
    root = git_root(cwd) or cwd
    profiles_state = load_profiles()
    profiles = profiles_state.get("profiles", {})

    # 1. An already-authenticated tool or session beats storing another secret.
    if allow_capability:
        capability = detect_capability(service, cwd, resource)
        if (
            capability
            and capability["kind"] not in ("mcp-present",)
            and capability.get("serves_resource", True)
        ):
            resolution.status = "resolved"
            resolution.via = capability["kind"]
            # Record the requested fields as satisfied by the tool. Leaving both
            # lists empty alongside `status: resolved` told a caller branching on
            # `fields_missing` that it held a host and a token when it held
            # neither — the tool holds them, and the caller must use the tool.
            resolution.fields_present = sorted(required)
            resolution.fields_missing = []
            for field in required:
                resolution.sources[field] = "%s (held by the tool, not by us)" % capability["kind"]
            resolution.notes.append(capability["detail"])
            resolution.notes.append(
                "No credential was read or stored. Use the authenticated tool directly."
            )
            return resolution
        if capability:
            resolution.notes.append(capability["detail"])

    found = {}

    # 2. Explicit process environment. Kept ahead of every file so an operator
    #    can always override without editing state.
    for field in required:
        for name in env_candidates(service, field):
            value = os.environ.get(name)
            if value:
                found[field] = value
                resolution.sources[field] = "process-env:%s" % name
                break

    # 3. Project-local sources, in order: untracked local override, then legacy
    #    workspace config for backwards compatibility.
    overrides, override_error = read_local_overrides(root)
    if override_error:
        resolution.notes.append(override_error)
    local_service_block = overrides.get(service)
    if isinstance(local_service_block, dict):
        for field in required:
            if field in found:
                continue
            value = local_service_block.get(field)
            if value:
                found[field] = value
                resolution.sources[field] = "project-local:.agent-skills.local.yml"

    # Fields a file inside the repository supplied. Tracked separately because a
    # repository is a weaker authority than the machine: it may describe what it
    # needs, but it must not end up steering a machine-held secret somewhere the
    # user did not choose. See the mismatch check before the identity merge.
    repo_controlled_fields = set()

    legacy_values, legacy_sources, legacy_refusals, legacy_repo_keys = read_legacy_sources(
        root, cwd
    )
    for refusal in legacy_refusals:
        resolution.notes.append(refusal)
    if legacy_values:
        for field in required:
            if field in found:
                continue
            for name in env_candidates(service, field):
                if legacy_values.get(name):
                    found[field] = legacy_values[name]
                    resolution.sources[field] = "legacy-config:%s" % name
                    if name in legacy_repo_keys:
                        repo_controlled_fields.add(field)
                    break
        if legacy_sources:
            resolution.notes.append(
                "legacy configuration discovered at: %s" % ", ".join(sorted(set(legacy_sources)))
            )

    # 4 and 5. A named global identity, chosen by an explicit binding or by
    #    being the only compatible one.
    profile_name = None
    binding_source = None

    local_bindings = overrides.get("credentials")
    if isinstance(local_bindings, dict) and local_bindings.get(service):
        profile_name = str(local_bindings[service])
        binding_source = "project-local:.agent-skills.local.yml"

    if profile_name is None:
        bindings = load_bindings()
        identity = project_identity(cwd)
        entry = bindings.get("projects", {}).get(identity["key"], {})
        if isinstance(entry, dict) and entry.get(service):
            profile_name = str(entry[service])
            binding_source = "user-global binding for %s" % identity["key"]

    matches = compatible_profiles(profiles, service, resource)

    # Auto-selection of a single compatible identity is what makes "two repos
    # share one work account" work without re-entering a token. It is safe
    # because the choice is a property of the machine, not of the repository:
    # a checked-in file cannot create, rename, or point at an identity.
    #
    # It is still a convenience, and someone working across several customers
    # may not want it. Strict mode turns it off, so an identity is only ever
    # used when the user bound it explicitly.
    strict = strict_binding_enabled()
    if profile_name is None and len(matches) == 1 and not strict:
        profile_name = matches[0][0]
        binding_source = "the only compatible identity on this machine"
    elif profile_name is None and len(matches) == 1 and strict:
        resolution.notes.append(
            "strict binding is on, so the single compatible identity %r was not used "
            "automatically. Bind it: agent-skills access bind --service %s --profile %s"
            % (matches[0][0], service, matches[0][0])
        )
        resolution.candidates = [
            {
                "profile": matches[0][0],
                "resource": matches[0][1].get("resource", ""),
                "account": matches[0][1].get("account", ""),
            }
        ]
    elif profile_name is None and len(matches) > 1:
        resolution.candidates = [
            {
                "profile": name,
                "resource": entry.get("resource", ""),
                "account": entry.get("account", ""),
            }
            for name, entry in matches
        ]

    if profile_name is not None:
        if not PROFILE_NAME_RE.match(profile_name):
            resolution.notes.append(
                "ignored an invalid profile name from %s" % (binding_source or "a binding")
            )
            profile_name = None
        elif profile_name not in profiles:
            resolution.notes.append(
                "binding names profile %r, which does not exist on this machine"
                % profile_name
            )
            profile_name = None

    # An identity must not be pointed at a host the repository chose.
    #
    # The invariant this release states is that a committed file cannot *select*
    # an identity, and that holds. But selection is not the only way to misuse
    # one: a file inside the repository can supply `host` while the identity
    # supplies `token`, and the merge below would hand a corporate secret to an
    # attacker-chosen endpoint and report `resolved`. `compatible_profiles`
    # cannot catch it, because on the default path the caller passes no
    # `--resource` to filter on. So compare the host that was actually resolved
    # against the one recorded for the identity, and refuse a mismatch.
    if profile_name is not None:
        repo_host = ""
        repo_host_field = ""
        for field in HOST_FIELDS:
            if field in repo_controlled_fields and found.get(field):
                repo_host = found[field]
                repo_host_field = field
                break
        recorded = str(profiles.get(profile_name, {}).get("resource", "") or "")
        if repo_host and recorded:
            if resource_host(repo_host) != resource_host(recorded):
                resolution.notes.append(
                    "refused identity %r: this repository supplies %s, which is not the "
                    "host that identity was created for. A file inside a repository may "
                    "not aim a machine-held credential at a different host. Set %s "
                    "outside the repository, or bind an identity for that host "
                    "explicitly." % (profile_name, repo_host_field, repo_host_field)
                )
                resolution.security_findings.append(
                    "repository-supplied %s did not match the resource recorded for "
                    "identity %r; the identity was not used"
                    % (repo_host_field, profile_name)
                )
                profile_name = None

    if profile_name is not None:
        entry = profiles[profile_name]
        resolution.profile = profile_name
        resolution.notes.append("using identity %r (%s)" % (profile_name, binding_source))
        stored_fields = entry.get("fields", {})
        if isinstance(stored_fields, dict):
            for field, value in sorted(stored_fields.items()):
                if field in found or field not in required:
                    continue
                if value:
                    found[field] = str(value)
                    resolution.sources[field] = "identity:%s" % profile_name
        # Each secret field is read from the store it was written to, so a
        # profile split across two stores resolves fully instead of reporting the
        # fields in the other store as missing.
        for field in entry.get("secret_fields", []) or []:
            if field in found or field not in required:
                continue
            backend, downgrade_error = backend_for_field(entry, field)
            if backend is None:
                if downgrade_error:
                    resolution.notes.append(downgrade_error)
                continue
            value = backend.fetch(profile_name, field)
            if value:
                found[field] = value
                resolution.sources[field] = "identity:%s (%s)" % (
                    profile_name, backend.name,
                )

    # A resource the caller supplied is itself a resolved field when the service
    # needs a host and nothing else provided one.
    if resource:
        for field in ("host", "base_url", "url", "server", "resource"):
            if field in required and field not in found:
                found[field] = resource
                resolution.sources[field] = "request:--resource"

    resolution.fields_present = sorted(found)
    resolution.fields_missing = [field for field in required if field not in found]
    if isinstance(values_out, dict):
        values_out.update(found)

    if not resolution.fields_missing:
        resolution.status = "resolved"
        resolution.via = resolution.via or (
            "identity" if resolution.profile else "configuration"
        )
    else:
        resolution.status = "needs-setup"
        resolution.next_steps = build_next_steps(resolution, service, resource, secrets)

    return resolution


def build_next_steps(resolution, service, resource, secrets):
    """Say the smallest true thing that unblocks the user.

    Never asks for a secret in the reply. Points at hidden-input entry, the OS
    store, or an environment variable instead.
    """
    steps = []
    if resolution.candidates:
        names = ", ".join(item["profile"] for item in resolution.candidates)
        steps.append(
            "Several identities match %s (%s). Choose one for this repository: "
            "agent-skills access bind --service %s --profile <name>"
            % (service, names, service)
        )
        return steps

    missing_secret = [f for f in resolution.fields_missing if is_secret_field(f, secrets)]
    missing_plain = [f for f in resolution.fields_missing if f not in missing_secret]

    if missing_plain:
        steps.append(
            "Missing non-secret field(s): %s. Provide with: agent-skills access set "
            "--profile <name> --service %s %s"
            % (
                ", ".join(missing_plain),
                service,
                " ".join("--field %s=<value>" % f for f in missing_plain),
            )
        )
    if missing_secret:
        steps.append(
            "Missing secret field(s): %s. Run this yourself in a terminal; the value is "
            "read with hidden input and stored in the OS credential store, never in a "
            "repository and never in chat: agent-skills access set --profile <name> "
            "--service %s %s"
            % (
                ", ".join(missing_secret),
                service,
                " ".join("--secret-field %s" % f for f in missing_secret),
            )
        )
        steps.append(
            "Alternatively export it for this session only: %s=<value>"
            % env_candidates(service, missing_secret[0])[0]
        )
    if resource:
        steps.append("Resource under request: %s" % resource)
    steps.append(
        "Prefer an already-authenticated tool, MCP server, or OAuth session if one exists "
        "for this service. See docs/access-resolution.md and docs/mcp.md."
    )
    return steps


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------
def render_resolution(resolution) -> str:
    lines = []
    lines.append("service: %s" % resolution.service)
    if resolution.resource:
        lines.append("resource: %s" % resolution.resource)
    lines.append("status: %s" % resolution.status)
    if resolution.via:
        lines.append("via: %s" % resolution.via)
    if resolution.profile:
        lines.append("identity: %s" % resolution.profile)
    if resolution.fields_present:
        lines.append("resolved fields:")
        for field in resolution.fields_present:
            source = resolution.sources.get(field, "unknown")
            lines.append("  - %s: %s [%s]" % (field, REDACTED, source))
    if resolution.fields_missing:
        lines.append("missing fields:")
        for field in resolution.fields_missing:
            lines.append("  - %s" % field)
    for finding in resolution.security_findings:
        lines.append("security: %s" % finding)
    for note in resolution.notes:
        lines.append("note: %s" % note)
    for step in resolution.next_steps:
        lines.append("next: %s" % step)
    lines.append(
        "authorization: authentication only. This does not authorize destructive action."
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cmd_resolve(args) -> int:
    service = args.service.strip().lower()
    if not SERVICE_NAME_RE.match(service):
        print("FAIL invalid service name %r" % args.service, file=sys.stderr)
        return 2
    required = split_list(args.require) or ["host", "token"]
    for field in required:
        if not FIELD_NAME_RE.match(field):
            print("FAIL invalid field name %r" % field, file=sys.stderr)
            return 2
    secrets = set(split_list(args.secret))
    resolution = resolve_access(
        service,
        (args.resource or "").strip(),
        required,
        secrets,
        Path(args.cwd),
        allow_capability=not args.no_capability,
    )
    if args.json:
        print(json.dumps(resolution.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_resolution(resolution))
    return 0 if resolution.status == "resolved" else 1


def cmd_profiles(args) -> int:
    state = load_profiles()
    profiles = state.get("profiles", {})
    rows = []
    for name in sorted(profiles):
        entry = profiles[name]
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "profile": name,
                "service": entry.get("service", ""),
                "resource": entry.get("resource", ""),
                "account": entry.get("account", ""),
                "fields": sorted((entry.get("fields") or {}).keys()),
                "secret_fields": sorted(entry.get("secret_fields") or []),
                "backend": entry.get("backend", ""),
                "created_at": entry.get("created_at", ""),
                "updated_at": entry.get("updated_at", ""),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("No credential identities are configured on this machine.")
        print("They are created on demand, when a task first needs one.")
        return 0
    print("Credential identities (values are never shown)")
    for row in rows:
        print("")
        print("%s" % row["profile"])
        print("  service        : %s" % row["service"])
        print("  resource       : %s" % (row["resource"] or "(any)"))
        print("  account        : %s" % (row["account"] or "(unset)"))
        print("  fields         : %s" % (", ".join(row["fields"]) or "(none)"))
        print("  secret fields  : %s" % (", ".join(row["secret_fields"]) or "(none)"))
        print("  stored in      : %s" % row["backend"])
        print("  updated        : %s" % row["updated_at"])
    return 0


def store_identity(profile, service, plain, secrets, backend=None, resource="", account=""):
    """Write one identity: non-secret fields to credentials.json, secrets to a backend.

    The one write path for credentials. `access set` uses it after reading
    secrets with hidden input; in-process callers that obtained a secret the
    same way (a hidden prompt) or from a token endpoint (an OAuth refresh
    token) use it too, so every secret lands in the same store, recorded per
    field, and `forget` removes it. Names must already be validated.
    """
    if not PROFILE_NAME_RE.match(profile) or not SERVICE_NAME_RE.match(service):
        raise BackendError("invalid profile or service name")
    for name in list(plain) + list(secrets):
        if not FIELD_NAME_RE.match(name):
            raise BackendError("invalid field name %r" % name)
    backend = backend or select_backend()
    for name, value in secrets.items():
        backend.store(profile, name, value)

    state = load_profiles()
    profiles = state.setdefault("profiles", {})
    entry = profiles.get(profile)
    if not isinstance(entry, dict):
        entry = {"created_at": utc_now()}
    entry["name"] = profile
    entry["service"] = service
    if resource:
        entry["resource"] = resource.strip()
    if account:
        entry["account"] = account.strip()
    merged_fields = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
    merged_fields.update(plain)
    entry["fields"] = merged_fields
    existing_secrets = entry.get("secret_fields") or []
    entry["secret_fields"] = sorted(set(list(existing_secrets) + list(secrets)))
    # Record storage per field. `backend` stays as the profile-level default so
    # profiles written by earlier versions keep resolving, but the per-field map
    # is what `resolve` and `forget` read.
    per_field = entry.get("secret_backends")
    if not isinstance(per_field, dict):
        per_field = {}
    for field in secrets:
        per_field[field] = backend.name
    if per_field:
        entry["secret_backends"] = per_field
    if secrets or not entry.get("backend"):
        entry["backend"] = backend.name
    entry["updated_at"] = utc_now()
    profiles[profile] = entry
    save_profiles(state)
    return entry


def fetch_identity(profile, fields):
    """In-process read of one identity's fields, secrets included.

    For callers that own the identity by name (the meeting providers' OAuth
    tokens). Values are returned to the caller only: never printed, never
    passed on argv. Missing profile or field -> absent from the result.
    """
    entry = (load_profiles().get("profiles") or {}).get(profile)
    if not isinstance(entry, dict):
        return {}
    out = {}
    plain = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
    secret_fields = set(entry.get("secret_fields") or [])
    for field in fields:
        if field in secret_fields:
            backend, problem = backend_for_field(entry, field)
            if backend is None:
                raise BackendError(problem)
            value = backend.fetch(profile, field)
            if value:
                out[field] = value
        elif plain.get(field) not in (None, ""):
            out[field] = str(plain[field])
    return out


def identity_metadata(profile):
    """Non-secret view of one identity: fields and the names of its secrets."""
    entry = (load_profiles().get("profiles") or {}).get(profile)
    if not isinstance(entry, dict):
        return {}
    return {
        "fields": dict(entry.get("fields") or {}),
        "secret_fields": sorted(entry.get("secret_fields") or []),
    }


def cmd_set(args) -> int:
    profile = args.profile.strip().lower()
    service = args.service.strip().lower()
    if not PROFILE_NAME_RE.match(profile):
        print(
            "FAIL invalid profile name %r. Use lowercase letters, digits, dot, "
            "dash, underscore." % args.profile,
            file=sys.stderr,
        )
        return 2
    if not SERVICE_NAME_RE.match(service):
        print("FAIL invalid service name %r" % args.service, file=sys.stderr)
        return 2

    plain = {}
    for item in args.field or []:
        key, sep, value = item.partition("=")
        key = key.strip().lower()
        if not sep or not FIELD_NAME_RE.match(key):
            # The name only. Echoing the whole `name=value` here printed the
            # value into the terminal and into whatever captured it, which is
            # precisely the exposure `--secret-field` exists to avoid — and the
            # likeliest reason the name was malformed is that somebody was
            # passing a credential through the wrong flag.
            shown = key or item.partition("=")[0]
            print(
                "FAIL --field expects name=value with a simple name; the name %r is not one"
                % shown[:60],
                file=sys.stderr,
            )
            return 2
        if is_secret_field(key, set(args.secret_field or [])):
            print(
                "FAIL %r looks like a secret. Pass it as --secret-field %s so the "
                "value is read with hidden input instead of appearing in your shell "
                "history." % (key, key),
                file=sys.stderr,
            )
            return 2
        plain[key] = value

    secret_fields = []
    for name in args.secret_field or []:
        name = name.strip().lower()
        if not FIELD_NAME_RE.match(name):
            print("FAIL invalid --secret-field name %r" % name, file=sys.stderr)
            return 2
        secret_fields.append(name)

    try:
        backend = select_backend(args.backend or "")
    except BackendError as error:
        print("FAIL %s" % error, file=sys.stderr)
        return 2

    if not backend.secure:
        print(
            "NOTE no OS credential store is available here, so secret values go to a "
            "permission-restricted file under %s (mode 0600, outside every repository)."
            % fallback_secrets_dir()
        )

    collected = {}
    for name in secret_fields:
        value = os.environ.get("AGENT_SKILLS_SECRET_VALUE_%s" % name.upper())
        if value:
            # Non-interactive path for CI and for the test suite. Documented so
            # nobody discovers it by reading the source and assumes it is a
            # supported way to pass production secrets around.
            collected[name] = value
            continue
        if not sys.stdin.isatty():
            print(
                "FAIL cannot read secret %r without a terminal. Run this command "
                "yourself in a terminal, or export %s for this session. A secret must "
                "not be relayed through an agent conversation."
                % (name, env_candidates(service, name)[0]),
                file=sys.stderr,
            )
            return 2
        entered = getpass.getpass("Value for %s.%s (hidden): " % (profile, name))
        if not entered:
            print("FAIL empty value for %r; nothing was stored." % name, file=sys.stderr)
            return 2
        collected[name] = entered

    try:
        store_identity(profile, service, plain, collected, backend=backend,
                       resource=args.resource or "", account=args.account or "")
    except BackendError as error:
        print("FAIL %s" % error, file=sys.stderr)
        return 2

    print("Stored identity %r for service %r." % (profile, service))
    if collected:
        print("  secret field(s) %s -> %s" % (", ".join(sorted(collected)), backend.label))
    if plain:
        print("  non-secret field(s) %s -> %s" % (", ".join(sorted(plain)), profiles_path()))
    print("  no secret value was printed, logged, or written to any repository")
    return 0


def cmd_bind(args) -> int:
    service = args.service.strip().lower()
    profile = args.profile.strip().lower()
    if not SERVICE_NAME_RE.match(service) or not PROFILE_NAME_RE.match(profile):
        print("FAIL invalid service or profile name", file=sys.stderr)
        return 2
    state = load_profiles()
    if profile not in state.get("profiles", {}):
        print(
            "FAIL no identity named %r. Create it first: agent-skills access set "
            "--profile %s --service %s ..." % (profile, profile, service),
            file=sys.stderr,
        )
        return 1
    identity = project_identity(Path(args.cwd))
    bindings = load_bindings()
    projects = bindings.setdefault("projects", {})
    entry = projects.get(identity["key"])
    if not isinstance(entry, dict):
        entry = {}
    entry[service] = profile
    entry["_root"] = identity["root"]
    entry["_updated_at"] = utc_now()
    projects[identity["key"]] = entry
    save_bindings(bindings)
    print("Bound service %r to identity %r for this repository." % (service, profile))
    print("  repository key: %s" % identity["key"])
    print("  binding stored in %s (user-global, contains no secret)" % bindings_path())
    return 0


def cmd_unbind(args) -> int:
    service = args.service.strip().lower()
    identity = project_identity(Path(args.cwd))
    bindings = load_bindings()
    entry = bindings.get("projects", {}).get(identity["key"])
    if not isinstance(entry, dict) or service not in entry:
        print("No binding for service %r in this repository." % service)
        return 0
    del entry[service]
    save_bindings(bindings)
    print("Removed the %r binding for %s." % (service, identity["key"]))
    return 0


def cmd_forget(args) -> int:
    if not args.profile:
        # `forget <system>` / `forget --all` remove confirmed route knowledge
        # (Access Discovery). Identities are only ever removed by --profile.
        if args.system and args.all:
            print("FAIL pass a system id or --all, not both", file=sys.stderr)
            return 2
        import access_discovery_cli
        return access_discovery_cli.cmd_forget_routes(args)
    if args.system or args.all:
        print("FAIL --profile removes one identity; it cannot be combined with a system id or --all",
              file=sys.stderr)
        return 2
    profile = args.profile.strip().lower()
    if not PROFILE_NAME_RE.match(profile):
        print("FAIL invalid profile name", file=sys.stderr)
        return 2
    state = load_profiles()
    profiles = state.get("profiles", {})
    entry = profiles.get(profile)
    if not isinstance(entry, dict):
        print("No identity named %r." % profile)
        return 0
    # Delete each field from the store it actually went into. Using one
    # profile-level backend left secrets behind in any other store the profile
    # had ever written to, unreachable once the metadata was gone.
    removed = 0
    stranded = []
    for field in entry.get("secret_fields") or []:
        backend, error = backend_for_field(entry, field)
        if backend is None:
            stranded.append(field)
            if error:
                print("WARN %s" % error, file=sys.stderr)
            continue
        if backend.delete(profile, field):
            removed += 1
    if stranded:
        print(
            "WARN could not delete %s: the store they were written to is unavailable. "
            "Re-run this command when it is, or remove them with that store's own tools."
            % ", ".join(sorted(stranded)),
            file=sys.stderr,
        )
    del profiles[profile]
    save_profiles(state)

    bindings = load_bindings()
    cleared = 0
    for key, mapping in list(bindings.get("projects", {}).items()):
        if not isinstance(mapping, dict):
            continue
        for service, bound in list(mapping.items()):
            if bound == profile:
                del mapping[service]
                cleared += 1
        if not [k for k in mapping if not k.startswith("_")]:
            del bindings["projects"][key]
    save_bindings(bindings)

    print("Removed identity %r." % profile)
    print("  secret field(s) deleted from the store: %d" % removed)
    print("  project binding(s) cleared: %d" % cleared)
    return 0


def cmd_backend(args) -> int:
    rows = []
    for backend in BACKENDS:
        try:
            available = backend.available()
        except Exception:
            available = False
        rows.append(
            {
                "name": backend.name,
                "label": backend.label,
                "secure": bool(backend.secure),
                "available": bool(available),
            }
        )
    active = select_backend()
    payload = {
        "active": active.name,
        "active_label": active.label,
        "secure": bool(active.secure),
        "config_dir": str(config_dir()),
        "backends": rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    marker = "ok    " if active.secure else "WARN  "
    print("  %ssecret storage: %s" % (marker, active.label))
    if not active.secure:
        print("        Values live in %s with mode 0600, outside every repository."
              % fallback_secrets_dir())
        print("        Install a keyring (libsecret) for OS-managed storage.")
    for row in rows:
        if row["name"] == active.name:
            continue
        state = "available" if row["available"] else "unavailable"
        print("  --    %s: %s" % (row["name"], state))
    print("  --    no secret value is ever printed by this report")
    return 0


LEGACY_IMPORT_MAP = (
    ("jira", ("JIRA_HOST", "host"), ("JIRA_LOGIN", "login"),
     ("JIRA_AUTH_TYPE", "auth_type"), ("JIRA_API_TOKEN", "token")),
    ("confluence", ("CONFLUENCE_HOST", "host"), ("CONFLUENCE_LOGIN", "login"),
     ("CONFLUENCE_API_TOKEN", "token")),
    ("sonar", ("SONAR_HOST_URL", "host"), ("SONAR_TOKEN", "token")),
)


def cmd_import_legacy(args) -> int:
    """Report legacy credentials and, only when asked, move them into identities.

    Read-only by default. Copying a secret into a new store without the user
    saying so would be a surprise, and the legacy file keeps working either way.
    """
    cwd = Path(args.cwd)
    root = git_root(cwd) or cwd
    values, sources, refusals, _repo_keys = read_legacy_sources(root, cwd)
    for refusal in refusals:
        print("skipped: %s" % refusal)
    if refusals:
        print("")
    if not values:
        print("No legacy .env / .env.local / .jira-config.yml was found.")
        return 0

    print("Legacy configuration found in:")
    for source in sorted(set(sources)):
        print("  - %s" % source)
    print("")

    plan = []
    for row in LEGACY_IMPORT_MAP:
        service = row[0]
        mapping = row[1:]
        present = {}
        for env_name, field in mapping:
            if values.get(env_name):
                present[field] = env_name
        if not present:
            continue
        plan.append((service, present))

    if not plan:
        print("Nothing recognisable to import. The resolver still reads these files.")
        return 0

    print("Importable identities (secret values are never displayed):")
    for service, present in plan:
        secret_fields = sorted(f for f in present if is_secret_field(f, set()))
        plain_fields = sorted(f for f in present if f not in secret_fields)
        print("  %s -> profile %r" % (service, "%s-imported" % service))
        if plain_fields:
            print("    non-secret: %s" % ", ".join(plain_fields))
        if secret_fields:
            print("    secret    : %s (%s)" % (", ".join(secret_fields), REDACTED))

    if not args.apply:
        print("")
        print("This was a read-only report. Nothing was copied.")
        print("To import, re-run with --apply. Your legacy files are never deleted,")
        print("and the resolver keeps reading them either way.")
        return 0

    try:
        backend = select_backend(args.backend or "")
    except BackendError as error:
        print("FAIL %s" % error, file=sys.stderr)
        return 2

    state = load_profiles()
    profiles = state.setdefault("profiles", {})

    # Importing must not quietly replace a working identity's stored secret.
    # `--apply` is a yes to "copy my legacy files in", not to "overwrite what I
    # already have"; `--force` is how you say the second thing.
    if not getattr(args, "force", False):
        clashes = [
            "%s-imported" % service
            for service, _present in plan
            if isinstance(profiles.get("%s-imported" % service), dict)
        ]
        if clashes:
            print("")
            print("FAIL these identities already exist: %s" % ", ".join(sorted(clashes)),
                  file=sys.stderr)
            print("      Importing would replace their stored secrets. Re-run with "
                  "--force to overwrite, or remove them first:", file=sys.stderr)
            for name in sorted(clashes):
                print("        agent-skills access forget --profile %s" % name, file=sys.stderr)
            return 2

    imported = 0
    for service, present in plan:
        profile = "%s-imported" % service
        entry = profiles.get(profile)
        if not isinstance(entry, dict):
            entry = {"created_at": utc_now()}
        plain = {}
        secret_names = []
        for field, env_name in sorted(present.items()):
            value = values[env_name]
            if is_secret_field(field, set()):
                try:
                    backend.store(profile, field, value)
                except BackendError as error:
                    print("FAIL %s" % error, file=sys.stderr)
                    return 2
                secret_names.append(field)
            else:
                plain[field] = value
        entry["name"] = profile
        entry["service"] = service
        if plain.get("host"):
            entry["resource"] = plain["host"]
        if plain.get("login"):
            entry["account"] = plain["login"]
        entry["fields"] = plain
        entry["secret_fields"] = sorted(set((entry.get("secret_fields") or []) + secret_names))
        per_field = entry.get("secret_backends")
        if not isinstance(per_field, dict):
            per_field = {}
        for field in secret_names:
            per_field[field] = backend.name
        if per_field:
            entry["secret_backends"] = per_field
        entry["backend"] = backend.name
        entry["updated_at"] = utc_now()
        entry["imported_from"] = "legacy .env"
        profiles[profile] = entry
        imported += 1
    save_profiles(state)

    print("")
    print("Imported %d identity(ies) into %s." % (imported, backend.label))
    print("Legacy files were left in place and not modified.")
    print("Rotate any token you believe was exposed while it sat in plaintext.")
    return 0


def cmd_check_permissions(args) -> int:
    """Report on the permissions of the state this tool owns."""
    problems = 0
    directory = config_dir()
    if not directory.exists():
        print("  ok    no credential state exists yet")
        return 0
    mode = stat.S_IMODE(directory.stat().st_mode)
    if mode & 0o077:
        print("  FAIL  %s is group/world accessible (mode %o)" % (directory, mode),
              file=sys.stderr)
        problems += 1
    else:
        print("  ok    %s mode %o" % (directory, mode))
    for path in [profiles_path(), bindings_path()]:
        if not path.exists():
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            print("  FAIL  %s is group/world readable (mode %o)" % (path, mode),
                  file=sys.stderr)
            problems += 1
        else:
            print("  ok    %s mode %o" % (path.name, mode))
    secrets_dir = fallback_secrets_dir()
    if secrets_dir.exists():
        for path in sorted(secrets_dir.glob("*.json")):
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                print("  FAIL  %s is group/world readable (mode %o)" % (path.name, mode),
                      file=sys.stderr)
                problems += 1
            else:
                print("  ok    %s mode %o" % (path.name, mode))
    return 1 if problems else 0


def split_list(value) -> list:
    if not value:
        return []
    parts = []
    for chunk in value:
        for item in str(chunk).split(","):
            item = item.strip().lower()
            if item:
                parts.append(item)
    return parts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-skills access",
        description="Resolve access to an external service, lazily and generically.",
    )
    parser.add_argument(
        "--cwd", default=os.getcwd(), help="Directory to treat as the working repository."
    )
    subparsers = parser.add_subparsers(dest="command")

    resolve = subparsers.add_parser("resolve", help="Resolve access for one service.")
    resolve.add_argument("--service", required=True)
    resolve.add_argument("--resource", default="", help="Host, URL, or resource identifier.")
    resolve.add_argument(
        "--require", action="append", default=[],
        help="Required field names, comma-separated or repeated. Default: host,token",
    )
    resolve.add_argument(
        "--secret", action="append", default=[],
        help="Field names that must be treated as secret.",
    )
    resolve.add_argument(
        "--no-capability", action="store_true",
        help="Skip the already-authenticated-tool probe (for tests and diagnosis).",
    )
    resolve.add_argument("--json", action="store_true")
    resolve.set_defaults(func=cmd_resolve)

    profiles = subparsers.add_parser("profiles", help="List credential identities.")
    profiles.add_argument("--json", action="store_true")
    profiles.set_defaults(func=cmd_profiles)

    setter = subparsers.add_parser("set", help="Create or update a credential identity.")
    setter.add_argument("--profile", required=True)
    setter.add_argument("--service", required=True)
    setter.add_argument("--resource", default="")
    setter.add_argument("--account", default="")
    setter.add_argument("--field", action="append", default=[], help="name=value (non-secret).")
    setter.add_argument(
        "--secret-field", action="append", default=[],
        help="Field name whose value is read with hidden input.",
    )
    setter.add_argument("--backend", default="", help="Force a secret backend by name.")
    setter.set_defaults(func=cmd_set)

    bind = subparsers.add_parser("bind", help="Bind a service to an identity for this repo.")
    bind.add_argument("--service", required=True)
    bind.add_argument("--profile", required=True)
    bind.set_defaults(func=cmd_bind)

    unbind = subparsers.add_parser("unbind", help="Remove a service binding for this repo.")
    unbind.add_argument("--service", required=True)
    unbind.set_defaults(func=cmd_unbind)

    forget = subparsers.add_parser(
        "forget",
        help="Delete an identity and its secrets (--profile), or forget confirmed route knowledge "
             "(<system> or --all).",
    )
    forget.add_argument("--profile", default="")
    forget.add_argument("system", nargs="?", default="",
                        help="forget confirmed route knowledge for this system (never an identity)")
    forget.add_argument("--all", action="store_true",
                        help="forget all confirmed route knowledge (never identities)")
    forget.add_argument("--json", action="store_true")
    forget.set_defaults(func=cmd_forget)

    backend = subparsers.add_parser("backend", help="Report the secret-storage backend.")
    backend.add_argument("--json", action="store_true")
    backend.set_defaults(func=cmd_backend)

    legacy = subparsers.add_parser(
        "import-legacy", help="Review legacy .env credentials and optionally import them."
    )
    legacy.add_argument("--apply", action="store_true", help="Actually import (opt-in).")
    legacy.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing <service>-imported identity (replaces its stored secret).",
    )
    legacy.add_argument("--backend", default="")
    legacy.set_defaults(func=cmd_import_legacy)

    perms = subparsers.add_parser(
        "check-permissions", help="Check permissions on credential state."
    )
    perms.set_defaults(func=cmd_check_permissions)

    # Access Discovery: which route can do which operation on which target.
    # Its modules import only the standard library and each other, so loading
    # them for every subcommand costs a few milliseconds and nothing else.
    import access_discovery_cli
    access_discovery_cli.register(subparsers)
    forget.set_defaults(func=access_discovery_cli.json_capable(cmd_forget, "forget"))

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    if not Path(args.cwd).is_dir():
        print("FAIL --cwd is not a directory: %s" % args.cwd, file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
