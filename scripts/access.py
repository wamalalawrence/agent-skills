#!/usr/bin/env python3
"""Resolve access to an external service, lazily and generically.

This is the single access-resolution mechanism every skill uses. It replaced a
per-skill scramble through `.env`, `.jira-config.yml`, and ad-hoc prompting.

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
"""
from __future__ import annotations

import argparse
import getpass
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


def backend_for_profile(entry: dict):
    """Return the backend a stored profile says it used.

    A profile written to the keychain must not silently start reading from the
    file fallback: that is how a "working" credential quietly becomes a
    different, weaker one. Downgrades are reported, never assumed.
    """
    recorded = entry.get("backend", "")
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


# ----------------------------------------------------------------------------
# Repository identity and trust
# ----------------------------------------------------------------------------
def run_git(args, cwd: Path):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


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


def path_is_tracked(path: Path) -> bool:
    """True when git tracks this path.

    Used to enforce the rule that a committed file cannot select a credential
    profile. Checked with git rather than inferred from the filename, because
    `.agent-skills.local.yml` is only trustworthy if it is actually untracked.
    """
    root = git_root(path.parent)
    if root is None:
        return False
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    listed = run_git(["ls-files", "--error-unmatch", str(relative)], root)
    return bool(listed)


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

MCP_CONFIG_CANDIDATES = (
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".kiro/settings/mcp.json",
)
MCP_HOME_CANDIDATES = (
    ".kiro/settings/mcp.json",
    ".cursor/mcp.json",
    ".claude.json",
    ".codex/config.toml",
)


def detect_mcp(service: str, cwd: Path):
    """Report host MCP configuration that mentions this service.

    This does not call a tool. It reports that an MCP path may exist so the
    agent tries it before asking for a token, which is the tool-preference order
    in docs/mcp.md.
    """
    root = git_root(cwd) or cwd
    found = []
    for candidate in MCP_CONFIG_CANDIDATES:
        path = root / candidate
        if path.is_file():
            found.append(path)
    for candidate in MCP_HOME_CANDIDATES:
        path = Path.home() / candidate
        if path.is_file():
            found.append(path)
    if not found:
        return None
    needle = service.lower().split("-")[0]
    for path in found:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if needle and needle in text:
            return {
                "kind": "mcp",
                "detail": "host MCP configuration mentions %r (%s)" % (service, path.name),
                "source": str(path),
            }
    return {
        "kind": "mcp-present",
        "detail": "host has MCP configuration; check for a %s tool before storing a secret"
                  % service,
        "source": str(found[0]),
    }


def detect_capability(service: str, cwd: Path):
    lowered = service.lower()
    for needles, kind, detail, probe in CAPABILITY_PROBES:
        if not any(needle in lowered for needle in needles):
            continue
        try:
            if probe():
                return {"kind": kind, "detail": detail, "source": "cli"}
        except Exception:
            continue
    return detect_mcp(service, cwd)


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
    if path_is_tracked(path):
        return {}, (
            "%s is tracked by git and was ignored. A committed file must not "
            "carry credentials or name a credential profile. Remove it from git "
            "and add it to .gitignore." % path.name
        )
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
    for directory in legacy_config_candidates(root, cwd):
        for name in (".env", ".env.local"):
            path = directory / name
            if path.is_file():
                found = read_env_file(path)
                if found:
                    values.update(found)
                    sources.append(str(path))
        jira_config = directory / ".jira-config.yml"
        if jira_config.is_file():
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
    return values, sources


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
            "next_steps": self.next_steps,
            "authorization": (
                "Resolution answers authentication only. It grants no "
                "permission to perform destructive actions. See "
                "docs/destructive-action-safety.md."
            ),
        }


def resolve_access(service, resource, required, secrets, cwd, allow_capability=True):
    """Walk the documented precedence order once, top to bottom."""
    resolution = Resolution(service, resource)
    root = git_root(cwd) or cwd
    profiles_state = load_profiles()
    profiles = profiles_state.get("profiles", {})

    # 1. An already-authenticated tool or session beats storing another secret.
    if allow_capability:
        capability = detect_capability(service, cwd)
        if capability and capability["kind"] not in ("mcp-present",):
            resolution.status = "resolved"
            resolution.via = capability["kind"]
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

    legacy_values, legacy_sources = read_legacy_sources(root, cwd)
    if legacy_values:
        for field in required:
            if field in found:
                continue
            for name in env_candidates(service, field):
                if legacy_values.get(name):
                    found[field] = legacy_values[name]
                    resolution.sources[field] = "legacy-config:%s" % name
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

    if profile_name is not None:
        entry = profiles[profile_name]
        resolution.profile = profile_name
        resolution.notes.append("using identity %r (%s)" % (profile_name, binding_source))
        backend, downgrade_error = backend_for_profile(entry)
        if downgrade_error:
            resolution.notes.append(downgrade_error)
        else:
            stored_fields = entry.get("fields", {})
            if isinstance(stored_fields, dict):
                for field, value in sorted(stored_fields.items()):
                    if field in found or field not in required:
                        continue
                    if value:
                        found[field] = str(value)
                        resolution.sources[field] = "identity:%s" % profile_name
            for field in entry.get("secret_fields", []) or []:
                if field in found or field not in required:
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
            print("FAIL --field expects name=value with a simple name, got %r" % item,
                  file=sys.stderr)
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

    for name, value in collected.items():
        try:
            backend.store(profile, name, value)
        except BackendError as error:
            print("FAIL %s" % error, file=sys.stderr)
            return 2

    state = load_profiles()
    profiles = state.setdefault("profiles", {})
    entry = profiles.get(profile)
    if not isinstance(entry, dict):
        entry = {"created_at": utc_now()}
    entry["name"] = profile
    entry["service"] = service
    if args.resource:
        entry["resource"] = args.resource.strip()
    if args.account:
        entry["account"] = args.account.strip()
    merged_fields = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
    merged_fields.update(plain)
    entry["fields"] = merged_fields
    existing_secrets = entry.get("secret_fields") or []
    entry["secret_fields"] = sorted(set(list(existing_secrets) + list(collected)))
    if collected or not entry.get("backend"):
        entry["backend"] = backend.name
    entry["updated_at"] = utc_now()
    profiles[profile] = entry
    save_profiles(state)

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
    backend, error = backend_for_profile(entry)
    removed = 0
    if backend is not None:
        for field in entry.get("secret_fields") or []:
            if backend.delete(profile, field):
                removed += 1
    elif error:
        print("WARN %s" % error, file=sys.stderr)
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
    values, sources = read_legacy_sources(root, cwd)
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

    forget = subparsers.add_parser("forget", help="Delete an identity and its secrets.")
    forget.add_argument("--profile", required=True)
    forget.set_defaults(func=cmd_forget)

    backend = subparsers.add_parser("backend", help="Report the secret-storage backend.")
    backend.add_argument("--json", action="store_true")
    backend.set_defaults(func=cmd_backend)

    legacy = subparsers.add_parser(
        "import-legacy", help="Review legacy .env credentials and optionally import them."
    )
    legacy.add_argument("--apply", action="store_true", help="Actually import (opt-in).")
    legacy.add_argument("--backend", default="")
    legacy.set_defaults(func=cmd_import_legacy)

    perms = subparsers.add_parser(
        "check-permissions", help="Check permissions on credential state."
    )
    perms.set_defaults(func=cmd_check_permissions)

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
