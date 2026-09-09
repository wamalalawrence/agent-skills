"""The install transaction.

    RESOLVE -> DOWNLOAD -> VERIFY -> STAGE -> SELF-TEST
            -> ACTIVATE -> RECONCILE HOSTS -> VERIFY MACHINE

The division of the sequence is the whole point. Everything up to and including
SELF-TEST happens off to the side, in a staging directory: if any of it fails,
the machine has not been touched and the previously installed version is still
the one running. Only ACTIVATE changes what the machine uses, and it is a
single atomic symlink swap. If activation or host reconciliation fails after
that point, the previous version is re-activated and the hosts are reconciled
back to it, so the machine is never left on a half-installed release.

There is no state in which some hosts point at one version and some at another,
because hosts do not point at versions. They point at ``~/.agent-skills/skills``,
which points at ``current``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .exits import Exit, ExitError
from .layout import Layout, LINKED_TREES, MANIFEST_SCHEMA
from .release import (
    MIN_INSTALLABLE_VERSION,
    ReleaseRef,
    compare_versions,
    normalise_version,
    read_manifest,
    verify_payload,
)


class Reporter:
    """Progress output. Quiet enough to read, loud enough to debug."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def step(self, name: str, detail: str = "") -> None:
        if self.quiet:
            return
        line = "  {:<10} {}".format(name, detail) if detail else "  {}".format(name)
        sys.stdout.write(line.rstrip() + "\n")
        sys.stdout.flush()

    def note(self, text: str) -> None:
        if self.quiet:
            return
        sys.stdout.write("             {}\n".format(text))
        sys.stdout.flush()

    def warn(self, text: str) -> None:
        sys.stderr.write("  WARN       {}\n".format(text))
        sys.stderr.flush()


