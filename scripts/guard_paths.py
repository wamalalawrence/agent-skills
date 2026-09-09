#!/usr/bin/env python3
"""Target classification for Execution Guard.

`rm -rf ./build` and `rm -rf /` are the same verb against very different blast
radii, so a guard that decides on the verb alone is either useless or
unusable. This module answers one question about each argument a destructive
command was given:

    where does this actually point?

"Actually" is the whole point. Three ways a textual path lies:

  * **Relative form.** `../../..` inside a repository is outside it.
  * **Symlink.** `repo/tmp -> /important/data` looks repo-local and is not.
    Every classification therefore runs `os.path.realpath` and compares the
    resolved path, not the string, against the workspace boundary.
  * **Unresolvable form.** `$DIR`, `*`, `"${BUILD}"`. These are not guessed at.
    They are reported as unresolved with the most specific ancestor that *can*
    be resolved, and the rules decide what an unresolved target is worth.

Classifications, from most to least dangerous:

    SYSTEM_ROOT          /, /usr, /etc, /var, C:\\, a volume root
    HOME_ROOT            $HOME itself, or a protected dotdir inside it
    OUTSIDE_WORKSPACE    resolves outside the repository being worked in
    TEMP                 inside /tmp or $TMPDIR
    WORKSPACE_DISPOSABLE inside the workspace, and a build/cache directory
    WORKSPACE            inside the workspace, everything else
    UNRESOLVED           a glob or variable that was not expanded
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SYSTEM_ROOT = "SYSTEM_ROOT"
HOME_ROOT = "HOME_ROOT"
OUTSIDE_WORKSPACE = "OUTSIDE_WORKSPACE"
TEMP = "TEMP"
WORKSPACE_DISPOSABLE = "WORKSPACE_DISPOSABLE"
WORKSPACE = "WORKSPACE"
UNRESOLVED = "UNRESOLVED"

# Ordered worst-first, so a command with several targets is scored by its worst.
SEVERITY_ORDER = (
    SYSTEM_ROOT,
    HOME_ROOT,
    OUTSIDE_WORKSPACE,
    UNRESOLVED,
    TEMP,
    WORKSPACE,
    WORKSPACE_DISPOSABLE,
)

# Absolute paths that must never be the target of a recursive delete or a
# format, whatever the workspace is. Children of these are system paths too;
# `/etc/nginx` is not safer than `/etc`.
SYSTEM_PREFIXES = (
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/opt", "/proc",
    "/root", "/sbin", "/srv", "/sys", "/usr", "/var", "/run",
    "/System", "/Library", "/Applications", "/Volumes", "/private",
    "/network", "/cores",
)

# Directories under $HOME that hold credentials, keys, or host configuration.
# Deleting or overwriting one is a credential-loss event, not a cleanup.
PROTECTED_HOME_DIRS = (
    ".ssh", ".aws", ".gnupg", ".gpg", ".kube", ".docker", ".config", ".gcloud",
    ".azure", ".npmrc", ".netrc", ".git-credentials", ".password-store",
    ".agent-skills", ".claude", ".codex", ".cursor", ".kiro", ".local",
    "Documents", "Desktop", "Downloads", "Library", "Pictures", "Movies",
    "Music", "Applications",
)

# Directory names that a build regenerates. Deleting one is ordinary work, and a
# guard that asks about it will be switched off within a day.
DISPOSABLE_DIRS = {
    "build", "dist", "out", "output", "target", "bin", "obj", "coverage",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".next", ".nuxt", ".svelte-kit", ".parcel-cache", ".turbo", ".cache",
    ".gradle", ".terraform", "vendor", ".venv", "venv", ".tox", ".nox",
    "tmp", "temp", ".tmp", "htmlcov", ".coverage", "test-results",
    "generated", ".angular", ".vite", "cmake-build-debug", ".nyc_output",
    ".sass-cache", ".eslintcache", "reports", "logs", ".dart_tool", "Pods",
    "DerivedData", ".terragrunt-cache", "__snapshots__.tmp", ".jest-cache",
}

GLOB_CHARS = re.compile(r"[*?\[\]]")
VARIABLE_RE = re.compile(r"\$\{?[A-Za-z_?][A-Za-z0-9_]*\}?|\$[0-9@*#]")

# Variables the guard expands itself, because leaving them unresolved would turn
# the single most dangerous command in the corpus (`rm -rf $HOME`) into a
# merely-unresolved one.
_SAFE_EXPANSIONS = ("HOME", "PWD", "OLDPWD", "TMPDIR", "USER", "LOGNAME")


@dataclass
class Target:
    """One resolved argument of a command, plus how it was resolved."""

    raw: str
    expanded: str
    resolved: str | None
    classification: str
    escaped_via_symlink: bool = False
    unresolved_reason: str | None = None

    @property
    def display(self) -> str:
        if self.resolved and self.resolved != self.expanded:
            return "%s -> %s" % (self.raw, self.resolved)
        return self.raw


@dataclass
class Workspace:
    """Where the command runs, and what counts as inside it."""

    cwd: str
    root: str
    is_repository: bool

    @property
    def root_real(self) -> str:
        return os.path.realpath(self.root)


def _git_toplevel(cwd: str) -> str | None:
    """The repository root above `cwd`, found by walking up for a `.git` entry.

    Deliberately not `git rev-parse --show-toplevel`. This runs before every
    shell command, and a subprocess costs more than the entire rule evaluation
    that follows it — around fifteen milliseconds against a few microseconds of
    `stat`. A `.git` *file* counts as well as a directory, so worktrees and
    submodules resolve to their own root.
    """
    current = os.path.abspath(cwd)
    seen = 0
    while seen < 64:
        marker = os.path.join(current, ".git")
        if os.path.exists(marker):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
        seen += 1
    return None


def resolve_workspace(cwd: str | None, root_hint: str | None = None) -> Workspace:
    """Determine the workspace boundary for a command.

    The repository root, when there is one, is the boundary a developer means by
    "my project". Outside a repository the boundary is the working directory
    itself, which is stricter, not looser: anything above it is outside.
    """
    where = os.path.abspath(os.path.expanduser(cwd or os.getcwd()))
    if root_hint:
        hint = os.path.abspath(os.path.expanduser(root_hint))
        return Workspace(cwd=where, root=hint, is_repository=True)
    top = _git_toplevel(where) if os.path.isdir(where) else None
    if top:
        return Workspace(cwd=where, root=os.path.abspath(top), is_repository=True)
    return Workspace(cwd=where, root=where, is_repository=False)


def _home() -> str:
    """The home directory, canonicalised.

    Canonicalised because every comparison against it is made against a
    `realpath`. Leaving this one uncanonicalised makes the comparison fail
    whenever $HOME contains a symlink — which silently disables the rule that
    protects `~/.ssh` and `~/.aws`.
    """
    return os.path.realpath(os.path.expanduser("~"))


def _expand(raw: str) -> tuple[str, str | None]:
    """Expand `~` and a small set of known variables. Returns (text, reason).

    `reason` is set when something was left unexpanded, which is a fact the
    rules need rather than an error.
    """
    text = raw
    if text.startswith("~"):
        text = os.path.expanduser(text)
    for name in _SAFE_EXPANSIONS:
        value = os.environ.get(name)
        if not value:
            continue
        text = text.replace("${%s}" % name, value).replace("$%s" % name, value)
    if VARIABLE_RE.search(text):
        return text, "contains an unexpanded shell variable"
    return text, None


def _normalise_prefix(path: str) -> str:
    return path.rstrip("/") or "/"


def _is_under(path: str, prefix: str) -> bool:
    path = _normalise_prefix(path)
    prefix = _normalise_prefix(prefix)
    if prefix == "/":
        return path.startswith("/")
    return path == prefix or path.startswith(prefix + "/")


def _is_under_workspace_lexically(path: str, workspace: Workspace) -> bool:
    """Whether the path, without resolving symlinks, reads as workspace-local."""
    return _is_under(path, workspace.root) or _is_under(path, workspace.root_real)


def _is_system_path(path: str) -> bool:
    path = _normalise_prefix(path)
    if path == "/":
        return True
    if re.match(r"^[A-Za-z]:[\\/]*$", path):
        return True
    home = _home()
    for prefix in SYSTEM_PREFIXES:
        if prefix == "/":
            continue
        if _is_under(path, prefix):
            # A user's own home may sit under /home or /Users; that is the
            # HOME_ROOT case, not the SYSTEM_ROOT one, and is classified below.
            if _is_under(path, home):
                return False
            return True
    # /home and /Users themselves are system-level: deleting them removes every
    # account's data, which is worse than deleting one home.
    for prefix in ("/home", "/Users"):
        if _normalise_prefix(path) == prefix:
            return True
    return False


def _is_home_sensitive(path: str) -> bool:
    home = _home()
    path = _normalise_prefix(path)
    if path == _normalise_prefix(home):
        return True
    if not _is_under(path, home):
        return False
    relative = os.path.relpath(path, home)
    first = relative.split(os.sep, 1)[0]
    return first in PROTECTED_HOME_DIRS


def _is_disposable(path: str, workspace: Workspace) -> bool:
    try:
        relative = os.path.relpath(path, workspace.root_real)
    except ValueError:
        return False
    if relative.startswith(".."):
        return False
    parts = [part for part in relative.split(os.sep) if part not in (".", "")]
    return any(part in DISPOSABLE_DIRS for part in parts)


def _temp_roots() -> list[str]:
    roots = ["/tmp", "/var/tmp", "/private/tmp", "/private/var/tmp"]
    env_tmp = os.environ.get("TMPDIR")
    if env_tmp:
        roots.append(os.path.realpath(env_tmp))
    return roots


def classify(raw: str, workspace: Workspace) -> Target:
    """Classify one command argument as a filesystem target."""
    expanded, unresolved_reason = _expand(raw)

    has_glob = bool(GLOB_CHARS.search(expanded))
    probe = expanded
    if has_glob:
        # Do not expand the glob: that would stat the filesystem and could be
        # enormous. Judge the most specific ancestor that has no glob in it,
        # which is the directory the glob would sweep.
        head = expanded
        while head and GLOB_CHARS.search(head):
            parent = os.path.dirname(head.rstrip("/"))
            if parent == head:
                break
            head = parent
        probe = head or "."
        if unresolved_reason is None:
            unresolved_reason = "contains an unexpanded glob"

    if not probe:
        probe = "."
    absolute = probe if os.path.isabs(probe) else os.path.join(workspace.cwd, probe)
    absolute = os.path.normpath(absolute)
    resolved = os.path.realpath(absolute)

    # A symlink escape is the case the string cannot show: the path *as written*
    # is inside the workspace and the path it actually reaches is not.
    #
    # The lexical side must be compared against both spellings of the root. On
    # macOS a checkout under `mktemp -d` has an unresolved root of
    # `/var/folders/...` and a real root of `/private/var/folders/...`; comparing
    # only against the real one makes every lexical test fail and silently
    # disables this check — which is the check that catches `repo/tmp` pointing
    # at somewhere it should not.
    escaped = _is_under_workspace_lexically(absolute, workspace) and not _is_under(
        resolved, workspace.root_real
    )

    classification = _classify_resolved(resolved, workspace)
    if classification in (WORKSPACE, WORKSPACE_DISPOSABLE) and unresolved_reason:
        # An unresolved element inside the workspace still widens the blast
        # radius: `rm -rf "$DIR"` in a repo may be anything at all.
        classification = UNRESOLVED

    return Target(
        raw=raw,
        expanded=expanded,
        resolved=resolved,
        classification=classification,
        escaped_via_symlink=escaped,
        unresolved_reason=unresolved_reason,
    )


def workspace_is_trustworthy(workspace: Workspace) -> bool:
    """Whether "inside the workspace" is a meaningful exemption at all.

    The credible signal is that the root is a **repository**. A checkout is a
    project wherever it sits — under `/srv`, under `/opt`, or in a `/var`-backed
    temporary directory on macOS, where every `mktemp` checkout lives. Judging
    such a root as a system path denies `rm -rf build`, which is the most
    ordinary command in the corpus.

    Without a repository the exemption is refused and paths are judged
    absolutely, which is the strict reading: an agent whose cwd is `/` or `/etc`
    must not thereby make the whole machine workspace-local.
    """
    root = _normalise_prefix(workspace.root_real)
    if root == "/" or root == _normalise_prefix(_home()):
        return False
    if workspace.is_repository:
        return True
    return not _is_system_path(root)


def _classify_resolved(resolved: str, workspace: Workspace) -> str:
    # Workspace membership is decided first. A repository legitimately lives
    # under /var (a temp checkout), /opt, /srv (a web root), or a scratch
    # directory, and its own `build/` is not a system path because of where the
    # repository happens to sit. Getting this order wrong denies `rm -rf build`,
    # which is the single most common cleanup command there is.
    inside = _is_under(resolved, workspace.root_real)
    if inside and workspace_is_trustworthy(workspace):
        if _normalise_prefix(resolved) == _normalise_prefix(workspace.root_real):
            # The repository root itself is not disposable, whatever its name.
            return WORKSPACE
        if _is_home_sensitive(resolved):
            # A credential directory nested inside a repository is still one.
            return HOME_ROOT
        if _is_disposable(resolved, workspace):
            return WORKSPACE_DISPOSABLE
        return WORKSPACE
    # Home and credential directories are checked before the temp exemption.
    # Order matters: a home directory that happens to sit inside a temp tree is
    # still the home directory, and `rm -rf ~/.ssh` must not become ordinary
    # scratch cleanup because of where $HOME points.
    if _is_home_sensitive(resolved):
        return HOME_ROOT
    for temp_root in _temp_roots():
        if _normalise_prefix(resolved) == _normalise_prefix(temp_root):
            # The shared temp root itself is system state; emptying it breaks
            # every other process on the machine.
            return SYSTEM_ROOT
        if _is_under(resolved, temp_root):
            return TEMP
    if _is_system_path(resolved):
        return SYSTEM_ROOT
    if not inside:
        return OUTSIDE_WORKSPACE
    return WORKSPACE


def worst(targets: list[Target]) -> Target | None:
    """The target with the widest blast radius, or None when there are none."""
    if not targets:
        return None
    ranking = {name: index for index, name in enumerate(SEVERITY_ORDER)}
    return min(targets, key=lambda t: ranking.get(t.classification, len(SEVERITY_ORDER)))


def path_like(token: str) -> bool:
    """Whether an argument looks like a filesystem target rather than a flag."""
    if not token or token.startswith("-"):
        return False
    if "=" in token and not token.startswith(("/", ".", "~", "$")):
        return False
    return True


def looks_like_repo_root(path: str, workspace: Workspace) -> bool:
    return _normalise_prefix(os.path.realpath(path)) == _normalise_prefix(workspace.root_real)


def relative_to_workspace(path: str, workspace: Workspace) -> str:
    try:
        return os.path.relpath(path, workspace.root_real)
    except ValueError:
        return path


def exists(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False
