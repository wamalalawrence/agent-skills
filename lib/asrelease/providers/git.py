"""Git release provider.

Resolves releases from git tags and fetches the payload with a shallow clone.
It is deliberately built on plain git rather than the GitHub API, so the same
code path serves an https remote, an ssh remote, a self-hosted git server, and
a local bare repository. GitHub is a URL here, not an architecture.

Authentication is DISTRIBUTION ACCESS: proof that this machine may download the
product. It is not project or service access, it is never stored in Agent
Skills configuration, and installing Agent Skills never asks for it. The
provider uses credentials the developer has already configured, in the least
intrusive order it can:

  1. ``native``  — git's own credential helpers and ssh-agent. This covers a
                   configured Git Credential Manager, macOS keychain, an ssh
                   remote, and ``gh auth setup-git``. Nothing is read by us.
  2. ``gh``      — the GitHub CLI, when it is installed and already logged in
                   and the remote is a github.com https URL. The token is
                   supplied to git through an askpass helper that shells out to
                   ``gh auth token``, so it never enters this process, never
                   appears in a command line visible to ``ps``, and is never
                   written to disk.

There is no token prompt and no ``GH_TOKEN`` requirement. If neither strategy
works the provider reports AUTHENTICATION_REQUIRED and exits 3 — it never hangs
waiting for a credential and never reports a private repository as missing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from ..exits import Exit
from ..archive import copy_payload
from ..release import (
    PAYLOAD_ENTRIES,
    ReleaseRef,
    StagedRelease,
    build_manifest,
    channel_of,
    normalise_version,
    parse_version,
    require_version,
    versions_equal,
    write_manifest,
)
from . import AuthState, ProviderError, ReleaseProvider

DEFAULT_REPO_URL = "https://github.com/wamalalawrence/agent-skills.git"

TAG_RE = re.compile(r"^refs/tags/(v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")

# Strings git and its transports use when the answer is "you are not allowed",
# as opposed to "the network is down". GitHub answers an unauthenticated
# request for a private repository with a 404, so "repository not found" has to
# live in this list: reporting that as a missing repository is the exact failure
# mode this provider is required not to have.
_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "permission denied (publickey)",
    "permission denied, please try again",
    "invalid username or password",
    "repository not found",
    "access denied",
    "403 forbidden",
    "401 unauthorized",
    "not authorized",
    "you must have push access",
)

_NETWORK_MARKERS = (
    "could not resolve host",
    "connection refused",
    "connection timed out",
    "operation timed out",
    "network is unreachable",
    "failed to connect",
    "temporary failure in name resolution",
    "ssl",
    "unable to access",
)

# Anything that looks like a credential is scrubbed before a git message is
# shown or logged. Git does echo the remote URL, and a URL can carry a token.
_REDACTIONS = (
    (re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1<redacted>@"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "<redacted-token>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "<redacted-token>"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), "<redacted-token>"),
    (re.compile(r"\b[A-Za-z0-9_\-]{0,8}(?:token|secret|password)[\"'\s:=]+\S{8,}", re.I),
     "<redacted-secret>"),
)


def redact(text: str) -> str:
    """Remove credential-shaped substrings from text before it is shown."""
    out = text or ""
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out


class GitReleaseProvider(ReleaseProvider):
    id = "git"

    def __init__(self, repo: str = "", **_ignored):
        self.repo = repo or os.environ.get("AGENT_SKILLS_RELEASE_REPO") or DEFAULT_REPO_URL
        self.description = "git remote {}".format(self.repo)
        self._strategy = None
        self._last_error = ""
        if not shutil.which("git"):
            raise ProviderError(
                "git is required to fetch releases from a git remote", Exit.USAGE
            )

    # --------------------------------------------------------------------------
    # Process plumbing
    # --------------------------------------------------------------------------
    def _base_env(self) -> dict:
        env = dict(os.environ)
        # No interactive prompt is allowed anywhere in this provider. An
        # installer that blocks on an invisible credential prompt inside a CI
        # job or an editor's integrated terminal is worse than one that fails.
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"
        env["GIT_CONFIG_NOSYSTEM"] = "0"
        env.setdefault(
            "GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
        )
        # Never let a repository the user merely has open influence a global
        # install: git reads config from the current directory upwards.
        env["GIT_CEILING_DIRECTORIES"] = os.path.expanduser("~")
        return env

    def _gh_ready(self) -> bool:
        if not shutil.which("gh"):
            return False
        if not self.repo.startswith("https://github.com/"):
            return False
        try:
            done = subprocess.run(
                ["gh", "auth", "status"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0

    def _askpass_dir(self):
        """Create a temporary askpass helper that reads the token from `gh`.

        The token is never read into this process, never passed as an argument,
        and never written to a file. git executes the helper, the helper
        executes `gh auth token`, and the value goes straight down the pipe git
        opened. The helper is removed when the context exits.
        """
        directory = tempfile.mkdtemp(prefix="agent-skills-askpass-")
        script = os.path.join(directory, "askpass.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/bin/sh\n"
                "# agent-skills distribution askpass. Supplies the GitHub CLI's\n"
                "# existing token to git without it passing through any other\n"
                "# process argument, environment variable, or file.\n"
                'case "$1" in\n'
                "  *[Uu]sername*) printf 'x-access-token\\n' ;;\n"
                "  *) exec gh auth token ;;\n"
                "esac\n"
            )
        os.chmod(script, 0o700)
        return directory, script

    def _run_git(self, args, strategy: str, cwd: str = None, timeout: int = 300):
        """Run one git command under one auth strategy. Returns (rc, stdout, stderr)."""
        env = self._base_env()
        cleanup = None
        if strategy == "gh":
            cleanup, script = self._askpass_dir()
            env["GIT_ASKPASS"] = script
            env["SSH_ASKPASS"] = script
        else:
            # Under `native`, git must still not fall back to a tty prompt.
            env["GIT_ASKPASS"] = "echo"
        try:
            done = subprocess.run(
                ["git"] + list(args),
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            return (
                done.returncode,
                done.stdout.decode("utf-8", "replace"),
                redact(done.stderr.decode("utf-8", "replace")),
            )
        except subprocess.TimeoutExpired:
            return 124, "", "git timed out after {}s".format(timeout)
        except OSError as exc:
            return 127, "", redact(str(exc))
        finally:
            if cleanup:
                shutil.rmtree(cleanup, ignore_errors=True)

    def _strategies(self):
        yield "native"
        if self._gh_ready():
            yield "gh"

    def _run_with_auth(self, args, cwd: str = None, timeout: int = 300):
        """Try each auth strategy in order. Returns (rc, stdout, stderr, strategy)."""
        last = (1, "", "no auth strategy attempted", "none")
        for strategy in self._strategies():
            rc, out, err = self._run_git(args, strategy, cwd=cwd, timeout=timeout)
            if rc == 0:
                self._strategy = strategy
                return rc, out, err, strategy
            last = (rc, out, err, strategy)
            if not _looks_like_auth(err):
                # A network failure will not be fixed by a different credential.
                break
        self._last_error = last[2]
        return last

    def _fail(self, rc: int, stderr: str, action: str):
        message = redact(stderr).strip().splitlines()
        detail = message[-1] if message else "git exited {}".format(rc)
        if _looks_like_auth(stderr):
            raise ProviderError(
                "AUTHENTICATION_REQUIRED: this machine is not authorised to read {}".format(
                    self.repo
                ),
                Exit.AUTH_REQUIRED,
                hint=(
                    "Agent Skills needs read access to its own release source. This is\n"
                    "  distribution access only; it is never used for your projects and is\n"
                    "  never stored in Agent Skills configuration. Authenticate the way you\n"
                    "  already authenticate to git, then retry:\n"
                    "    gh auth login              (then: gh auth setup-git)\n"
                    "    or configure a git credential helper for this remote\n"
                    "    or use an ssh remote with a key your agent already holds\n"
                    "  If the URL itself is wrong, pass --repo. git said: {}".format(detail)
                ),
            )
        if _looks_like_network(stderr) or rc == 124:
            raise ProviderError(
                "could not reach {} while trying to {}".format(self.repo, action),
                Exit.NETWORK,
                hint="git said: {}".format(detail),
            )
        raise ProviderError(
            "git failed while trying to {}".format(action),
            Exit.NETWORK,
            hint="git said: {}".format(detail),
        )

    # --------------------------------------------------------------------------
    # ReleaseProvider contract
    # --------------------------------------------------------------------------
    def auth_state(self) -> str:
        """Can this machine read the release source right now? No secret is shown."""
        rc, _out, err, _strategy = self._run_with_auth(
            ["ls-remote", "--heads", "--refs", self.repo, "HEAD"], timeout=45
        )
        if rc == 0:
            return AuthState.AVAILABLE
        if _looks_like_auth(err):
            return AuthState.REQUIRED
        return AuthState.UNKNOWN

    def _tags(self):
        """Every release tag on the remote, as (version, ref, commit).

        Listed without ``--refs`` on purpose. An annotated tag — which is what
        a signed or message-carrying release tag is — has its own object, and
        ``ls-remote --refs`` reports that object's id, not the commit it points
        at. Comparing that id against the commit a clone checks out would flag
        every annotated release as a moved tag. The peeled ``^{}`` entry is the
        commit, so it is preferred wherever the remote offers one.
        """
        rc, out, err, _strategy = self._run_with_auth(
            ["ls-remote", "--tags", self.repo], timeout=90
        )
        if rc != 0:
            self._fail(rc, err, "list releases")
        objects = {}
        peeled = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            sha, ref = parts
            if ref.endswith("^{}"):
                match = TAG_RE.match(ref[:-3])
                if match:
                    peeled[ref[:-3]] = sha
                continue
            match = TAG_RE.match(ref)
            if not match:
                continue
            version = normalise_version(match.group(1))
            if parse_version(version) is None:
                continue
            objects[ref] = (version, sha)

        versions = []
        for ref, (version, sha) in objects.items():
            versions.append((version, ref, peeled.get(ref, sha)))
        versions.sort(key=lambda item: parse_version(item[0]))
        return versions

    def available_versions(self):
        return [version for version, _ref, _sha in self._tags()]

    def resolve_latest(self, channel: str = "stable") -> ReleaseRef:
        tags = self._tags()
        if not tags:
            raise ProviderError(
                "no release tags found at {}".format(self.repo), Exit.NETWORK
            )
        if channel and channel != "any":
            # The rc channel is a superset: someone tracking rc must be offered
            # a stable release that supersedes the last rc, or they would be
            # pinned to pre-releases forever.
            if channel == "stable":
                candidates = [t for t in tags if channel_of(t[0]) == "stable"]
            else:
                candidates = list(tags)
        else:
            candidates = list(tags)
        if not candidates:
            raise ProviderError(
                "no {} release found at {}".format(channel, self.repo), Exit.NETWORK
            )
        version, ref, sha = candidates[-1]
        return ReleaseRef(version, self.id, ref, channel=channel_of(version), commit=sha)

    def resolve_version(self, version: str) -> ReleaseRef:
        """The release the operator named, or a refusal. Never a near miss.

        The wanted version is validated before any comparison happens. It has
        to be: ``compare_versions`` reports an unparseable operand as *equal*,
        so a typo compared against every tag matched the first one and installed
        whatever release happened to sort earliest. ``--version X`` means that
        release or nothing.
        """
        wanted = require_version(version, "--version")
        for found, ref, sha in self._tags():
            if versions_equal(found, wanted):
                return ReleaseRef(found, self.id, ref, channel=channel_of(found), commit=sha)
        raise ProviderError(
            "no release {} at {}".format(wanted, self.repo),
            Exit.USAGE,
            hint="list what is available with: agent-skills versions",
        )

    def fetch_release(self, ref: ReleaseRef, dest: str) -> StagedRelease:
        os.makedirs(dest, exist_ok=True)
        work = tempfile.mkdtemp(prefix="agent-skills-fetch-", dir=os.path.dirname(dest) or None)
        checkout = os.path.join(work, "src")
        tag = ref.ref if ref.ref.startswith("refs/") else "refs/tags/v{}".format(ref.version)
        short = tag.rsplit("/", 1)[-1]
        try:
            rc, _out, err, _strategy = self._run_with_auth(
                [
                    "clone",
                    "--quiet",
                    "--depth",
                    "1",
                    "--no-tags",
                    "--branch",
                    short,
                    "--config",
                    "advice.detachedHead=false",
                    self.repo,
                    checkout,
                ],
                timeout=900,
            )
            if rc != 0:
                self._fail(rc, err, "download release {}".format(ref.version))

            commit = ""
            rc, out, _err = self._run_git(["rev-parse", "HEAD"], "native", cwd=checkout, timeout=30)
            if rc == 0:
                commit = out.strip()
            # The tag the provider resolved and the commit actually checked out
            # must be the same object. A tag that moved between resolve and
            # fetch is exactly the shape of a downgrade or substitution attack.
            if ref.commit and commit and not commit.startswith(ref.commit[:12]):
                rc, out, _err = self._run_git(
                    ["rev-list", "-n", "1", short], "native", cwd=checkout, timeout=30
                )
                if rc != 0 or not out.strip().startswith(ref.commit[:12]):
                    raise ProviderError(
                        "release {} resolved to {} but delivered {}".format(
                            ref.version, ref.commit[:12], commit[:12]
                        ),
                        Exit.INTEGRITY,
                        hint="the tag moved between resolution and download; do not install it",
                    )

            copy_payload(checkout, dest, PAYLOAD_ENTRIES)
            resolved = ReleaseRef(
                ref.version, self.id, tag, channel=ref.channel, commit=commit or ref.commit
            )
            manifest = build_manifest(
                dest,
                resolved,
                extra={
                    "source": {
                        "repo": self.repo,
                        "ref": tag,
                        "commit": commit or ref.commit,
                    }
                },
            )
            write_manifest(dest, manifest)
            return StagedRelease(dest, resolved, manifest)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _looks_like_auth(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(marker in low for marker in _AUTH_MARKERS)


def _looks_like_network(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(marker in low for marker in _NETWORK_MARKERS)