class InstallTransaction:
    def __init__(
        self,
        layout: Layout,
        provider,
        reporter: Reporter = None,
        hosts: str = "",
        all_hosts: bool = False,
        path_link: bool = True,
        mode: str = "release",
        allow_downgrade: bool = False,
        keep_versions: int = 2,
    ):
        self.layout = layout
        self.provider = provider
        self.report = reporter or Reporter()
        self.hosts = hosts
        self.all_hosts = all_hosts
        self.path_link = path_link
        self.mode = mode
        self.allow_downgrade = allow_downgrade
        self.keep_versions = keep_versions

    # --------------------------------------------------------------------------
    def run(self, version: str = "", channel: str = "stable") -> dict:
        layout = self.layout
        previous = layout.active_version()

        # RESOLVE. Nothing is created on disk until a release has been resolved:
        # a failed `install` against an unreachable source must not leave an
        # empty install root behind that later makes the machine look installed.
        if version:
            ref = self.provider.resolve_version(version)
        else:
            ref = self.provider.resolve_latest(channel)
        self.report.step("resolve", "{} ({}, via {})".format(ref.version, ref.channel, ref.provider))

        if compare_versions(ref.version, MIN_INSTALLABLE_VERSION) < 0:
            raise ExitError(
                "release {} predates the Agent Skills CLI installer".format(ref.version),
                Exit.USAGE,
                hint=(
                    "This installer can only install v{0} and later; earlier releases were\n"
                    "  installed by cloning the repository and running ./setup.init. If {1} is\n"
                    "  the newest release your source offers, that source has not published a\n"
                    "  CLI-installable release yet.".format(MIN_INSTALLABLE_VERSION, ref.version)
                ),
            )

        self._guard_downgrade(previous, ref.version)
        layout.ensure_dirs()

        if previous == ref.version and self.mode != "dev":
            self.report.note("{} is already active; re-staging to repair the install".format(ref.version))

        # DOWNLOAD + STAGE (into a scratch directory, never the live tree)
        staging = os.path.join(layout.staging_dir, ref.version)
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        try:
            staged = self.provider.fetch_release(ref, staging)
            self.report.step("download", "{} files staged".format(
                staged.manifest.get("payload", {}).get("file_count", "?")
            ))

            # VERIFY the payload before it is anywhere near the active tree.
            self.provider.verify_release(staged)
            self.report.step("verify", "payload hash and version agree")

            # SELF-TEST the staged release, still off to the side.
            self._self_test(staged.root)
            self.report.step("self-test", "staged runtime answers correctly")

            # STAGE into versions/<v>, atomically enough that a crash leaves a
            # directory that is either complete or clearly incomplete.
            target = layout.version_path(ref.version)
            pending = target + ".incoming"
            shutil.rmtree(pending, ignore_errors=True)
            shutil.move(staged.root, pending)
            if os.path.isdir(target) and target != layout.active_root():
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.isdir(target):
                # Replacing the running version in place would be the one
                # unrecoverable move. Stage beside it and swap `current`.
                shutil.rmtree(target + ".replaced", ignore_errors=True)
                os.rename(target, target + ".replaced")
            os.rename(pending, target)
            self.report.step("stage", target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        # ACTIVATE
        try:
            layout.activate(ref.version)
            self.report.step("activate", "current -> versions/{}".format(ref.version))
        except Exception as exc:
            self._rollback(previous, "activation failed: {}".format(exc))
            raise

        # RECONCILE HOSTS
        try:
            result = self._reconcile_hosts()
            self.report.step(
                "hosts",
                ", ".join(result["hosts"]) if result["hosts"] else "none detected on this machine",
            )
        except Exception as exc:
            self._rollback(previous, "host reconciliation failed: {}".format(exc))
            raise

        payload_manifest = read_manifest(layout.version_path(ref.version))
        record = self._write_manifest(ref, payload_manifest, result, previous)

        # VERIFY MACHINE
        code = self._verify_machine()
        if code != 0:
            self._rollback(previous, "post-install verification failed")
            raise ExitError(
                "installation verification failed; rolled back to {}".format(previous or "nothing"),
                Exit.VERIFY_FAILED,
            )
        self.report.step("verified", "installation is consistent")

        removed = layout.prune_versions(self.keep_versions)
        if removed:
            self.report.note("removed superseded release(s): {}".format(", ".join(removed)))

        shutil.rmtree(layout.version_path(ref.version) + ".replaced", ignore_errors=True)
        layout.append_history(
            {
                "action": "install" if not previous else "update",
                "from": previous,
                "to": ref.version,
                "provider": ref.provider,
                "channel": ref.channel,
                "at": layout.now(),
            }
        )
        return record

    # --------------------------------------------------------------------------
    def rollback(self, version: str = "") -> dict:
        """Return to a previously installed release, hosts and hooks included."""
        layout = self.layout
        active = layout.active_version()
        target = normalise_version(version) if version else layout.rollback_candidate()
        if not target:
            raise ExitError(
                "no previous release is available to roll back to",
                Exit.USAGE,
                hint="installed releases: {}".format(", ".join(layout.installed_versions()) or "none"),
            )
        if target == active:
            raise ExitError("{} is already the active release".format(target), Exit.USAGE)
        if not os.path.isdir(layout.version_path(target)):
            raise ExitError(
                "{} is not installed on this machine".format(target),
                Exit.USAGE,
                hint="installed releases: {}".format(", ".join(layout.installed_versions()) or "none"),
            )

        layout.ensure_dirs()
        verify_payload(layout.version_path(target))
        self.report.step("verify", "{} payload is intact".format(target))
        layout.activate(target)
        self.report.step("activate", "current -> versions/{}".format(target))
        result = self._reconcile_hosts()
        self.report.step("hosts", ", ".join(result["hosts"]) or "none")

        ref = ReleaseRef(target, "local", layout.version_path(target))
        record = self._write_manifest(ref, read_manifest(layout.version_path(target)), result, active)
        code = self._verify_machine()
        if code != 0:
            raise ExitError(
                "verification failed after rolling back to {}".format(target), Exit.VERIFY_FAILED
            )
        layout.append_history(
            {"action": "rollback", "from": active, "to": target, "at": layout.now()}
        )
        return record

    # --------------------------------------------------------------------------
    def _guard_downgrade(self, active: str, wanted: str) -> None:
        """Refuse to silently replace a newer release with an older one.

        An update that quietly moves the machine backwards is how a downgrade
        attack lands a version whose vulnerabilities are already published, and
        it is also just a bad surprise. Going backwards is supported — it is
        called ``rollback`` — but never as a side effect of ``update``.
        """
        if not active or self.allow_downgrade:
            return
        if compare_versions(wanted, active) < 0:
            raise ExitError(
                "refusing to replace the active release {} with the older {}".format(active, wanted),
                Exit.USAGE,
                hint=(
                    "to go back deliberately:   agent-skills rollback --version {}\n"
                    "  to force it anyway:        add --allow-downgrade".format(wanted)
                ),
            )

    def _self_test(self, root: str) -> None:
        """Prove the staged release can run before anything points at it."""
        launcher = os.path.join(root, "bin", "agent-skills")
        env = dict(os.environ)
        env["AGENT_SKILLS_SOURCE"] = root
        env["AGENT_SKILLS_SELF_TEST"] = "1"
        try:
            done = subprocess.run(
                ["bash", launcher, "self-test"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExitError(
                "staged release {} could not be executed: {}".format(root, exc),
                Exit.INSTALL_FAILED,
            )
        if done.returncode != 0:
            detail = done.stdout.decode("utf-8", "replace").strip()
            raise ExitError(
                "staged release failed its self-test; nothing was activated",
                Exit.INSTALL_FAILED,
                hint=detail[-1500:],
            )

    def _reconcile_hosts(self) -> dict:
        """Register the active release with every supported host on this machine.

        Host adapters stay in shell, next to the ownership predicates that decide
        what may and may not be touched in a user's own skills directory. This
        calls them and parses two result lines; it does not reimplement them.
        """
        script = os.path.join(self.layout.home, "scripts", "hosts-reconcile.sh")
        if not os.path.isfile(script):
            script = os.path.join(self.layout.active_root(), "scripts", "hosts-reconcile.sh")
        if not os.path.isfile(script):
            raise ExitError("host reconciliation helper is missing from the release", Exit.INSTALL_FAILED)

        env = dict(os.environ)
        env["AGENT_SKILLS_HOME"] = self.layout.home
        env["AGENT_SKILLS_CONFIG_DIR"] = self.layout.config_dir
        env["AS_OPT_HOSTS"] = self.hosts or ""
        env["AS_OPT_ALL_HOSTS"] = "true" if self.all_hosts else "false"
        env["AS_OPT_NO_PATH"] = "false" if self.path_link else "true"
        done = subprocess.run(
            ["bash", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
        out = done.stdout.decode("utf-8", "replace")
        err = done.stderr.decode("utf-8", "replace")
        hosts, cli_link = [], ""
        for line in out.splitlines():
            if line.startswith("AS_RESULT_HOSTS="):
                hosts = [h for h in line.split("=", 1)[1].split() if h]
            elif line.startswith("AS_RESULT_CLI_LINK="):
                cli_link = line.split("=", 1)[1].strip()
            elif not self.report.quiet and line.strip():
                self.report.note(line.rstrip())
        if err.strip():
            # Forwarded verbatim: the host adapters already format their own
            # status lines, and re-prefixing them produces "WARN WARN".
            for line in err.splitlines():
                if line.strip():
                    sys.stderr.write(line.rstrip() + "\n")
        if done.returncode != 0:
            raise ExitError("host reconciliation exited {}".format(done.returncode), Exit.INSTALL_FAILED)
        return {"hosts": hosts, "cli_link": cli_link}

    def _verify_machine(self) -> int:
        launcher = self.layout.launcher
        if not os.path.isfile(launcher):
            return 1
        env = dict(os.environ)
        env["AGENT_SKILLS_HOME"] = self.layout.home
        env["AGENT_SKILLS_CONFIG_DIR"] = self.layout.config_dir
        env.pop("AGENT_SKILLS_SOURCE", None)
        done = subprocess.run(
            ["bash", launcher, "verify", "--quiet"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        if done.returncode != 0 and not self.report.quiet:
            sys.stderr.write(done.stdout.decode("utf-8", "replace"))
        return done.returncode

    def _write_manifest(self, ref, payload_manifest: dict, hosts_result: dict, previous: str) -> dict:
        layout = self.layout
        record = {
            "schema": MANIFEST_SCHEMA,
            "version": ref.version,
            "channel": ref.channel,
            "mode": self.mode,
            "home": layout.home,
            "config_dir": layout.config_dir,
            "current": layout.version_path(ref.version),
            "canonical_skills_dir": os.path.join(layout.home, "skills"),
            "linked_trees": list(LINKED_TREES),
            "hosts": hosts_result.get("hosts", []),
            "cli_link": hosts_result.get("cli_link", ""),
            "previous_version": previous,
            "installed_at": layout.now(),
            "provider": {
                "id": ref.provider,
                "description": getattr(self.provider, "description", ""),
                "ref": ref.ref,
                "commit": ref.commit,
            },
            "release": {
                "tree_sha256": payload_manifest.get("payload", {}).get("tree_sha256", ""),
                "file_count": payload_manifest.get("payload", {}).get("file_count", 0),
                "built_at": payload_manifest.get("built_at", ""),
            },
        }
        layout.write_manifest(record)
        return record

    def _rollback(self, previous: str, reason: str) -> None:
        self.report.warn(reason)
        if not previous or not os.path.isdir(self.layout.version_path(previous)):
            self.report.warn("no previous release to fall back to; run: agent-skills doctor")
            return
        try:
            self.layout.activate(previous)
            self._reconcile_hosts()
            self.report.warn("rolled back to {}".format(previous))
            self.layout.append_history(
                {
                    "action": "auto-rollback",
                    "from": self.layout.active_version(),
                    "to": previous,
                    "reason": reason,
                    "at": self.layout.now(),
                }
            )
        except Exception as exc:  # pragma: no cover - the last-resort path
            self.report.warn("rollback to {} also failed: {}".format(previous, exc))
