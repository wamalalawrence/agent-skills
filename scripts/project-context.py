#!/usr/bin/env python3
"""Derive project context from the repository itself.

The global installer cannot know which repositories a developer will open, so it
does not ask. This script answers "what project am I in?" from evidence that is
already on disk, and reports how confident each answer is.

Before v0.37.0 the answer came from `PROJECTS_JSON` in a workspace `.env`, which
had to be registered up front and was derived by globbing directories next to the
`agent-skills` clone. A repository cloned anywhere else was simply unknown.

The contract that matters most: **a repository with no agent-skills
configuration is a normal, supported case.** It gets planning, engineering,
review, and testing on inferred context. Configuration is requested only when a
specific task needs a specific fact that cannot be inferred safely — and this
script says which facts those are, in `needs_confirmation`.

Committed configuration still wins where it exists, because a human wrote it.
What committed configuration may *not* do is carry a secret or name a credential
identity; that boundary lives in scripts/access.py.

Usage:
  project-context.py                 human-readable report
  project-context.py --json          machine-readable
  project-context.py --field name    print one field and exit

Exit codes:
  0  context derived (even when sparse — sparse is not an error)
  2  the working directory is unusable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Build-system detection. Ordered: the first manifest that matches wins, so a
# polyglot repo reports its primary stack rather than an arbitrary one.
STACK_MARKERS = (
    ("java", ("pom.xml",), "maven"),
    ("java", ("build.gradle", "build.gradle.kts"), "gradle"),
    ("typescript", ("package.json",), "node"),
    ("python", ("pyproject.toml", "requirements.txt", "setup.py"), "python"),
    ("go", ("go.mod",), "go"),
    ("rust", ("Cargo.toml",), "cargo"),
    ("dotnet", ("global.json",), "dotnet"),
    ("ruby", ("Gemfile",), "bundler"),
    ("php", ("composer.json",), "composer"),
    ("elixir", ("mix.exs",), "mix"),
)

NODE_LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("package-lock.json", "npm"),
)

# Default build and format commands per build system. These are hints an agent
# should confirm, not commands to run blindly, which is why they land in
# `needs_confirmation` when nothing in the repo corroborates them.
DEFAULT_COMMANDS = {
    "maven": ("mvn clean verify", ""),
    "gradle": ("./gradlew build", ""),
    "go": ("go build ./... && go test ./...", "gofmt -l ."),
    "cargo": ("cargo test", "cargo fmt --check"),
    "dotnet": ("dotnet test", "dotnet format --verify-no-changes"),
    "bundler": ("bundle exec rake", ""),
    "composer": ("composer test", ""),
    "mix": ("mix test", "mix format --check-formatted"),
    "python": ("pytest", ""),
}


def run_git(args, cwd):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def detect_git_root(cwd):
    top = run_git(["rev-parse", "--show-toplevel"], cwd)
    return Path(top) if top else None


def detect_remote(root):
    return run_git(["config", "--get", "remote.origin.url"], root) or ""


def repo_slug(remote):
    """Extract `owner/name` from a git remote, for display and tracker lookups."""
    if not remote:
        return ""
    cleaned = re.sub(r"\.git$", "", remote.strip())
    cleaned = re.sub(r"^[a-z0-9+]+://", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^[^@/]+@", "", cleaned)
    cleaned = cleaned.replace(":", "/", 1)
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) >= 3:
        return "/".join(parts[-2:])
    if len(parts) == 2:
        return parts[-1]
    return ""


def detect_base_branch(root):
    """Find the repository's default branch, preferring recorded facts.

    Order: the remote's own HEAD, then a local branch that conventionally is the
    default, then the current branch. Reported with a source so an agent knows
    whether it is a fact or a guess.
    """
    head = run_git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], root)
    if head:
        name = head.rsplit("/", 1)[-1]
        if name:
            return name, "origin/HEAD"
    for candidate in ("main", "master", "develop", "trunk"):
        if run_git(["rev-parse", "--verify", "--quiet",
                    "refs/remotes/origin/%s" % candidate], root):
            return candidate, "origin branch exists"
    for candidate in ("main", "master", "develop", "trunk"):
        if run_git(["rev-parse", "--verify", "--quiet", "refs/heads/%s" % candidate], root):
            return candidate, "local branch exists"
    current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if current and current != "HEAD":
        return current, "current branch (guess)"
    return "", "undetermined"


def detect_current_branch(root):
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""


def detect_stack(root):
    for stack, markers, build_system in STACK_MARKERS:
        for marker in markers:
            if (root / marker).is_file():
                return stack, build_system, marker
    return "other", "unknown", ""


def detect_package_manager(root, build_system):
    if build_system != "node":
        return ""
    for lockfile, manager in NODE_LOCKFILES:
        if (root / lockfile).is_file():
            return manager
    return "npm"


def read_package_json_scripts(root):
    path = root / "package.json"
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def node_commands(root, manager):
    """Build node commands from the scripts that actually exist.

    Guessing `npm test` for a repo with no test script produces a command that
    fails for a reason unrelated to the change under review, which is worse than
    reporting that no command was found.
    """
    scripts = read_package_json_scripts(root)
    install = "%s install" % manager if manager != "npm" else "npm ci"
    build_parts = [install]
    if "build" in scripts:
        build_parts.append("%s run build" % manager)
    if "test" in scripts:
        build_parts.append("%s test" % manager)
    build = " && ".join(build_parts) if len(build_parts) > 1 else ""

    format_parts = []
    for name in ("lint", "format:check", "format"):
        if name in scripts:
            format_parts.append("%s run %s" % (manager, name))
            break
    return build, (format_parts[0] if format_parts else "")


def detect_python_commands(root):
    if (root / "tox.ini").is_file():
        return "tox", ""
    if (root / "noxfile.py").is_file():
        return "nox", ""
    fmt = ""
    try:
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        pyproject = ""
    if "[tool.ruff" in pyproject:
        fmt = "ruff check . && ruff format --check ."
    elif "[tool.black" in pyproject:
        fmt = "black --check ."
    return "pytest", fmt


def detect_commands(root, build_system, manager):
    if build_system == "node":
        return node_commands(root, manager)
    if build_system == "python":
        return detect_python_commands(root)
    if build_system == "gradle":
        wrapper = "./gradlew build" if (root / "gradlew").is_file() else "gradle build"
        return wrapper, ""
    return DEFAULT_COMMANDS.get(build_system, ("", ""))


def detect_ci(root):
    found = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        count = len(list(workflows.glob("*.yml")) + list(workflows.glob("*.yaml")))
        if count:
            found.append("github-actions (%d workflow(s))" % count)
    for name, label in (
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        ("azure-pipelines.yml", "azure-pipelines"),
        (".circleci/config.yml", "circleci"),
        (".travis.yml", "travis"),
        ("bitbucket-pipelines.yml", "bitbucket-pipelines"),
    ):
        if (root / name).exists():
            found.append(label)
    return found


def read_simple_yaml(path):
    """Read the flat/one-level YAML shapes this repository documents."""
    result = {}
    if not path.is_file():
        return result
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    current = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            key, sep, value = raw.partition(":")
            if not sep:
                continue
            current = key.strip()
            value = clean_scalar(value)
            result[current] = value if value else {}
            continue
        if current is None or not isinstance(result.get(current), dict):
            continue
        key, sep, value = raw.strip().partition(":")
        if sep:
            result[current][key.strip()] = clean_scalar(value)
    return result


def clean_scalar(value):
    value = value.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    value = re.sub(r"\s+#.*$", "", value)
    return value.strip().strip("'\"")


def detect_committed_config(root):
    path = root / ".agent-skills.yml"
    if not path.is_file():
        return {}, ""
    return read_simple_yaml(path), str(path)


def detect_repo_knowledge(root):
    directory = root / ".agent-skills" / "knowledge"
    if not directory.is_dir():
        return {"present": False, "lessons": 0, "path": ""}
    lessons = list((directory / "lessons").glob("*.md")) if (directory / "lessons").is_dir() else []
    return {"present": True, "lessons": len(lessons), "path": str(directory)}


def detect_vendored_skills(root):
    directory = root / ".agent-skills" / "skills"
    return str(directory) if directory.is_dir() else ""


def detect_mode(root, committed):
    """Report the execution mode without ever stopping the caller.

    `global` is the new local default. `in-repo` is what a cloud agent uses.
    `local-workspace` is the pre-0.37 layout, still recognised so an existing
    install keeps behaving as its owner expects.
    """
    override = os.environ.get("AGENT_SKILLS_MODE", "").strip()
    if override in ("global", "in-repo", "local-workspace"):
        return override, "AGENT_SKILLS_MODE"
    if str(committed.get("mode", "")).strip() == "in-repo":
        return "in-repo", "committed .agent-skills.yml"
    home = os.environ.get("AGENT_SKILLS_HOME") or str(Path.home() / ".agent-skills")
    if (Path(home) / "install.json").is_file():
        return "global", "global installation present"
    workspace = os.environ.get("WORKSPACE_ROOT")
    if workspace and (Path(workspace) / ".env").is_file():
        return "local-workspace", "legacy ${WORKSPACE_ROOT}/.env"
    if (root / ".agent-skills.yml").is_file():
        return "in-repo", "committed .agent-skills.yml"
    # No configuration anywhere is a supported case, not a failure.
    return "global", "no configuration found; using inference only"


def project_slug(name):
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")
    return slug or "unknown-project"


def build_context(cwd):
    root = detect_git_root(cwd)
    in_git = root is not None
    if root is None:
        root = cwd

    committed, committed_path = detect_committed_config(root)
    project_block = committed.get("project")
    if not isinstance(project_block, dict):
        project_block = {}

    remote = detect_remote(root) if in_git else ""
    stack, build_system, marker = detect_stack(root)
    manager = detect_package_manager(root, build_system)
    build, fmt = detect_commands(root, build_system, manager)
    base_branch, branch_source = detect_base_branch(root) if in_git else ("", "not a git repository")
    mode, mode_source = detect_mode(root, committed)

    sources = {}
    needs_confirmation = []

    def pick(field, inferred, inferred_source, committed_value):
        """Committed configuration wins; inference fills the gaps."""
        if committed_value:
            sources[field] = "committed .agent-skills.yml"
            return committed_value
        sources[field] = inferred_source
        return inferred

    name = pick("name", root.name, "repository directory name", project_block.get("name"))
    stack = pick(
        "stack",
        stack,
        "manifest: %s" % marker if marker else "no build manifest found",
        project_block.get("stack"),
    )
    base_branch = pick("base_branch", base_branch, branch_source, project_block.get("base_branch"))
    build = pick(
        "build",
        build,
        "inferred from %s" % build_system if build else "not determined",
        project_block.get("build"),
    )
    fmt = pick(
        "format",
        fmt,
        "inferred from %s" % build_system if fmt else "not determined",
        project_block.get("format"),
    )

    if not build:
        needs_confirmation.append(
            "build command: no build/test command could be inferred. Ask the user, or read "
            "the CI workflow, before claiming a change is validated."
        )
    elif sources.get("build", "").startswith("inferred"):
        needs_confirmation.append(
            "build command %r is inferred from the build system, not read from this "
            "repository. Confirm it before treating a run as authoritative." % build
        )
    if not in_git:
        needs_confirmation.append(
            "this directory is not a git repository, so branch, remote, and diff-based "
            "work are unavailable."
        )
    if base_branch and branch_source == "current branch (guess)" and not project_block.get(
        "base_branch"
    ):
        needs_confirmation.append(
            "base branch %r is a guess from the current checkout. Confirm before opening "
            "a pull request against it." % base_branch
        )

    return {
        "schema": "agent-skills.project-context/v1",
        "mode": mode,
        "mode_source": mode_source,
        "cwd": str(cwd),
        "root": str(root),
        "is_git_repository": in_git,
        "name": name,
        "slug": project_slug(str(name)),
        "remote": remote,
        "repo_slug": repo_slug(remote),
        "current_branch": detect_current_branch(root) if in_git else "",
        "base_branch": base_branch,
        "stack": stack,
        "build_system": build_system,
        "package_manager": manager,
        "build": build,
        "format": fmt,
        "ci": detect_ci(root),
        "committed_config": committed_path,
        "vendored_skills": detect_vendored_skills(root),
        "repo_knowledge": detect_repo_knowledge(root),
        "field_sources": sources,
        "needs_confirmation": needs_confirmation,
        "notes": [
            "No configuration is required to work in this repository. Anything listed "
            "under needs_confirmation is a fact to establish before it matters, not a "
            "blocker for planning or read-only work.",
            "Credentials are resolved separately and only when a task needs them: "
            "agent-skills access resolve --service <name>",
        ],
    }


def render(context):
    lines = []
    lines.append("project: %s" % context["name"])
    lines.append("  slug          : %s" % context["slug"])
    lines.append("  root          : %s" % context["root"])
    lines.append("  mode          : %s (%s)" % (context["mode"], context["mode_source"]))
    if context["remote"]:
        lines.append("  remote        : %s" % context["remote"])
    if context["repo_slug"]:
        lines.append("  repo          : %s" % context["repo_slug"])
    if context["current_branch"]:
        lines.append("  branch        : %s" % context["current_branch"])
    lines.append("  base branch   : %s [%s]"
                 % (context["base_branch"] or "(unknown)",
                    context["field_sources"].get("base_branch", "")))
    lines.append("  stack         : %s [%s]"
                 % (context["stack"], context["field_sources"].get("stack", "")))
    if context["package_manager"]:
        lines.append("  package mgr   : %s" % context["package_manager"])
    lines.append("  build         : %s [%s]"
                 % (context["build"] or "(not determined)",
                    context["field_sources"].get("build", "")))
    lines.append("  format        : %s [%s]"
                 % (context["format"] or "(not determined)",
                    context["field_sources"].get("format", "")))
    if context["ci"]:
        lines.append("  ci            : %s" % ", ".join(context["ci"]))
    if context["committed_config"]:
        lines.append("  committed cfg : %s" % context["committed_config"])
    if context["vendored_skills"]:
        lines.append("  vendored skills: %s" % context["vendored_skills"])
    knowledge = context["repo_knowledge"]
    if knowledge["present"]:
        lines.append("  repo knowledge: %s (%d lesson(s))"
                     % (knowledge["path"], knowledge["lessons"]))
    if context["needs_confirmation"]:
        lines.append("")
        lines.append("confirm before relying on:")
        for item in context["needs_confirmation"]:
            lines.append("  - %s" % item)
    else:
        lines.append("")
        lines.append("every field above was read from this repository.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--field", default="", help="Print a single field and exit.")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd)
    if not cwd.is_dir():
        print("FAIL --cwd is not a directory: %s" % args.cwd, file=sys.stderr)
        return 2

    context = build_context(cwd.resolve())

    if args.field:
        value = context.get(args.field)
        if value is None:
            print("FAIL unknown field %r" % args.field, file=sys.stderr)
            return 2
        if isinstance(value, (list, dict)):
            print(json.dumps(value))
        else:
            print(value)
        return 0

    print(json.dumps(context, indent=2, sort_keys=True) if args.json else render(context))
    return 0


if __name__ == "__main__":
    sys.exit(main())
