#!/usr/bin/env python3
"""GitKnowledgeStore: the v1 organisational knowledge backend.

A knowledge source is an ordinary git repository (docs/knowledge/SETUP.md). This
module is the only place in the runtime that knows that. Branches, commits,
paths inside the source, merge commits, and host CLIs never cross the
`KnowledgeStore` interface.

Git access is the user's own, used exactly as the installer uses it: the git
plumbing, prompt suppression, askpass, redaction, and auth/network
classification are imported from `lib/asrelease/providers/git.py`. Agent Skills
never stores a credential. Two rules differ from the installer, both from the
brief:

  * A push uses only the auth strategy that last succeeded for this source,
    once. A permission failure falls back to a fork (when the host CLI can) or
    the outbox. It is never retried with another credential.
  * The client pushes only to `agent-skills/proposals/...` branches, never to
    the default branch, and never with --force, whatever the permissions allow.

Approval provenance is derived from git history, never from fact content:

  * the latest first-parent commit touching a fact file on the default branch
    is a merge commit -> approved_by = the merge's author, proposed_by = the
    author of the merged-in commit that changed the file;
  * a host-made squash/rebase commit (committer is the host, subject carries a
    PR/MR number) -> approved via that PR, proposed_by = the commit author;
  * a commit whose committer is a different person from its author -> that
    committer approved it;
  * anything else (a direct push by the author) is unreviewed: a CONFIRMED
    claim in it is reported as PROPOSED (DISCOVERY.md D8).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from asrelease.providers import git as release_git  # noqa: E402
from asrelease.providers import ProviderError  # noqa: E402

import knowledge_model as km  # noqa: E402
from durable import LockTimeout, locked  # noqa: E402
from knowledge_store import (  # noqa: E402
    KnowledgeStore,
    ProposalLedger,
    StoreError,
    outbox_dir,
    private_dir,
    read_json,
    sources_dir,
    write_private_json,
)

try:  # stdlib, but a minimal Python build can omit it (DISCOVERY.md §7)
    import sqlite3
except ImportError:  # pragma: no cover - exercised by forcing SQLITE = None
    sqlite3 = None

SQLITE = sqlite3
PROPOSAL_PREFIX = "agent-skills/proposals/"
INDEX_SCHEMA = 1
NETWORK_TIMEOUT = 120
_PUSH_DENIED = (
    "permission denied",
    "permission to",
    "insufficient permission",
    "unable to create temporary object",
    "read-only",
    "you are not allowed to push",
    "you must have push access",
    "403",
    "protected branch",
)
_HOST_COMMITTERS = ("noreply@github.com", "noreply@gitlab.com")
_PR_SUBJECT = (
    re.compile(r"^Merge pull request #(\d+)"),
    re.compile(r"See merge request \S*!(\d+)"),
    re.compile(r"\(#(\d+)\)\s*$"),
    re.compile(r"^Merged PR (\d+):"),
)


# ---------------------------------------------------------------------------
# Git access, reusing the installer's provider
# ---------------------------------------------------------------------------
class GitAccess(release_git.GitReleaseProvider):
    """The installer's git plumbing, pointed at a knowledge source."""

    def __init__(self, url: str) -> None:
        # A URL can come from untrusted content (a pointer file, a manifest's
        # successor). One that starts with "-" would be read by git as an
        # option such as --upload-pack=<program>. Every command below also puts
        # "--" before the URL; this refuses it before any git runs.
        if not isinstance(url, str) or not url.strip() or url.lstrip().startswith("-") or any(
                ord(c) < 32 for c in url):
            raise StoreError("not a usable git URL: {!r}".format(url), "usage")
        try:
            super().__init__(repo=url)
        except ProviderError as exc:
            raise StoreError(exc.message, "usage")

    def remote(self, args: List[str], cwd: Optional[Path] = None, timeout: int = NETWORK_TIMEOUT,
               strategy: Optional[str] = None) -> Tuple[int, str, str, str]:
        """A networked git command. Tries each strategy unless one is pinned."""
        where = str(cwd) if cwd else None
        if strategy:
            rc, out, err = self._run_git(args, strategy, cwd=where, timeout=timeout)
            return rc, out, err, strategy
        return self._run_with_auth(args, cwd=where, timeout=timeout)

    def run_local(self, args: List[str], cwd: Path, timeout: int = 60,
                  env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        base = self._base_env()
        base["GIT_ASKPASS"] = "echo"
        # The clone lives under the user's home, so the installer's ceiling
        # (the home directory itself) is correct here too.
        if env:
            base.update(env)
        try:
            done = subprocess.run(["git"] + args, cwd=str(cwd), env=base, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, "", "git timed out after {}s".format(timeout)
        except OSError as exc:
            return 127, "", release_git.redact(str(exc))
        return (done.returncode, done.stdout.decode("utf-8", "replace"),
                release_git.redact(done.stderr.decode("utf-8", "replace")))


def classify_failure(rc: int, stderr: str) -> str:
    if release_git._looks_like_auth(stderr):
        return "auth"
    if release_git._looks_like_network(stderr) or rc == 124:
        return "network"
    return "state"


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _fail(action: str, url: str, rc: int, stderr: str) -> StoreError:
    kind = classify_failure(rc, stderr)
    detail = _last_line(stderr) or "git exited {}".format(rc)
    if kind == "auth":
        return StoreError(
            "AUTHENTICATION_REQUIRED: your git access cannot {} {}".format(action, url), "auth",
            hint="Agent Skills uses the git access you already have and never stores it. "
                 "Authenticate the way you normally do for this host (credential helper, ssh key, "
                 "or `gh auth login` then `gh auth setup-git`). git said: " + detail)
    if kind == "network":
        return StoreError("could not reach {} to {}".format(url, action), "network",
                          hint="git said: " + detail)
    return StoreError("git failed to {} {}".format(action, url), "state", hint="git said: " + detail)


def web_location(url: str) -> Tuple[str, str]:
    """(host, path) of a remote, for building review URLs."""
    from access import normalise_remote

    key = normalise_remote(url)
    host, _, path = key.partition("/")
    return host, path


# ---------------------------------------------------------------------------
# Review hosts: PR/MR creation through a CLI the user already has
# ---------------------------------------------------------------------------
class HostAdapter:
    name = "none"
    cli = ""

    def __init__(self, repo_slug: str) -> None:
        self.repo_slug = repo_slug

    def available(self) -> bool:
        if not self.cli or not shutil.which(self.cli):
            return False
        try:
            done = subprocess.run([self.cli, "auth", "status"], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0

    def _run(self, args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
        try:
            done = subprocess.run([self.cli] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, "", str(exc)
        return (done.returncode, done.stdout.decode("utf-8", "replace"),
                release_git.redact(done.stderr.decode("utf-8", "replace")))

    def create_pr(self, base: str, head: str, title: str, body: str) -> Optional[str]:
        return None

    def pr_state(self, url: str) -> str:
        return "unknown"

    def fork(self) -> Optional[Tuple[str, str]]:
        return None


class GitHubCli(HostAdapter):
    name = "github"
    cli = "gh"

    def create_pr(self, base: str, head: str, title: str, body: str) -> Optional[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            handle.write(body)
            body_file = handle.name
        try:
            rc, out, _ = self._run(["pr", "create", "--repo", self.repo_slug, "--base", base,
                                    "--head", head, "--title", title, "--body-file", body_file])
        finally:
            os.unlink(body_file)
        return _last_line(out) if rc == 0 and _last_line(out) else None

    def pr_state(self, url: str) -> str:
        rc, out, _ = self._run(["pr", "view", url, "--json", "state", "--jq", ".state"])
        state = out.strip().upper() if rc == 0 else ""
        return {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(state, "unknown")

    def fork(self) -> Optional[Tuple[str, str]]:
        rc, _, _ = self._run(["repo", "fork", self.repo_slug, "--clone=false", "--remote=false"])
        if rc != 0:
            return None
        rc, login, _ = self._run(["api", "user", "--jq", ".login"])
        login = login.strip()
        if rc != 0 or not re.match(r"^[A-Za-z0-9-]{1,39}$", login):
            return None
        name = self.repo_slug.split("/")[-1]
        rc, url, _ = self._run(["repo", "view", "{}/{}".format(login, name), "--json", "url",
                                "--jq", ".url"])
        url = url.strip()
        return (url, login) if rc == 0 and url else None


class GitLabCli(HostAdapter):
    name = "gitlab"
    cli = "glab"

    def create_pr(self, base: str, head: str, title: str, body: str) -> Optional[str]:
        rc, out, _ = self._run(["mr", "create", "--repo", self.repo_slug, "--source-branch", head,
                                "--target-branch", base, "--title", title, "--description", body,
                                "--yes"])
        urls = re.findall(r"https?://\S+", out) if rc == 0 else []
        return urls[-1] if urls else None

    def pr_state(self, url: str) -> str:
        rc, out, _ = self._run(["mr", "view", url, "--output", "json"])
        match = re.search(r'"state"\s*:\s*"(\w+)"', out) if rc == 0 else None
        state = match.group(1).lower() if match else ""
        return {"opened": "open", "merged": "merged", "closed": "closed"}.get(state, "unknown")


def host_adapter(config: dict) -> HostAdapter:
    host, path = web_location(config["url"])
    choice = config.get("review_host") or "auto"
    slug = config.get("review_repo") or path
    if choice == "auto":
        choice = "github" if host == "github.com" else ("gitlab" if "gitlab" in host else "none")
    if choice == "github":
        return GitHubCli(slug)
    if choice == "gitlab":
        return GitLabCli(slug)
    return HostAdapter(slug)


def compare_url(url: str, base: str, branch: str) -> Optional[str]:
    """Where a human opens the review, when no host CLI created it."""
    host, path = web_location(url)
    if not host or "/" not in path:
        return None
    if host == "github.com" or host.startswith("github."):
        return "https://{}/{}/compare/{}...{}?expand=1".format(host, path, base, branch)
    if "gitlab" in host:
        return ("https://{}/{}/-/merge_requests/new?merge_request%5Bsource_branch%5D={}"
                "&merge_request%5Btarget_branch%5D={}".format(host, path, branch, base))
    if host.endswith("azure.com") or host.endswith("visualstudio.com"):
        parts = [p for p in path.split("/") if p not in ("v3", "_git")]
        if len(parts) >= 3:
            return "https://{}/{}/{}/_git/{}/pullrequestcreate?sourceRef={}&targetRef={}".format(
                "dev.azure.com", parts[0], parts[1], parts[-1], branch, base)
    if host.startswith("bitbucket"):
        return "https://{}/{}/pull-requests/new?source={}&dest={}".format(host, path, branch, base)
    return None


def well_known_candidate(remote: str, name: str) -> str:
    """`<same host>/<same org>/<name>`, in the same URL form as `remote`."""
    if not re.match(r"^[A-Za-z0-9._-]{1,100}$", name or ""):
        return ""
    candidate = re.sub(r"[^/:]+?(?:\.git)?/?$", name + ".git", remote.strip())
    return candidate if candidate != remote.strip() else ""


# ---------------------------------------------------------------------------
# Reading a manifest from a remote without adding it
# ---------------------------------------------------------------------------
def remote_manifest(url: str, timeout: int = NETWORK_TIMEOUT) -> Tuple[Optional[dict], str]:
    """(manifest, state) where state is found | absent | missing | auth | network."""
    access = GitAccess(url)
    rc, out, err, _ = access.remote(["ls-remote", "--symref", "--", url, "HEAD"], timeout=timeout)
    if rc != 0:
        kind = classify_failure(rc, err)
        return None, kind if kind in ("auth", "network") else "missing"
    if not out.strip():
        return None, "absent"  # an empty repository
    work = Path(tempfile.mkdtemp(prefix="agent-skills-knowledge-probe-"))
    try:
        rc, _, err, _ = access.remote(["clone", "--quiet", "--depth", "1", "--no-tags", "--", url,
                                       str(work / "c")], timeout=timeout)
        if rc != 0:
            kind = classify_failure(rc, err)
            return None, kind if kind in ("auth", "network") else "missing"
        data = read_json(work / "c" / km.MANIFEST_NAME, None)
        return (data, "found") if isinstance(data, dict) else (None, "absent")
    except StoreError:
        return None, "absent"
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------
class GitKnowledgeStore(KnowledgeStore):
    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.config = config
        self.url = config["url"]
        self.root = sources_dir() / name
        self.clone = self.root / "clone"
        self.index_path = self.root / "index.sqlite"
        self.sync_path = self.root / "sync.json"
        self.lock_path = self.root / "source"
        self.ledger = ProposalLedger()
        self._access: Optional[GitAccess] = None

    @property
    def access(self) -> GitAccess:
        if self._access is None:
            self._access = GitAccess(self.url)
        return self._access

    # -- state --------------------------------------------------------------
    def sync_state(self) -> dict:
        try:
            return read_json(self.sync_path, {}) or {}
        except StoreError:
            return {"error": "sync state unreadable", "error_kind": "state"}

    def _save_sync_state(self, state: dict) -> None:
        write_private_json(self.sync_path, state)

    def manifest(self) -> Optional[dict]:
        if not (self.clone / km.MANIFEST_NAME).exists():
            return None
        try:
            data = read_json(self.clone / km.MANIFEST_NAME, None)
        except StoreError:
            return None
        return data if isinstance(data, dict) else None

    def read_only_reason(self) -> str:
        manifest = self.manifest()
        state = self.sync_state()
        if state.get("auth_lost"):
            return ("access to this source was lost (authentication required on the last sync); "
                    "the cache is read-only. If you have left this source, run: "
                    "agent-skills knowledge sources remove {}".format(self.name))
        if manifest is None:
            return "the source has not been synced, or has no manifest"
        if km.validate_manifest(manifest):
            return "the source manifest is invalid: " + "; ".join(km.validate_manifest(manifest))
        if manifest.get("schema_version", 1) > km.SUPPORTED_SOURCE_SCHEMA:
            return ("this source uses schema version {} and this client writes version {}: reading "
                    "only. Update agent-skills to propose to it.".format(
                        manifest["schema_version"], km.SUPPORTED_SOURCE_SCHEMA))
        if manifest.get("status") == "deprecated":
            return ("this source is deprecated; its successor is {}. Switch with: agent-skills "
                    "knowledge sources add {}".format(manifest.get("successor"), manifest.get("successor")))
        return ""

    def cache_age_seconds(self) -> Optional[int]:
        stamp = self.sync_state().get("last_success_at")
        if not stamp:
            return None
        from datetime import datetime, timezone

        try:
            then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return max(0, int((datetime.now(timezone.utc) - then).total_seconds()))

    def default_branch(self) -> str:
        return self.sync_state().get("default_branch") or "main"

    # -- sync ---------------------------------------------------------------
    def sync(self, timeout: int = NETWORK_TIMEOUT, lock_timeout: Optional[float] = None) -> dict:
        """Fast-forward the local clone to the default branch and re-index.

        Returns a report: head, previous head, facts that changed status in
        this sync (SUPERSEDED / STALE), and proposal lifecycle transitions.
        """
        private_dir(self.root)
        kwargs = {} if lock_timeout is None else {"timeout": lock_timeout}
        with locked(self.lock_path, **kwargs):
            return self._sync_locked(timeout)

    def _sync_locked(self, timeout: int) -> dict:
        state = self.sync_state()
        state["last_attempt_at"] = km.now_iso()
        previous_head = state.get("head")
        before = {row["id"]: row["body"]["status"] for row in self._rows_or_empty()}
        strategy = None
        try:
            if not (self.clone / ".git").is_dir():
                shutil.rmtree(self.clone, ignore_errors=True)
                rc, _, err, strategy = self.access.remote(
                    ["clone", "--quiet", "--no-tags", "--", self.url, str(self.clone)], timeout=timeout)
                if rc != 0:
                    raise _fail("read", self.url, rc, err)
            else:
                rc, _, err, strategy = self.access.remote(
                    ["fetch", "--quiet", "--prune", "--no-tags", "origin"], cwd=self.clone, timeout=timeout)
                if rc != 0:
                    raise _fail("read", self.url, rc, err)
            rc, out, err, _ = self.access.remote(["ls-remote", "--symref", "origin", "HEAD"],
                                                 cwd=self.clone, timeout=timeout, strategy=strategy)
            match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", out) if rc == 0 else None
            if not match:
                if rc != 0:
                    raise _fail("read", self.url, rc, err)
                raise StoreError("the source repository is empty; a source admin must run "
                                 "`agent-skills knowledge init-source` and push it first", "state")
            branch = match.group(1)
        except StoreError as exc:
            state["error"] = str(exc)
            state["error_kind"] = exc.kind
            if exc.kind == "auth":
                state["auth_lost"] = True
            self._save_sync_state(state)
            raise
        rc, head, err = self.access.run_local(["rev-parse", "refs/remotes/origin/" + branch], self.clone)
        if rc != 0:
            raise StoreError("the default branch {} is missing after fetch".format(branch), "state",
                             hint=_last_line(err))
        head = head.strip()
        rewritten = False
        if previous_head and previous_head != head:
            rc, _, _ = self.access.run_local(["merge-base", "--is-ancestor", previous_head, head], self.clone)
            rewritten = rc != 0
        rc, _, err = self.access.run_local(["checkout", "--quiet", "--force", "--detach", head], self.clone)
        if rc != 0:
            raise StoreError("could not update the local cache of {}".format(self.name), "state",
                             hint=_last_line(err))
        # The clone is a cache pinned to origin's default branch. A local branch
        # (the one `git clone` created, or a leftover proposal branch) would keep
        # old history reachable after an upstream rewrite, so none is kept.
        rc, heads, _ = self.access.run_local(["for-each-ref", "--format=%(refname)", "refs/heads"], self.clone)
        for ref in heads.split() if rc == 0 else []:
            self.access.run_local(["update-ref", "-d", ref], self.clone)
        if rewritten:
            # The history-removal runbook rewrites the source. Drop every object
            # the new history no longer reaches, so a purged secret does not
            # survive in this cache.
            self.access.run_local(["reflog", "expire", "--expire=now", "--all"], self.clone)
            self.access.run_local(["gc", "--quiet", "--prune=now"], self.clone, timeout=300)
        state.update({
            "last_success_at": km.now_iso(), "head": head, "previous_head": previous_head,
            "default_branch": branch, "strategy": strategy or state.get("strategy") or "native",
            "error": None, "error_kind": None, "auth_lost": False, "history_rewritten": rewritten,
        })
        self._save_sync_state(state)
        self.build_index()
        after = {row["id"]: row for row in self._rows_or_empty()}
        changed = []
        for fact_id, row in sorted(after.items()):
            status = row["body"]["status"]
            if status in ("SUPERSEDED", "STALE") and before.get(fact_id) != status:
                changed.append(self._present(row))
        return {
            "source": self.name, "head": head, "previous_head": previous_head,
            "history_rewritten": rewritten, "status_changes": changed,
            "proposals": self._update_lifecycle(),
        }

    # -- index --------------------------------------------------------------
    def _fact_files(self) -> List[Path]:
        folder = self.clone / "facts"
        return sorted(folder.rglob("f_*.json")) if folder.is_dir() else []

    def _provenance(self) -> Dict[str, dict]:
        """Approval provenance for every fact file, from git history only."""
        if not (self.clone / ".git").is_dir():
            return {}
        rc, out, _ = self.access.run_local(
            ["log", "--first-parent", "--format=%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s",
             "--name-only", "HEAD", "--", "facts"], self.clone, timeout=300)
        if rc != 0:
            return {}
        latest: Dict[str, dict] = {}
        for record in out.split("\x1e"):
            if not record.strip():
                continue
            head, _, names = record.partition("\n")
            parts = head.split("\x1f")
            if len(parts) != 7:
                continue
            sha, parents, an, ae, cn, ce, subject = parts
            for name in names.split("\n"):
                name = name.strip()
                if name and name not in latest:
                    latest[name] = {"commit": sha, "parents": parents.split(), "author": an,
                                    "author_email": ae, "committer": cn, "committer_email": ce,
                                    "subject": subject}
        merged_authors: Dict[str, Dict[str, str]] = {}
        out_map: Dict[str, dict] = {}
        for name, info in latest.items():
            pr = None
            for pattern in _PR_SUBJECT:
                match = pattern.search(info["subject"])
                if match:
                    pr = "#" + match.group(1)
                    break
            if len(info["parents"]) >= 2:
                merge = info["commit"]
                if merge not in merged_authors:
                    merged_authors[merge] = self._merged_in_authors(merge, info["parents"])
                proposer = merged_authors[merge].get(name) or info["author"]
                prov = {"review": "merge", "approved_by": info["author"], "proposed_by": proposer}
            elif info["committer_email"].lower() in _HOST_COMMITTERS and pr:
                prov = {"review": "host-merge", "approved_by": "the {} merge of PR {}".format(
                    "GitHub" if "github" in info["committer_email"] else "GitLab", pr),
                    "proposed_by": info["author"]}
            elif (info["committer_email"].lower() != info["author_email"].lower()
                  and info["committer_email"].lower() not in _HOST_COMMITTERS):
                prov = {"review": "committer", "approved_by": info["committer"],
                        "proposed_by": info["author"]}
            else:
                prov = {"review": "unreviewed", "approved_by": None, "proposed_by": info["author"]}
            prov["pr"] = pr
            prov["commit"] = info["commit"]
            out_map[name] = prov
        return out_map

    def _merged_in_authors(self, merge: str, parents: List[str]) -> Dict[str, str]:
        rc, out, _ = self.access.run_local(
            ["log", "--format=%x1e%an", "--name-only", "{}..{}".format(parents[0], parents[1]),
             "--", "facts"], self.clone, timeout=120)
        authors: Dict[str, str] = {}
        if rc != 0:
            return authors
        for record in out.split("\x1e"):
            if not record.strip():
                continue
            author, _, names = record.partition("\n")
            for name in names.split("\n"):
                name = name.strip()
                if name and name not in authors:
                    authors[name] = author.strip()
        return authors

    def scan_rows(self) -> List[dict]:
        """Every valid fact in the clone with derived provenance. The truth the index caches."""
        provenance = self._provenance()
        rows = []
        for path in self._fact_files():
            if path.is_symlink():
                continue  # a source could point a "fact" at any file on this machine
            location = path.relative_to(self.clone).as_posix()
            try:
                body = read_json(path, None)
            except StoreError:
                continue
            if not isinstance(body, dict) or km.validate_fact(body):
                continue
            if km.fact_location(body) != location:
                continue  # a file outside its scope directory is not trusted
            rows.append({"id": body["id"], "location": location, "body": body,
                         "provenance": provenance.get(location) or {"review": "unreviewed",
                                                                      "approved_by": None,
                                                                      "proposed_by": None}})
        return sorted(rows, key=lambda r: r["id"])

    def build_index(self) -> str:
        """Rebuild the derived index from the clone. Never authoritative."""
        import json

        rows = self.scan_rows()
        if SQLITE is None:
            return "unavailable"
        temporary = self.index_path.with_name("index.sqlite.tmp.%d" % os.getpid())
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        conn = SQLITE.connect(str(temporary))
        try:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE facts (id TEXT PRIMARY KEY, location TEXT, body TEXT, "
                         "provenance TEXT, scope TEXT, type TEXT, status TEXT, norm TEXT)")
            conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (r["id"], r["location"], json.dumps(r["body"], sort_keys=True),
                 json.dumps(r["provenance"], sort_keys=True), km.scope_string(r["body"]["scope"]),
                 r["body"]["type"], r["body"]["status"], km.normalise_statement(r["body"]["statement"]))
                for r in rows])
            conn.executemany("INSERT INTO meta VALUES (?, ?)", [
                ("schema", str(INDEX_SCHEMA)), ("head", self.sync_state().get("head") or ""),
                ("count", str(len(rows)))])
            conn.commit()
        finally:
            conn.close()
        os.replace(temporary, self.index_path)
        return "ok"

    def _index_rows(self) -> Optional[List[dict]]:
        import json

        if SQLITE is None or not self.index_path.exists():
            return None
        try:
            conn = SQLITE.connect("file:{}?mode=ro".format(self.index_path), uri=True)
            try:
                meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
                if meta.get("schema") != str(INDEX_SCHEMA) or meta.get("head") != (
                        self.sync_state().get("head") or ""):
                    return None
                rows = conn.execute("SELECT id, location, body, provenance FROM facts ORDER BY id")
                return [{"id": i, "location": loc, "body": json.loads(b), "provenance": json.loads(p)}
                        for i, loc, b, p in rows.fetchall()]
            finally:
                conn.close()
        except (SQLITE.Error, ValueError):
            return None

    def index_health(self) -> str:
        if SQLITE is None:
            return "unavailable (no sqlite3; scanning the clone)"
        if not self.index_path.exists():
            return "missing"
        return "ok" if self._index_rows() is not None else "stale"

    def _rows_or_empty(self) -> List[dict]:
        if not (self.clone / ".git").is_dir():
            return []
        rows = self._index_rows()
        if rows is None:
            rows = self.scan_rows()
        return rows

    def _present(self, row: dict) -> dict:
        fact = dict(row["body"])
        provenance = dict(row["provenance"])
        claimed = fact["status"]
        if claimed == "CONFIRMED" and provenance.get("review") == "unreviewed":
            # CONFIRMED means a human approved it; git shows no approval.
            fact["status"] = "PROPOSED"
            provenance["note"] = ("claims CONFIRMED but landed on the default branch without review; "
                                  "shown as PROPOSED")
        provenance["claimed_status"] = claimed
        fact["_origin"] = "shared:" + self.name
        fact["_provenance"] = provenance
        fact["_location"] = row["location"]
        return fact

    # -- the interface ------------------------------------------------------
    def get(self, fact_id: str) -> Optional[dict]:
        for row in self._rows_or_empty():
            if row["id"] == fact_id:
                return self._present(row)
        return None

    def query(self, scope_filter: Optional[List[str]] = None, terms: Iterable[str] = (),
              types: Iterable[str] = (), statuses: Iterable[str] = ()) -> List[dict]:
        types, statuses = set(types), set(statuses)
        out = []
        for row in self._rows_or_empty():
            fact = self._present(row)
            if scope_filter is not None and not km.scope_allowed(fact["scope"], scope_filter):
                continue
            if types and fact["type"] not in types:
                continue
            if statuses and fact["status"] not in statuses:
                continue
            out.append(fact)
        return out

    def capabilities(self) -> dict:
        reason = self.read_only_reason()
        adapter = host_adapter(self.config)
        return {"read": True, "propose": not reason, "read_only_reason": reason, "shared": True,
                "review_host": adapter.name, "backend": "git"}

    def health(self) -> dict:
        manifest = self.manifest() or {}
        state = self.sync_state()
        clone = "ok" if (self.clone / ".git").is_dir() else "missing"
        if clone == "ok":
            rc, _, _ = self.access.run_local(["rev-parse", "--verify", "HEAD"], self.clone)
            clone = "ok" if rc == 0 else "broken"
        schema = "unknown"
        if manifest:
            schema = "compatible" if manifest.get("schema_version", 1) <= km.SUPPORTED_SOURCE_SCHEMA \
                else "newer (read-only)"
        setup = []
        if clone == "ok":
            if not manifest:
                setup.append("no manifest ({})".format(km.MANIFEST_NAME))
            if not (self.clone / "CODEOWNERS").exists() and not (self.clone / ".github" / "CODEOWNERS").exists():
                setup.append("no CODEOWNERS")
            workflows = self.clone / ".github" / "workflows"
            ci = any(p.read_text(encoding="utf-8", errors="replace").find("knowledge check") >= 0
                     for p in workflows.glob("*.y*ml")) if workflows.is_dir() else False
            if not ci and not (self.clone / ".gitlab-ci.yml").exists():
                setup.append("no CI running `agent-skills knowledge check`")
        return {
            "source": self.name, "url": self.url, "clone": clone,
            "last_sync": state.get("last_success_at"), "cache_age_seconds": self.cache_age_seconds(),
            "last_error": state.get("error"), "error_kind": state.get("error_kind"),
            "auth_lost": bool(state.get("auth_lost")), "schema": schema,
            "status": manifest.get("status", "unknown"), "successor": manifest.get("successor"),
            "org": manifest.get("org"), "source_id": manifest.get("source_id"),
            "index": self.index_health() if clone == "ok" else "missing",
            "read_only_reason": self.read_only_reason(), "setup_missing": setup,
        }

    def list_proposals(self) -> List[dict]:
        return self.ledger.for_source(self.name)

    # -- proposals ----------------------------------------------------------
    def _apply(self, tree: Path, change: dict) -> List[dict]:
        """Write a change into a working tree. Returns what was written.

        A patch whose base changed upstream is re-applied when that is
        mechanical: none of the fields it sets were changed upstream.
        Otherwise the change is refused as a conflict; it is never forced.
        """
        written = []
        by_id = {row["id"]: row for row in self._scan_tree(tree)}
        for item in change["writes"]:
            if item["op"] == "add":
                body = item["fact"]
                location = km.fact_location(body)
                if item.get("replace") is not True and body["id"] in by_id:
                    raise StoreError("fact {} already exists in the source".format(body["id"]), "conflict")
                action = "add"
            elif item["op"] == "patch":
                row = by_id.get(item["id"])
                if row is None:
                    raise StoreError("fact {} is not in the source any more".format(item["id"]), "conflict")
                body = dict(row["body"])
                if item.get("base_hash") and km.content_hash(body) != item["base_hash"]:
                    base = item.get("base") or {}
                    moved = [k for k in item["set"] if base.get(k) != body.get(k)]
                    if moved:
                        raise StoreError("fact {} changed upstream in {}; re-run propose after sync".format(
                            item["id"], ", ".join(moved)), "conflict")
                body.update(item["set"])
                location = row["location"]
                action = "update"
            else:
                raise StoreError("unknown change op {!r}".format(item["op"]), "usage")
            errors = km.validate_fact(body)
            if errors:
                raise StoreError("{} would not be valid: {}".format(body.get("id"), "; ".join(errors)), "usage")
            path = tree / location
            path.parent.mkdir(parents=True, exist_ok=True)
            text = km.canonical_json(body)
            path.write_text(text, encoding="utf-8")
            by_id[body["id"]] = {"id": body["id"], "location": location, "body": body}
            written.append({"location": location, "action": action, "content": text, "id": body["id"],
                            "content_hash": km.content_hash(body)})
        return written

    def _scan_tree(self, tree: Path) -> List[dict]:
        rows = []
        folder = tree / "facts"
        for path in sorted(folder.rglob("f_*.json")) if folder.is_dir() else []:
            if path.is_symlink():
                continue
            try:
                body = read_json(path, None)
            except StoreError:
                continue
            if isinstance(body, dict) and body.get("id"):
                rows.append({"id": body["id"], "location": path.relative_to(tree).as_posix(), "body": body})
        return rows

    def preview(self, change: dict) -> List[dict]:
        """The exact files a proposal will write, against the current cache."""
        if not (self.clone / ".git").is_dir():
            raise StoreError("source {} has not been synced".format(self.name), "state")
        work = Path(tempfile.mkdtemp(prefix="agent-skills-preview-"))
        try:
            shutil.copytree(self.clone / "facts", work / "facts") if (self.clone / "facts").is_dir() else None
            return self._apply(work, change)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def propose(self, change: dict) -> dict:
        reason = self.read_only_reason()
        if reason:
            raise StoreError(reason, "readonly")
        private_dir(self.root)
        with locked(self.lock_path):
            return self._propose_locked(change)

    def _propose_locked(self, change: dict) -> dict:
        state = self.sync_state()
        strategy = state.get("strategy") or "native"
        rc, _, err, _ = self.access.remote(["fetch", "--quiet", "--no-tags", "origin"], cwd=self.clone,
                                           strategy=strategy)
        if rc != 0:
            raise _fail("read", self.url, rc, err)
        base = self.default_branch()
        stamp = km.now_iso().replace("-", "").replace(":", "")
        branch = "{}{}/{}-{}".format(PROPOSAL_PREFIX, change["installation"][:8], stamp,
                                     os.urandom(2).hex())
        if branch == base or not branch.startswith(PROPOSAL_PREFIX) or base.startswith(PROPOSAL_PREFIX):
            raise StoreError("refusing to push anywhere but a proposal branch", "usage")
        work = self.root / "work-{}".format(os.getpid())
        shutil.rmtree(work, ignore_errors=True)
        rc, _, err = self.access.run_local(["worktree", "add", "--quiet", "-b", branch, str(work),
                                        "refs/remotes/origin/" + base], self.clone)
        if rc != 0:
            raise StoreError("could not prepare a proposal worktree", "state", hint=_last_line(err))
        try:
            written = self._apply(work, change)
            self.access.run_local(["add", "--all", "facts"], work)
            rc, _, err = self.access.run_local(["commit", "--quiet", "-m", change["title"], "-m",
                                            change["summary"]], work)
            if rc != 0:
                if "tell me who you are" in err.lower() or "user.email" in err:
                    raise StoreError("git has no identity configured; proposed_by is derived from it. "
                                     "Set it with: git config --global user.name ... / user.email ...",
                                     "usage")
                raise StoreError("could not commit the proposal", "state", hint=_last_line(err))
            _, commit, _ = self.access.run_local(["rev-parse", "HEAD"], work)
            commit = commit.strip()
            result = self._push_and_review(work, branch, base, change, strategy)
            result.update({"branch": branch, "commit": commit, "files": written, "source": self.name})
            proposal_id = "p_{}_{}".format(stamp, os.urandom(3).hex())
            self.ledger.add(proposal_id, {
                "source": self.name, "branch": branch, "commit": commit, "state": "open",
                "created_at": km.now_iso(), "via": result["via"], "pr_url": result.get("pr_url"),
                "compare_url": result.get("compare_url"), "outbox": result.get("outbox"),
                "facts": [{"id": w["id"], "content_hash": w["content_hash"], "location": w["location"]}
                          for w in written],
                "title": change["title"],
            })
            result["proposal_id"] = proposal_id
            return result
        finally:
            self.access.run_local(["worktree", "remove", "--force", str(work)], self.clone)
            shutil.rmtree(work, ignore_errors=True)
            self.access.run_local(["worktree", "prune"], self.clone)
            self.access.run_local(["branch", "-D", branch], self.clone)

    def _push_and_review(self, work: Path, branch: str, base: str, change: dict, strategy: str) -> dict:
        refspec = "refs/heads/{0}:refs/heads/{0}".format(branch)
        # No --force, no default branch: asserted, not assumed.
        assert refspec.startswith("refs/heads/" + PROPOSAL_PREFIX) and "+" not in refspec
        rc, _, err, _ = self.access.remote(["push", "--quiet", "origin", refspec], cwd=work, strategy=strategy)
        adapter = host_adapter(self.config)
        if rc == 0:
            pr_url = adapter.create_pr(base, branch, change["title"], change["summary"]) \
                if adapter.available() else None
            return {"via": "pushed", "pr_url": pr_url,
                    "compare_url": None if pr_url else compare_url(self.url, base, branch)}
        low = err.lower()
        denied = any(marker in low for marker in _PUSH_DENIED) or classify_failure(rc, err) == "auth"
        if classify_failure(rc, err) == "network" and not denied:
            raise _fail("push a proposal to", self.url, rc, err)
        if not denied:
            raise _fail("push a proposal to", self.url, rc, err)
        # No write access. Never retried with another credential.
        if adapter.available():
            fork = adapter.fork()
            if fork and fork[0].lstrip().startswith("-"):
                fork = None
            if fork:
                fork_url, owner = fork
                rc, _, err, _ = self.access.remote(["push", "--quiet", "--", fork_url, refspec], cwd=work,
                                                   strategy=strategy)
                if rc == 0:
                    pr_url = adapter.create_pr(base, "{}:{}".format(owner, branch), change["title"],
                                               change["summary"])
                    return {"via": "fork", "pr_url": pr_url, "fork": fork_url,
                            "compare_url": None if pr_url else compare_url(fork_url, base, branch)}
        return self._outbox(work, branch, base, change)

    def _outbox(self, work: Path, branch: str, base: str, change: dict) -> dict:
        folder = private_dir(outbox_dir() / self.name)
        name = branch[len(PROPOSAL_PREFIX):].replace("/", "-")
        rc, patch, err = self.access.run_local(["format-patch", "-1", "--stdout", "HEAD"], work)
        if rc != 0:
            raise StoreError("could not write the proposal to the outbox", "state", hint=_last_line(err))
        patch_path = folder / "{}.patch".format(name)
        summary_path = folder / "{}.md".format(name)
        patch_path.write_text(patch, encoding="utf-8")
        summary_path.write_text(
            "# Knowledge proposal (not pushed)\n\n"
            "Your git access cannot push to `{url}`, and no fork could be made.\n\n"
            "To submit it, send `{patch}` to a source admin, or apply it on a branch of a clone "
            "you can push:\n\n    git checkout -b {branch} origin/{base}\n    git am {patch}\n\n"
            "## Summary\n\n{summary}\n".format(url=self.url, patch=patch_path.name, branch=branch,
                                               base=base, summary=change["summary"]),
            encoding="utf-8")
        for path in (patch_path, summary_path):
            os.chmod(path, 0o600)
        return {"via": "outbox", "outbox": str(patch_path), "summary_file": str(summary_path),
                "pr_url": None, "compare_url": None}

    def _update_lifecycle(self) -> List[dict]:
        """open -> merged | closed_unmerged, from the default branch and the host CLI."""
        transitions = []
        adapter = None
        current = {row["location"]: row for row in self._rows_or_empty()}
        for proposal in self.ledger.for_source(self.name):
            if proposal.get("state") != "open":
                continue
            merged = bool(proposal.get("facts")) and all(
                f["location"] in current and km.content_hash(current[f["location"]]["body"]) == f["content_hash"]
                for f in proposal["facts"])
            if not merged and proposal.get("commit"):
                rc, _, _ = self.access.run_local(["merge-base", "--is-ancestor", proposal["commit"], "HEAD"],
                                             self.clone)
                merged = rc == 0
            state = "merged" if merged else "open"
            if not merged and proposal.get("pr_url"):
                adapter = adapter or host_adapter(self.config)
                if adapter.available():
                    remote_state = adapter.pr_state(proposal["pr_url"])
                    state = {"merged": "merged", "closed": "closed_unmerged"}.get(remote_state, "open")
            if state != "open":
                self.ledger.set_state(proposal["id"], state)
                transitions.append({"proposal": proposal["id"], "state": state, "facts": proposal["facts"],
                                    "pr_url": proposal.get("pr_url")})
        return transitions

    # -- offboarding --------------------------------------------------------
    def remove_local_data(self) -> List[str]:
        removed = []
        for path in (self.root, outbox_dir() / self.name):
            if path.exists():
                shutil.rmtree(path)
                removed.append(str(path))
        count = self.ledger.drop_source(self.name)
        if count:
            removed.append("{} proposal record(s)".format(count))
        return removed


def try_sync(store: GitKnowledgeStore, timeout: int) -> Tuple[Optional[dict], Optional[StoreError]]:
    """Sync without ever blocking a query for long: a held lock or a failure uses the cache."""
    try:
        return store.sync(timeout=timeout, lock_timeout=0), None
    except LockTimeout:
        return None, StoreError("another agent-skills process is syncing this source; using the cache",
                                "state")
    except StoreError as exc:
        return None, exc
