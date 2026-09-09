#!/usr/bin/env python3
"""agent-skills installation engine.

The single authoritative implementation of install, update, rollback, and
release resolution. `bin/agent-skills` dispatches to it, the npm bootstrap runs
it after downloading a first release, and `setup.init` delegates to it. There is
no second installer.

Usage is not intended to be typed directly; use the `agent-skills` CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The engine runs from three places: a release payload (`<release>/scripts`),
# a source checkout, and the npm bootstrap package (`<package>/vendor`), which
# vendors this file next to a copy of `asrelease`. All three are covered here so
# there is one engine rather than one per distribution shape.
for _candidate in (os.path.join(_HERE, "..", "lib"), os.path.join(_HERE, "vendor"), _HERE):
    _candidate = os.path.abspath(_candidate)
    if os.path.isdir(os.path.join(_candidate, "asrelease")) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from asrelease.exits import Exit, ExitError  # noqa: E402
from asrelease.layout import Layout  # noqa: E402
from asrelease.providers import AuthState, build_provider  # noqa: E402
from asrelease.release import CHANNELS, compare_versions, normalise_version  # noqa: E402
from asrelease.transaction import InstallTransaction, Reporter  # noqa: E402


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", default="", help="install root (default ~/.agent-skills)")
    parser.add_argument("--config-dir", default="", help="non-secret state dir")
    parser.add_argument("--provider", default="", help="release provider: local | git")
    parser.add_argument("--source", default="", help="source directory for the local provider")
    parser.add_argument("--repo", default="", help="git remote for the git provider")
    parser.add_argument("--quiet", action="store_true")


def add_install_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", default="", help="install this exact version")
    # Default is resolved in resolve_channel(): an explicit value always wins; a
    # --dev install of a working tree is not a release-channel decision, so it
    # falls back to "any" rather than "stable" (which would refuse a pre-release
    # checkout). Everything else falls back to "stable".
    parser.add_argument("--channel", default=None, choices=list(CHANNELS) + ["any"])
    parser.add_argument("--hosts", default="", help="comma-separated host ids to register")
    parser.add_argument("--all-hosts", action="store_true")
    parser.add_argument("--no-path-link", action="store_true")
    parser.add_argument("--allow-downgrade", action="store_true")
    parser.add_argument("--keep", type=int, default=2, help="how many releases to retain")
    parser.add_argument("--dev", action="store_true", help="mark this install as a development one")


def make_layout(args) -> Layout:
    return Layout(home=args.home, config_dir=args.config_dir)


def make_provider(args):
    options = {}
    if getattr(args, "source", ""):
        options["source"] = args.source
    if getattr(args, "repo", ""):
        options["repo"] = args.repo
    return build_provider(getattr(args, "provider", ""), **options)


def make_transaction(args, layout, provider) -> InstallTransaction:
    return InstallTransaction(
        layout,
        provider,
        reporter=Reporter(quiet=args.quiet),
        hosts=getattr(args, "hosts", ""),
        all_hosts=getattr(args, "all_hosts", False),
        path_link=not getattr(args, "no_path_link", False),
        mode="dev" if getattr(args, "dev", False) else "release",
        allow_downgrade=getattr(args, "allow_downgrade", False),
        keep_versions=max(1, getattr(args, "keep", 2)),
    )


# ------------------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------------------
def resolve_channel(args) -> str:
    """The effective release channel.

    An explicit ``--channel`` always wins. Otherwise a ``--dev`` install of a
    working tree falls back to ``any`` — a development install is not a
    release-channel choice and must not be refused just because the checkout is
    a pre-release. Every other install falls back to ``stable``.
    """
    if getattr(args, "channel", None):
        return args.channel
    return "any" if getattr(args, "dev", False) else "stable"


def cmd_install(args) -> int:
    args.channel = resolve_channel(args)
    layout = make_layout(args)
    provider = make_provider(args)
    transaction = make_transaction(args, layout, provider)
    if not args.quiet:
        print("Installing Agent Skills")
        print("  source: {}".format(provider.description))
        print("  home:   {}".format(layout.home))
        print("")
    record = transaction.run(version=args.version, channel=args.channel)
    if not args.quiet:
        print_success(record, layout, updated=bool(record.get("previous_version")))
    return Exit.OK


def cmd_update(args) -> int:
    args.channel = resolve_channel(args)
    layout = make_layout(args)
    active = layout.active_version()
    if not active:
        raise ExitError(
            "nothing is installed on this machine yet",
            Exit.USAGE,
            hint="install it first: agent-skills install",
        )
    provider = make_provider(args)
    transaction = make_transaction(args, layout, provider)
    if not args.version:
        ref = provider.resolve_latest(args.channel)
        if compare_versions(ref.version, active) == 0:
            if not args.quiet:
                print("Agent Skills {} is already the latest {} release.".format(active, args.channel))
            return Exit.OK
    if not args.quiet:
        print("Updating Agent Skills from {}".format(active))
        print("  source: {}".format(provider.description))
        print("")
    record = transaction.run(version=args.version, channel=args.channel)
    if not args.quiet:
        print_success(record, layout, updated=True)
    return Exit.OK


def cmd_rollback(args) -> int:
    layout = make_layout(args)
    provider_stub = _NullProvider()
    transaction = InstallTransaction(
        layout,
        provider_stub,
        reporter=Reporter(quiet=args.quiet),
        hosts=getattr(args, "hosts", ""),
        all_hosts=getattr(args, "all_hosts", False),
        path_link=not getattr(args, "no_path_link", False),
    )
    record = transaction.rollback(args.version)
    if not args.quiet:
        print("")
        print("Rolled back to Agent Skills {}.".format(record["version"]))
        print("Host registrations and hooks now resolve to that release.")
    return Exit.OK


def cmd_check_updates(args) -> int:
    layout = make_layout(args)
    active = layout.active_version() or "unknown"
    provider = make_provider(args)
    ref = provider.resolve_latest(args.channel)
    payload = {
        "installed": active,
        "latest": ref.version,
        "channel": ref.channel,
        "provider": provider.id,
    }
    comparison = compare_versions(active, ref.version)
    payload["status"] = (
        "update-available" if comparison < 0 else ("ahead" if comparison > 0 else "up-to-date")
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("agent-skills update check")
        print("  installed: {}".format(active))
        print("  latest   : {}  ({} channel, via {})".format(ref.version, ref.channel, provider.id))
        print("  status   : {}".format(payload["status"]))
        if payload["status"] == "update-available":
            print("  apply    : agent-skills update")
    return Exit.UPDATE_AVAILABLE if payload["status"] == "update-available" else Exit.OK


def cmd_versions(args) -> int:
    layout = make_layout(args)
    installed = layout.installed_versions()
    active = layout.active_version()
    remote = []
    if not args.local:
        try:
            remote = make_provider(args).available_versions()
        except ExitError as exc:
            if not args.json:
                print("  (could not list remote releases: {})".format(exc.message), file=sys.stderr)
    if args.json:
        json.dump(
            {
                "active": active,
                "installed": installed,
                "available": remote,
                "rollback_candidate": layout.rollback_candidate(),
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return Exit.OK
    print("Installed on this machine")
    for version in installed:
        marker = "*" if version == active else " "
        print("  {} {}".format(marker, version))
    if not installed:
        print("  (none)")
    candidate = layout.rollback_candidate()
    if candidate:
        print("\nPrevious release: {}   (agent-skills rollback)".format(candidate))
    if remote:
        print("\nAvailable from {}".format(make_provider(args).description))
        for version in remote[-10:]:
            print("  {}".format(version))
    return Exit.OK


def cmd_provider_info(args) -> int:
    layout = make_layout(args)
    manifest = layout.read_manifest()
    try:
        provider = make_provider(args)
        described = provider.describe()
    except ExitError as exc:
        described = {"id": getattr(args, "provider", "") or "git", "description": exc.message,
                     "auth": AuthState.UNKNOWN}
    payload = {
        "provider": described,
        "installed_provider": manifest.get("provider", {}),
        "channel": manifest.get("channel", ""),
    }
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("Release provider")
        print("  id          : {}".format(described["id"]))
        print("  source      : {}".format(described["description"]))
        print("  access      : {}".format(described["auth"]))
        if manifest:
            print("  installed by: {} ({})".format(
                manifest.get("provider", {}).get("id", "?"),
                manifest.get("channel", "?"),
            ))
    return Exit.OK if described["auth"] != AuthState.REQUIRED else Exit.AUTH_REQUIRED


class _NullProvider:
    """Rollback works entirely from what is already on disk."""

    id = "installed"
    description = "already-installed releases"

    def describe(self):
        return {"id": self.id, "description": self.description, "auth": AuthState.NOT_REQUIRED}


def print_success(record: dict, layout: Layout, updated: bool) -> None:
    print("")
    print("Agent Skills {} is {}.".format(record["version"], "active" if updated else "installed"))
    print("")
    print("  install root : {}".format(layout.home))
    print("  active release: {}".format(record["current"]))
    if record.get("hosts"):
        print("  hosts        : {}".format(", ".join(record["hosts"])))
    else:
        print("  hosts        : none detected on this machine")
    if record.get("cli_link"):
        print("  command      : {}".format(record["cli_link"]))
    if record.get("previous_version"):
        print("  rollback to  : {}  (agent-skills rollback)".format(record["previous_version"]))
    print("")
    print("No credentials were requested or stored. External-service access is")
    print("resolved only when a task needs it: see docs/access-resolution.md.")
    print("")
    print("Next:")
    print("  cd into any repository and ask your assistant to use Wamala.")
    print("  agent-skills doctor    what this environment can actually do")
    print("  agent-skills verify    re-check this installation")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-skills-install", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install")
    add_common(install)
    add_install_options(install)
    install.set_defaults(handler=cmd_install)

    update = sub.add_parser("update")
    add_common(update)
    add_install_options(update)
    update.set_defaults(handler=cmd_update)

    rollback = sub.add_parser("rollback")
    add_common(rollback)
    rollback.add_argument("--version", default="")
    rollback.add_argument("--hosts", default="")
    rollback.add_argument("--all-hosts", action="store_true")
    rollback.add_argument("--no-path-link", action="store_true")
    rollback.set_defaults(handler=cmd_rollback)

    check = sub.add_parser("check-updates")
    add_common(check)
    check.add_argument("--channel", default="stable", choices=list(CHANNELS) + ["any"])
    check.add_argument("--json", action="store_true")
    check.set_defaults(handler=cmd_check_updates)

    versions = sub.add_parser("versions")
    add_common(versions)
    versions.add_argument("--json", action="store_true")
    versions.add_argument("--local", action="store_true", help="do not contact the provider")
    versions.set_defaults(handler=cmd_versions)

    info = sub.add_parser("provider")
    add_common(info)
    info.add_argument("--json", action="store_true")
    info.set_defaults(handler=cmd_provider_info)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ExitError as exc:
        # Flush first. Progress goes to stdout, which is block-buffered when it
        # is a file or a pipe; without this the failure can be written before
        # the steps that led to it, or — if the reader only tails — lost among
        # them. A diagnostic that arrives out of order is a diagnostic nobody
        # trusts.
        sys.stdout.flush()
        sys.stderr.write(exc.render() + "\n")
        sys.stderr.flush()
        return exc.code
    except KeyboardInterrupt:
        sys.stderr.write("\nagent-skills: interrupted; nothing was activated\n")
        return Exit.INSTALL_FAILED


if __name__ == "__main__":
    sys.exit(main())
