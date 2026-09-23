#!/usr/bin/env python3
"""The Execution Guard rule catalogue.

Every rule here is deterministic: the same action, cwd, and filesystem produce
the same decision, with no model in the path. That is a requirement, not a
preference. Asking a language model "does `rm -rf /` look dangerous?" makes the
answer probabilistic exactly where it must not be, and puts a network round trip
in front of every shell command.

Three tiers, and the difference matters for configuration:

  * **floor** rules encode the repository's own
    [destructive-action policy](../docs/destructive-action-safety.md). Their
    outcome cannot be lowered by any configuration layer, including the user's.
    They are the hard floor the whole design exists to hold.
  * **graduated** rules resolve to ASK. They cover real state mutation where a
    human answer is the right control, not a refusal.
  * **advisory** rules resolve to ALLOW with a note, so an audit reader can see
    the action was recognised rather than merely unmatched.

A rule states five things, because a denial that only says "denied" teaches the
agent nothing and gets the guard switched off:

    rule id | risk category | reason | target | safe alternative

The catalogue is intentionally readable top to bottom. When a rule and the
written policy disagree, the stricter of the two wins and the mismatch is a bug
in this file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import guard_paths as gp

ALLOW = "ALLOW"
ASK = "ASK"
DENY = "DENY"

_ORDER = {ALLOW: 0, ASK: 1, DENY: 2}


def strictest(*outcomes: str) -> str:
    """The strictest of several outcomes. DENY beats ASK beats ALLOW."""
    best = ALLOW
    for outcome in outcomes:
        if _ORDER.get(outcome, 0) > _ORDER[best]:
            best = outcome
    return best


# Risk categories, used for reporting and for organisation policy that wants to
# escalate a whole class at once.
CATEGORIES = (
    "filesystem",
    "disk",
    "database",
    "infrastructure",
    "cloud",
    "container",
    "vcs",
    "credential",
    "remote-execution",
    "observability",
    "parse",
    "policy",
    "access",
)


@dataclass(frozen=True)
class Rule:
    identifier: str
    outcome: str
    category: str
    summary: str
    alternative: str
    floor: bool = False


@dataclass
class Finding:
    rule: Rule
    outcome: str
    reason: str
    target: str | None = None
    detail: dict = field(default_factory=dict)


def _rule(*args, **kwargs) -> Rule:
    rule = Rule(*args, **kwargs)
    CATALOGUE[rule.identifier] = rule
    return rule


CATALOGUE: dict[str, Rule] = {}

# --- filesystem ------------------------------------------------------------
FS_ROOT_RECURSIVE_DELETE = _rule(
    "FS_ROOT_RECURSIVE_DELETE", DENY, "filesystem",
    "recursive deletion of a system path",
    "Name the directory you actually mean, inside the working repository.",
    floor=True,
)
FS_HOME_RECURSIVE_DELETE = _rule(
    "FS_HOME_RECURSIVE_DELETE", DENY, "filesystem",
    "recursive deletion of the home directory or a credential directory inside it",
    "Delete the specific project directory instead; ~/.ssh, ~/.aws and friends "
    "hold credentials whose loss is not recoverable from this machine.",
    floor=True,
)
FS_OUTSIDE_WORKSPACE_DELETE = _rule(
    "FS_OUTSIDE_WORKSPACE_DELETE", DENY, "filesystem",
    "recursive deletion escapes the working repository",
    "Run the delete from inside the repository it belongs to, with a relative path.",
    floor=True,
)
FS_SYMLINK_ESCAPE = _rule(
    "FS_SYMLINK_ESCAPE", DENY, "filesystem",
    "the path looks repository-local but resolves outside it through a symlink",
    "Resolve the target first (`readlink -f <path>`) and delete the real location "
    "deliberately, if that is what you meant.",
    floor=True,
)
FS_UNRESOLVED_RECURSIVE_DELETE = _rule(
    "FS_UNRESOLVED_RECURSIVE_DELETE", ASK, "filesystem",
    "recursive deletion of a target that could not be resolved",
    "List the target first (`ls -la <path>`), or substitute the literal path.",
)
FS_WORKSPACE_RECURSIVE_DELETE = _rule(
    "FS_WORKSPACE_RECURSIVE_DELETE", ASK, "filesystem",
    "recursive deletion of tracked working-tree content",
    "Delete the build output instead, or let `git clean -n` show you what would go.",
)
FS_SYSTEM_DELETE = _rule(
    "FS_SYSTEM_DELETE", DENY, "filesystem",
    "deletion of a system or credential file",
    "Nothing in a repository task needs to remove a file from a system path.",
    floor=True,
)
FS_SYSTEM_WRITE = _rule(
    "FS_SYSTEM_WRITE", DENY, "filesystem",
    "write or truncation of a system file",
    "Write to a file inside the repository and have an operator install it.",
    floor=True,
)
FS_PERMISSION_WIDENING = _rule(
    "FS_PERMISSION_WIDENING", ASK, "filesystem",
    "recursive permission or ownership change",
    "Scope the change to the one file that needs it; 0777 on a tree is rarely the fix.",
)
FS_MOVE_OVER_SYSTEM = _rule(
    "FS_MOVE_OVER_SYSTEM", DENY, "filesystem",
    "move or overwrite targeting a system path",
    "Stage the file inside the repository and hand the install step to an operator.",
    floor=True,
)

# --- disk ------------------------------------------------------------------
DISK_FORMAT = _rule(
    "DISK_FORMAT", DENY, "disk",
    "filesystem creation or volume erase",
    "Disk formatting is an operator action performed from a console, never from an agent.",
    floor=True,
)
DISK_RAW_WRITE = _rule(
    "DISK_RAW_WRITE", DENY, "disk",
    "raw block-device write",
    "Write the image to a file and let an operator flash the device.",
    floor=True,
)
DISK_SECURE_ERASE = _rule(
    "DISK_SECURE_ERASE", DENY, "disk",
    "secure erase or partition-table wipe",
    "Nothing recoverable follows this command; it belongs to an operator runbook.",
    floor=True,
)

# --- database --------------------------------------------------------------
DB_DROP = _rule(
    "DB_DROP", DENY, "database",
    "DROP of a database, schema, table, or index",
    "Inspect the schema first (`\\d+`, `SHOW CREATE TABLE`) and propose a reviewed "
    "forward-only migration.",
    floor=True,
)
DB_TRUNCATE = _rule(
    "DB_TRUNCATE", DENY, "database",
    "TRUNCATE removes every row without a WHERE clause",
    "Count first (`SELECT count(*)`), then propose a scoped, reviewed deletion.",
    floor=True,
)
DB_UNSCOPED_WRITE = _rule(
    "DB_UNSCOPED_WRITE", DENY, "database",
    "DELETE or UPDATE with no WHERE clause",
    "Add a WHERE clause and confirm its selectivity with a SELECT count(*) first.",
    floor=True,
)
DB_ADMIN_DESTRUCTIVE = _rule(
    "DB_ADMIN_DESTRUCTIVE", DENY, "database",
    "database administration command that discards data",
    "Use the read-only inspection command for this engine and propose a runbook.",
    floor=True,
)
DB_SCOPED_WRITE = _rule(
    "DB_SCOPED_WRITE", ASK, "database",
    "scoped data mutation",
    "Confirm the row count the WHERE clause selects before running it.",
)
DB_MIGRATION = _rule(
    "DB_MIGRATION", ASK, "database",
    "schema migration",
    "Run the migration's dry-run or plan output first.",
)

# --- infrastructure --------------------------------------------------------
IAC_DESTROY = _rule(
    "IAC_DESTROY", DENY, "infrastructure",
    "infrastructure destroy",
    "Run `terraform plan -destroy` and hand the output to an operator.",
    floor=True,
)
IAC_APPLY_PRODUCTION = _rule(
    "IAC_APPLY_PRODUCTION", DENY, "infrastructure",
    "infrastructure apply against production state",
    "Produce `terraform plan` output and route the apply through the deployment pipeline.",
    floor=True,
)
IAC_APPLY = _rule(
    "IAC_APPLY", ASK, "infrastructure",
    "infrastructure apply",
    "Review `terraform plan` output before applying.",
)
K8S_DELETE = _rule(
    "K8S_DELETE", DENY, "infrastructure",
    "Kubernetes object deletion against a non-ephemeral context",
    "Use `kubectl get` / `describe` / `logs` to investigate, and route deletion "
    "through the cluster's change process.",
    floor=True,
)
K8S_DISRUPTIVE = _rule(
    "K8S_DISRUPTIVE", DENY, "infrastructure",
    "Kubernetes node drain, eviction, or release uninstall",
    "`kubectl get nodes` and `helm status` describe the same state without moving workloads.",
    floor=True,
)
K8S_MUTATE = _rule(
    "K8S_MUTATE", ASK, "infrastructure",
    "Kubernetes state mutation",
    "`kubectl diff -f` shows the effect before it is applied.",
)

# --- cloud -----------------------------------------------------------------
CLOUD_DESTRUCTIVE = _rule(
    "CLOUD_DESTRUCTIVE", DENY, "cloud",
    "cloud-provider delete, terminate, or recursive removal",
    "Use the provider's `describe-*` / `list-*` verb and hand the deletion to an operator.",
    floor=True,
)
CLOUD_BACKUP_DESTRUCTIVE = _rule(
    "CLOUD_BACKUP_DESTRUCTIVE", DENY, "cloud",
    "deletion or expiry of a backup, snapshot, or retention policy",
    "Backups are the last line of defence against exactly this command. List them "
    "instead, and route removal through a separate approval and credential.",
    floor=True,
)
CLOUD_IAM_DESTRUCTIVE = _rule(
    "CLOUD_IAM_DESTRUCTIVE", DENY, "cloud",
    "IAM, key, or secret mutation",
    "Read the policy (`get-*` / `describe-*`) and propose the change as a reviewed "
    "infrastructure diff.",
    floor=True,
)
CLOUD_MUTATE = _rule(
    "CLOUD_MUTATE", ASK, "cloud",
    "cloud-provider state mutation",
    "Add `--dry-run` where the provider supports it, or run the `describe-*` verb first.",
)

# --- access ------------------------------------------------------------------
ACCESS_UNQUALIFIED_WRITE = _rule(
    "ACCESS_UNQUALIFIED_WRITE", ASK, "access",
    "a write to a known external system without a passing access check",
    "Run `agent-skills access check --system <id> --op write --target <url-or-key> "
    "--user-authorised`; a passing check allows the write for 30 minutes.",
)

# --- observability ---------------------------------------------------------
SECURITY_CONTROL_DISABLE = _rule(
    "SECURITY_CONTROL_DISABLE", DENY, "observability",
    "monitoring, audit logging, or security control being disabled or deleted",
    "This is the control that would record the rest of the incident. Leave it on and "
    "raise the noise problem with its owner.",
    floor=True,
)

# --- containers ------------------------------------------------------------
CONTAINER_PRUNE = _rule(
    "CONTAINER_PRUNE", DENY, "container",
    "Docker prune or volume removal discards data outside the current task",
    "`docker ps -a` and `docker volume ls` show what exists; remove the one container "
    "you created by name.",
    floor=True,
)
CONTAINER_MUTATE = _rule(
    "CONTAINER_MUTATE", ASK, "container",
    "container or compose teardown that can remove volumes",
    "`docker compose down` without `-v` keeps named volumes.",
)

# --- version control -------------------------------------------------------
VCS_FORCE_PUSH_PROTECTED = _rule(
    "VCS_FORCE_PUSH_PROTECTED", DENY, "vcs",
    "force push to a shared or protected branch",
    "Push the branch under a new name and open a pull request.",
    floor=True,
)
VCS_FORCE_PUSH = _rule(
    "VCS_FORCE_PUSH", ASK, "vcs",
    "force push rewrites published history",
    "`git push --force-with-lease` on your own feature branch, after confirming nobody "
    "else has pushed to it.",
)
VCS_PUSH = _rule(
    "VCS_PUSH", ASK, "vcs",
    "remote mutation",
    "Confirm the branch and remote first with `git status -sb`.",
)
VCS_DESTRUCTIVE_CLEAN = _rule(
    "VCS_DESTRUCTIVE_CLEAN", DENY, "vcs",
    "clean or checkout that discards untracked content outside the repository",
    "`git clean -n` lists what would be removed without removing it.",
    floor=True,
)
VCS_LOCAL_DISCARD = _rule(
    "VCS_LOCAL_DISCARD", ASK, "vcs",
    "discards uncommitted local work",
    "`git stash` keeps the same working tree recoverable.",
)
VCS_HISTORY_REWRITE = _rule(
    "VCS_HISTORY_REWRITE", ASK, "vcs",
    "rewrites local history",
    "Confirm the branch is unpublished before rewriting it.",
)

# --- credentials and remote execution --------------------------------------
CRED_EXFILTRATION = _rule(
    "CRED_EXFILTRATION", DENY, "credential",
    "credential material being read into a network request",
    "A discovered credential is evidence of a leak, not a tool. Report it and "
    "recommend rotation; do not transmit it.",
    floor=True,
)
CRED_HARVEST = _rule(
    "CRED_HARVEST", ASK, "credential",
    "bulk read of credential stores",
    "Name the one file you need. Sweeping for secrets is a security-review activity "
    "that produces findings, not an acquisition step.",
)
REMOTE_EXEC_PIPELINE = _rule(
    "REMOTE_EXEC_PIPELINE", DENY, "remote-execution",
    "downloaded content piped straight into an interpreter",
    "Download to a file, read it, then run it deliberately: "
    "`curl -fsSL URL -o setup.sh` then review, then `sh setup.sh`.",
    floor=True,
)
REMOTE_EXEC_DECODED = _rule(
    "REMOTE_EXEC_DECODED", DENY, "remote-execution",
    "decoded or obfuscated content piped into an interpreter",
    "Decode to a file and read it before running anything.",
    floor=True,
)
REMOTE_EXEC_INLINE = _rule(
    "REMOTE_EXEC_INLINE", DENY, "remote-execution",
    "inline program that downloads and executes code",
    "Fetch the payload to a file and review it first.",
    floor=True,
)
REMOTE_EXEC_EVAL = _rule(
    "REMOTE_EXEC_EVAL", ASK, "remote-execution",
    "evaluation of dynamically constructed shell text",
    "Print the string first and run the result deliberately.",
)
PKG_UNPINNED_REMOTE = _rule(
    "PKG_UNPINNED_REMOTE", ASK, "remote-execution",
    "package installation from a URL or version-control reference",
    "Install from the registry with a pinned version, or vendor the dependency.",
)

# --- parse and policy ------------------------------------------------------
EXEC_UNRESOLVED_COMMAND = _rule(
    "EXEC_UNRESOLVED_COMMAND", ASK, "parse",
    "the program being run could not be identified",
    "Name the program directly rather than through a variable or a substitution.",
)
EXEC_OPAQUE_INPUT = _rule(
    "EXEC_OPAQUE_INPUT", ASK, "remote-execution",
    "an interpreter or database client is fed from a source this check cannot read",
    "Read the file first, then run it deliberately — `cat <file>` before `sh <file>`.",
)
DB_OPAQUE_STATEMENT = _rule(
    "DB_OPAQUE_STATEMENT", ASK, "database",
    "a database client was given statements this check cannot see",
    "Print the file first, or pass the statement inline so it can be reviewed.",
)
FETCH_THEN_EXECUTE = _rule(
    "FETCH_THEN_EXECUTE", DENY, "remote-execution",
    "content is downloaded to a file and executed in the same command",
    "Download, read the file, then run it as a separate deliberate step.",
    floor=True,
)
PARSE_UNRESOLVED = _rule(
    "PARSE_UNRESOLVED", ASK, "parse",
    "the command could not be fully decomposed, so its effect is not known",
    "Split it into separate, individually reviewable commands.",
)
PARSE_UNRESOLVED_HIGH_RISK = _rule(
    "PARSE_UNRESOLVED_HIGH_RISK", DENY, "parse",
    "the command could not be decomposed and its text contains a hard-floor pattern",
    "Split it into separate commands so each can be evaluated on its own.",
    floor=True,
)
POLICY_REPOSITORY_OVERRIDE = _rule(
    "POLICY_REPOSITORY_OVERRIDE", ASK, "policy",
    "repository configuration attempted to weaken the guard",
    "Repository configuration may add restrictions only. Machine-scope policy is the "
    "only place a non-floor rule can be relaxed.",
)
POLICY_CUSTOM_DENY = _rule(
    "POLICY_CUSTOM_DENY", DENY, "policy",
    "matched a locally configured deny pattern",
    "See the policy file that added this pattern.",
)
POLICY_CUSTOM_ASK = _rule(
    "POLICY_CUSTOM_ASK", ASK, "policy",
    "matched a locally configured ask pattern",
    "See the policy file that added this pattern.",
)


# ---------------------------------------------------------------------------
# Helpers shared by several checks
# ---------------------------------------------------------------------------
DELETE_COMMANDS = {"rm", "unlink", "rmdir", "srm", "trash"}
RECURSIVE_FLAGS = {"-r", "-R", "--recursive", "-rf", "-fr", "-Rf", "-fR", "-rvf", "-rfv"}
FORCE_FLAGS = {"-f", "--force"}

PROTECTED_BRANCHES = re.compile(
    r"^(?:main|master|develop|development|trunk|prod|production|stable|"
    r"release(?:[/-].*)?|hotfix(?:[/-].*)?|v\d+(?:\.\d+)*)$",
    re.IGNORECASE,
)

PRODUCTION_MARKER = re.compile(
    r"(?:^|[^a-z0-9])(prod|production|prd|live)(?:[^a-z0-9]|$)", re.IGNORECASE
)

EPHEMERAL_CLUSTER = re.compile(
    r"(?:kind-|minikube|docker-desktop|docker-for-desktop|k3d-|rancher-desktop|colima|"
    r"microk8s|localhost|127\.0\.0\.1)",
    re.IGNORECASE,
)

NETWORK_FETCHERS = {"curl", "wget", "fetch", "http", "https", "httpie", "aria2c", "axel"}
DECODERS = {"base64", "openssl", "xxd", "uudecode", "gunzip", "zcat", "gzip", "bunzip2"}
INTERPRETERS = {
    "sh", "bash", "zsh", "dash", "ksh", "ash", "fish", "csh", "tcsh",
    "python", "python2", "python3", "perl", "ruby", "node", "nodejs", "php",
}

CREDENTIAL_PATHS = re.compile(
    r"(?:\.ssh/|\.aws/|\.gnupg/|\.kube/config|\.docker/config|\.netrc|\.npmrc|"
    r"\.git-credentials|id_rsa|id_ed25519|id_ecdsa|\.pem\b|\.p12\b|\.pfx\b|"
    r"credentials(?:\.json)?\b|\.env(?:\.[a-z]+)?\b|service[_-]account.*\.json)",
    re.IGNORECASE,
)

SECRET_ENV_NAMES = re.compile(
    r"\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|PRIVATE_KEY|"
    r"ACCESS_KEY|CREDENTIAL)[A-Z0-9_]*\b"
)


def _has_flag(command, *names: str) -> bool:
    """Whether any of `names` appears, including inside a combined short flag."""
    for arg in command.args:
        if arg in names:
            return True
        if arg.startswith("--"):
            continue
        if arg.startswith("-") and len(arg) > 1:
            for name in names:
                if len(name) == 2 and name.startswith("-") and name[1] in arg[1:]:
                    return True
    return False


def _flag_value(command, *names: str) -> str | None:
    args = command.args
    for index, arg in enumerate(args):
        for name in names:
            if arg == name and index + 1 < len(args):
                return args[index + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return None


def _positional(command) -> list[str]:
    """Arguments that are not flags and not the value of a flag."""
    out: list[str] = []
    skip_next = False
    for arg in command.args:
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            continue
        out.append(arg)
    return out


def _targets(command, workspace) -> list[gp.Target]:
    return [
        gp.classify(arg, workspace)
        for arg in _positional(command)
        if gp.path_like(arg)
    ]


def _joined(command) -> str:
    return " ".join(command.argv)


# ---------------------------------------------------------------------------
# Individual checks. Each returns a list of Findings for one simple command.
# ---------------------------------------------------------------------------
def check_delete(command, workspace, context) -> list[Finding]:
    if command.name not in DELETE_COMMANDS:
        return []
    recursive = command.name in ("rmdir", "srm", "trash") or _has_flag(
        command, "-r", "-R", "--recursive"
    )
    if command.name == "rm" and not recursive and not _has_flag(command, "-f"):
        # `rm one-file.txt` is ordinary editing.
        pass
    targets = _targets(command, workspace)
    if recursive and not targets:
        return [Finding(
            FS_UNRESOLVED_RECURSIVE_DELETE, ASK,
            "recursive delete with no visible target; the paths come from "
            "somewhere this check cannot see",
        )]
    findings: list[Finding] = []
    for target in targets:
        classification = target.classification
        if target.escaped_via_symlink and recursive:
            findings.append(Finding(
                FS_SYMLINK_ESCAPE, DENY,
                "%s is inside the repository by name but resolves to %s"
                % (target.raw, target.resolved),
                target.display,
            ))
            continue
        if classification == gp.SYSTEM_ROOT:
            findings.append(Finding(
                FS_ROOT_RECURSIVE_DELETE if recursive else FS_SYSTEM_DELETE,
                DENY,
                "%s resolves to the system path %s" % (target.raw, target.resolved),
                target.display,
            ))
            continue
        if classification == gp.HOME_ROOT:
            findings.append(Finding(
                FS_HOME_RECURSIVE_DELETE, DENY,
                "%s resolves to %s, a home or credential directory"
                % (target.raw, target.resolved),
                target.display,
            ))
            continue
        if not recursive:
            continue
        if classification == gp.OUTSIDE_WORKSPACE:
            findings.append(Finding(
                FS_OUTSIDE_WORKSPACE_DELETE, DENY,
                "%s resolves to %s, outside the working repository %s"
                % (target.raw, target.resolved, workspace.root),
                target.display,
            ))
            continue
        if classification == gp.UNRESOLVED:
            findings.append(Finding(
                FS_UNRESOLVED_RECURSIVE_DELETE, ASK,
                "%s could not be resolved (%s)"
                % (target.raw, target.unresolved_reason or "unknown form"),
                target.raw,
            ))
            continue
        if classification == gp.WORKSPACE:
            if gp.looks_like_repo_root(target.resolved or "", workspace):
                findings.append(Finding(
                    FS_WORKSPACE_RECURSIVE_DELETE, ASK,
                    "%s is the repository root" % target.raw,
                    target.display,
                ))
            else:
                findings.append(Finding(
                    FS_WORKSPACE_RECURSIVE_DELETE, ASK,
                    "%s is tracked working-tree content, not build output" % target.raw,
                    target.display,
                ))
    return findings


def check_find_delete(command, workspace, context) -> list[Finding]:
    """`find / -delete` removes everything it matches without an `-exec`."""
    if command.name != "find" or not _has_flag(command, "-delete"):
        return []
    roots = [arg for arg in _positional(command) if gp.path_like(arg)] or ["."]
    targets = [gp.classify(root, workspace) for root in roots]
    worst = gp.worst(targets)
    if worst is None:
        return []
    if worst.classification in (gp.SYSTEM_ROOT, gp.HOME_ROOT):
        return [Finding(
            FS_ROOT_RECURSIVE_DELETE, DENY,
            "find -delete walks %s" % worst.resolved, worst.display,
        )]
    if worst.classification == gp.OUTSIDE_WORKSPACE:
        return [Finding(
            FS_OUTSIDE_WORKSPACE_DELETE, DENY,
            "find -delete walks %s, outside the repository" % worst.resolved,
            worst.display,
        )]
    if worst.classification != gp.WORKSPACE_DISPOSABLE:
        return [Finding(
            FS_WORKSPACE_RECURSIVE_DELETE, ASK,
            "find -delete removes every match under %s" % worst.raw, worst.display,
        )]
    return []


def check_system_write(command, workspace, context) -> list[Finding]:
    findings: list[Finding] = []
    for redirect in command.redirects:
        operator, _, path = redirect.partition(" ")
        if operator.endswith("<") or operator in ("<", "<<", "<<<"):
            continue
        target = gp.classify(path or redirect, workspace)
        if target.classification == gp.SYSTEM_ROOT:
            findings.append(Finding(
                FS_SYSTEM_WRITE, DENY,
                "redirection writes to the system path %s" % target.resolved,
                target.display,
            ))
        elif target.classification == gp.HOME_ROOT:
            findings.append(Finding(
                FS_SYSTEM_WRITE, DENY,
                "redirection writes to %s, a home or credential path" % target.resolved,
                target.display,
            ))
    if command.name in ("mv", "cp", "install", "ln", "dd", "tee", "truncate"):
        # HOME_ROOT belongs here as much as SYSTEM_ROOT. The redirection branch
        # above covers both, so `echo x > ~/.ssh/authorized_keys` was denied
        # while `cp key ~/.ssh/authorized_keys` — the same write, and the more
        # likely spelling — was allowed. A credential path does not become safe
        # because the bytes arrived by copy.
        for target in _targets(command, workspace)[1:] or _targets(command, workspace):
            if target.classification in (gp.SYSTEM_ROOT, gp.HOME_ROOT):
                findings.append(Finding(
                    FS_MOVE_OVER_SYSTEM, DENY,
                    "%s targets %s" % (command.name, target.resolved),
                    target.display,
                ))
                break
    if command.name in ("chmod", "chown", "chgrp"):
        recursive = _has_flag(command, "-R", "-r")
        wide = any(arg in ("777", "0777", "a+rwx", "666", "0666") for arg in command.args)
        targets = _targets(command, workspace)
        worst = gp.worst(targets)
        if worst is not None and worst.classification in (gp.SYSTEM_ROOT, gp.HOME_ROOT):
            findings.append(Finding(
                FS_SYSTEM_WRITE, DENY,
                "%s changes permissions on %s" % (command.name, worst.resolved),
                worst.display,
            ))
        elif recursive or wide:
            findings.append(Finding(
                FS_PERMISSION_WIDENING, ASK,
                "%s applies a %s permission change"
                % (command.name, "recursive" if recursive else "world-writable"),
                worst.display if worst else None,
            ))
    return findings


def check_disk(command, workspace, context) -> list[Finding]:
    name = command.name
    joined = _joined(command)
    if name.startswith("mkfs") or name in ("newfs", "mke2fs", "mkswap"):
        return [Finding(DISK_FORMAT, DENY, "%s creates a filesystem, erasing the device" % name)]
    if name == "diskutil" and any(
        arg.lower().startswith("erase") or arg.lower() in ("reformat", "zerodisk", "securedisk")
        for arg in command.args
    ):
        return [Finding(DISK_FORMAT, DENY, "diskutil erase destroys the volume")]
    if name in ("wipefs", "sgdisk", "sfdisk") and not _has_flag(command, "--print", "-l"):
        return [Finding(DISK_SECURE_ERASE, DENY, "%s rewrites the partition table" % name)]
    if name == "shred":
        targets = _targets(command, workspace)
        worst = gp.worst(targets)
        if worst is not None and worst.classification in (
            gp.SYSTEM_ROOT, gp.HOME_ROOT, gp.OUTSIDE_WORKSPACE,
        ):
            return [Finding(
                DISK_SECURE_ERASE, DENY,
                "shred irreversibly overwrites %s" % worst.resolved, worst.display,
            )]
    if name == "dd":
        destination = _flag_value(command, "of") or ""
        for arg in command.args:
            if arg.startswith("of="):
                destination = arg.split("=", 1)[1]
        if destination.startswith("/dev/"):
            return [Finding(
                DISK_RAW_WRITE, DENY,
                "dd writes directly to the block device %s" % destination, destination,
            )]
        if destination:
            target = gp.classify(destination, workspace)
            if target.classification in (gp.SYSTEM_ROOT, gp.HOME_ROOT):
                return [Finding(
                    DISK_RAW_WRITE, DENY,
                    "dd overwrites %s" % target.resolved, target.display,
                )]
    if name in ("hdparm", "nvme") and "secure-erase" in joined.lower():
        return [Finding(DISK_SECURE_ERASE, DENY, "%s issues a secure erase" % name)]
    return []


# --- SQL -------------------------------------------------------------------
SQL_CLIENTS = {
    "psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "clickhouse-client",
    "cockroach", "snowsql", "bq", "athena", "duckdb", "usql", "pgcli", "mycli",
}
SQL_DROP_RE = re.compile(
    r"\bdrop\s+(?:database|schema|table|index|view|materialized\s+view|"
    r"tablespace|user|role|type|sequence)\b",
    re.IGNORECASE,
)
SQL_TRUNCATE_RE = re.compile(r"\btruncate\s+(?:table\s+)?[\w.\"`\[\]]+", re.IGNORECASE)
SQL_DELETE_RE = re.compile(r"\bdelete\s+from\s+([\w.\"`\[\]]+)(.*)", re.IGNORECASE | re.DOTALL)
SQL_UPDATE_RE = re.compile(r"\bupdate\s+([\w.\"`\[\]]+)\s+set\b(.*)", re.IGNORECASE | re.DOTALL)
SQL_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)
SQL_READONLY_RE = re.compile(
    r"\b(?:set\s+transaction\s+read\s+only|begin\s+read\s+only)\b", re.IGNORECASE
)
SQL_MIGRATION_RE = re.compile(
    r"\balter\s+table\b.*\b(?:drop\s+column|drop\s+constraint|rename\s+to)\b",
    re.IGNORECASE | re.DOTALL,
)


def sql_findings(sql: str, source: str) -> list[Finding]:
    """Classify a SQL string. Shared by the shell path and the MCP path."""
    findings: list[Finding] = []
    if not sql:
        return findings
    read_only = bool(SQL_READONLY_RE.search(sql))
    if SQL_DROP_RE.search(sql):
        findings.append(Finding(DB_DROP, DENY, "%s contains a DROP statement" % source))
    if SQL_TRUNCATE_RE.search(sql):
        findings.append(Finding(DB_TRUNCATE, DENY, "%s contains TRUNCATE" % source))
    for pattern, verb in ((SQL_DELETE_RE, "DELETE"), (SQL_UPDATE_RE, "UPDATE")):
        match = pattern.search(sql)
        if not match:
            continue
        remainder = match.group(2) or ""
        if SQL_WHERE_RE.search(remainder):
            if not read_only:
                findings.append(Finding(
                    DB_SCOPED_WRITE, ASK,
                    "%s contains a %s with a WHERE clause" % (source, verb),
                    match.group(1),
                ))
        else:
            findings.append(Finding(
                DB_UNSCOPED_WRITE, DENY,
                "%s contains %s against %s with no WHERE clause"
                % (source, verb, match.group(1)),
                match.group(1),
            ))
    if SQL_MIGRATION_RE.search(sql):
        findings.append(Finding(
            DB_MIGRATION, ASK, "%s narrows a table definition" % source
        ))
    return findings


def check_database(command, workspace, context) -> list[Finding]:
    name = command.name
    findings: list[Finding] = []
    if name in ("dropdb", "dropuser"):
        return [Finding(DB_ADMIN_DESTRUCTIVE, DENY, "%s removes a database object" % name)]
    if name == "mongo" or name == "mongosh":
        joined = _joined(command)
        if re.search(r"\b(?:dropDatabase|drop|deleteMany|remove)\s*\(", joined):
            return [Finding(
                DB_ADMIN_DESTRUCTIVE, DENY, "MongoDB shell call discards a collection"
            )]
    if name in ("redis-cli", "valkey-cli"):
        joined = _joined(command).upper()
        if "FLUSHALL" in joined or "FLUSHDB" in joined:
            return [Finding(DB_ADMIN_DESTRUCTIVE, DENY, "Redis FLUSH discards every key")]
    if name in SQL_CLIENTS:
        statement = _flag_value(command, "-c", "--command", "-e", "--execute", "-q") or ""
        if not statement:
            # `psql db < file.sql` and `mysql db -e ...` both end up here; the
            # positional form is only inspected when it looks like SQL.
            for arg in _positional(command):
                if re.search(r"\b(?:select|insert|update|delete|drop|truncate)\b", arg, re.I):
                    statement = arg
                    break
        if command.here_string:
            statement = statement or command.here_string
        findings.extend(sql_findings(statement, "%s statement" % name))
        if not statement:
            # The statements are in a file, on stdin, or arriving through a
            # pipe. The guard cannot read them, and a database client whose
            # input it cannot see is not an ALLOW.
            from_file = _flag_value(command, "-f", "--file") or _has_flag(command, "-f")
            from_stdin = any(
                red.startswith("<") for red in command.redirects
            ) or command.origin == "pipeline-stage"
            if from_file or from_stdin:
                findings.append(Finding(
                    DB_OPAQUE_STATEMENT, ASK,
                    "%s runs statements this check cannot see" % name,
                ))
    if name in ("flyway", "liquibase") or (
        name in ("alembic", "rails", "manage.py", "artisan", "sequelize", "knex", "prisma")
        and any("migrat" in arg for arg in command.args)
    ):
        if any(arg in ("clean", "drop", "reset", "wipe") for arg in command.args):
            findings.append(Finding(
                DB_ADMIN_DESTRUCTIVE, DENY,
                "%s clean/reset drops the managed schema" % name,
            ))
        else:
            findings.append(Finding(DB_MIGRATION, ASK, "%s runs a schema migration" % name))
    return findings


def check_infrastructure(command, workspace, context) -> list[Finding]:
    name = command.name
    args = command.args
    findings: list[Finding] = []

    if name in ("terraform", "tofu", "terragrunt"):
        verb = next((a for a in args if not a.startswith("-")), "")
        joined = _joined(command)
        if verb == "destroy" or _has_flag(command, "-destroy", "--destroy"):
            return [Finding(IAC_DESTROY, DENY, "%s destroy tears down managed infrastructure" % name)]
        if verb == "apply":
            if PRODUCTION_MARKER.search(joined) or PRODUCTION_MARKER.search(
                context.get("environment", "") or ""
            ):
                return [Finding(
                    IAC_APPLY_PRODUCTION, DENY,
                    "%s apply names a production target" % name,
                )]
            return [Finding(IAC_APPLY, ASK, "%s apply changes real infrastructure" % name)]
        if verb in ("state",) and any(a in ("rm", "mv", "replace-provider") for a in args):
            return [Finding(IAC_DESTROY, DENY, "terraform state rm detaches managed resources")]
        if verb in ("workspace",) and "delete" in args:
            return [Finding(IAC_DESTROY, DENY, "terraform workspace delete discards state")]

    if name == "pulumi" and "destroy" in args:
        return [Finding(IAC_DESTROY, DENY, "pulumi destroy tears down the stack")]
    if name in ("cdk", "cdktf") and "destroy" in args:
        return [Finding(IAC_DESTROY, DENY, "%s destroy tears down the stack" % name)]
    if name in ("ansible", "ansible-playbook") and _has_flag(command, "--force"):
        findings.append(Finding(IAC_APPLY, ASK, "ansible run applies configuration changes"))

    if name == "kubectl" or name == "oc":
        verb = next((a for a in args if not a.startswith("-")), "")
        context_name = _flag_value(command, "--context") or context.get("kube_context", "") or ""
        namespace = _flag_value(command, "-n", "--namespace") or ""
        ephemeral = bool(EPHEMERAL_CLUSTER.search(context_name)) if context_name else False
        dry_run = any(a.startswith("--dry-run") for a in args)
        if verb == "delete":
            if dry_run:
                return []
            if ephemeral:
                return [Finding(
                    K8S_MUTATE, ASK,
                    "kubectl delete against the ephemeral context %s" % context_name,
                    context_name,
                )]
            return [Finding(
                K8S_DELETE, DENY,
                "kubectl delete against context %s namespace %s"
                % (context_name or "<current>", namespace or "<default>"),
                context_name or namespace or None,
            )]
        if verb in ("drain", "cordon", "uncordon", "taint", "evict"):
            return [Finding(K8S_DISRUPTIVE, DENY, "kubectl %s moves running workloads" % verb)]
        if verb in ("apply", "patch", "replace", "scale", "rollout", "annotate", "label",
                    "set", "edit", "exec", "cp", "port-forward"):
            if dry_run:
                return []
            return [Finding(K8S_MUTATE, ASK, "kubectl %s mutates cluster state" % verb)]

    if name == "helm":
        verb = next((a for a in args if not a.startswith("-")), "")
        if verb in ("uninstall", "delete"):
            return [Finding(K8S_DISRUPTIVE, DENY, "helm %s removes a release" % verb)]
        if verb in ("install", "upgrade", "rollback"):
            if _has_flag(command, "--dry-run"):
                return []
            return [Finding(K8S_MUTATE, ASK, "helm %s changes deployed state" % verb)]
    return findings


# --- cloud providers -------------------------------------------------------
AWS_DESTRUCTIVE_VERBS = re.compile(
    r"^(?:delete|terminate|remove|deregister|destroy|purge|revoke|disassociate|"
    r"detach|cancel|abort|stop|reboot|deactivate|disable)-", re.IGNORECASE
)
# The verb is not always first. `schedule-key-deletion`, `delete-bucket-policy`
# and `batch-delete-image` all destroy, and only one of them starts with the
# destructive word.
AWS_DESTRUCTIVE_ANYWHERE = re.compile(
    r"(?:^|-)(?:delete|deletion|terminate|destroy|purge|remove|revoke|expire)(?:-|$)",
    re.IGNORECASE,
)
AWS_BACKUP_NOUNS = re.compile(
    r"(?:snapshot|backup|recovery-point|restore|vault|replication|retention|"
    r"lifecycle|point-in-time)", re.IGNORECASE
)
AWS_IAM_SERVICES = {"iam", "kms", "secretsmanager", "ssm", "sts", "acm", "cognito-idp",
                    "organizations", "sso-admin", "identitystore"}
AWS_SECURITY_SERVICES = {"cloudtrail", "guardduty", "config", "securityhub", "inspector2",
                         "macie2", "access-analyzer", "detective", "shield", "wafv2"}
AWS_MUTATING_VERBS = re.compile(
    r"^(?:create|put|update|modify|set|attach|associate|start|run|register|"
    r"enable|import|restore|copy|tag|untag|invoke|publish|send)-", re.IGNORECASE
)


def check_cloud(command, workspace, context) -> list[Finding]:
    name = command.name
    args = command.args
    joined = _joined(command)

    if name == "aws":
        positional = [a for a in args if not a.startswith("-")]
        service = positional[0] if positional else ""
        operation = positional[1] if len(positional) > 1 else ""
        if service == "s3":
            if operation == "rm" and _has_flag(command, "--recursive"):
                return [Finding(
                    CLOUD_DESTRUCTIVE, DENY, "aws s3 rm --recursive empties a bucket prefix"
                )]
            if operation in ("rb",):
                return [Finding(CLOUD_DESTRUCTIVE, DENY, "aws s3 rb removes a bucket")]
            if operation in ("sync",) and _has_flag(command, "--delete"):
                return [Finding(
                    CLOUD_DESTRUCTIVE, DENY, "aws s3 sync --delete removes destination objects"
                )]
            if operation in ("cp", "mv", "sync"):
                return [Finding(CLOUD_MUTATE, ASK, "aws s3 %s writes to object storage" % operation)]
            return []
        if not operation:
            return []
        if AWS_DESTRUCTIVE_VERBS.match(operation) or AWS_DESTRUCTIVE_ANYWHERE.search(
            operation
        ):
            if AWS_BACKUP_NOUNS.search(operation) or service == "backup":
                return [Finding(
                    CLOUD_BACKUP_DESTRUCTIVE, DENY,
                    "aws %s %s removes recovery data" % (service, operation),
                    "%s:%s" % (service, operation),
                )]
            if service in AWS_SECURITY_SERVICES:
                return [Finding(
                    SECURITY_CONTROL_DISABLE, DENY,
                    "aws %s %s disables a security control" % (service, operation),
                    "%s:%s" % (service, operation),
                )]
            if service in AWS_IAM_SERVICES:
                return [Finding(
                    CLOUD_IAM_DESTRUCTIVE, DENY,
                    "aws %s %s mutates identity or secret material" % (service, operation),
                    "%s:%s" % (service, operation),
                )]
            return [Finding(
                CLOUD_DESTRUCTIVE, DENY,
                "aws %s %s is a destructive provider call" % (service, operation),
                "%s:%s" % (service, operation),
            )]
        if service in AWS_IAM_SERVICES and AWS_MUTATING_VERBS.match(operation):
            return [Finding(
                CLOUD_IAM_DESTRUCTIVE, DENY,
                "aws %s %s mutates identity or secret material" % (service, operation),
                "%s:%s" % (service, operation),
            )]
        if service in AWS_SECURITY_SERVICES and operation.startswith("stop-"):
            return [Finding(
                SECURITY_CONTROL_DISABLE, DENY,
                "aws %s %s stops a security control" % (service, operation),
            )]
        if AWS_MUTATING_VERBS.match(operation):
            return [Finding(
                CLOUD_MUTATE, ASK, "aws %s %s mutates cloud state" % (service, operation)
            )]
        return []

    if name in ("gcloud", "gsutil", "gsutil.py", "bq"):
        if name == "gsutil":
            if "rm" in args and (_has_flag(command, "-r", "-R") or "-m" in args):
                return [Finding(CLOUD_DESTRUCTIVE, DENY, "gsutil rm -r removes stored objects")]
            if "rm" in args:
                return [Finding(CLOUD_DESTRUCTIVE, DENY, "gsutil rm removes stored objects")]
            return []
        if "delete" in args or "remove" in args or "destroy" in args:
            if any("snapshot" in a or "backup" in a for a in args):
                return [Finding(
                    CLOUD_BACKUP_DESTRUCTIVE, DENY, "%s removes recovery data" % name
                )]
            if any(a in ("iam", "secrets", "kms") for a in args):
                return [Finding(
                    CLOUD_IAM_DESTRUCTIVE, DENY, "%s mutates identity or secret material" % name
                )]
            return [Finding(CLOUD_DESTRUCTIVE, DENY, "%s delete is a destructive call" % name)]
        if any(a in ("create", "update", "set", "add", "enable", "deploy") for a in args):
            return [Finding(CLOUD_MUTATE, ASK, "%s mutates cloud state" % name)]
        return []

    if name == "az":
        if "delete" in args or "purge" in args or "remove" in args:
            if any("backup" in a or "snapshot" in a or "restore" in a for a in args):
                return [Finding(CLOUD_BACKUP_DESTRUCTIVE, DENY, "az removes recovery data")]
            if any(a in ("keyvault", "role", "ad", "identity") for a in args):
                return [Finding(
                    CLOUD_IAM_DESTRUCTIVE, DENY, "az mutates identity or secret material"
                )]
            return [Finding(CLOUD_DESTRUCTIVE, DENY, "az delete is a destructive call")]
        if any(a in ("create", "update", "set", "deploy") for a in args):
            return [Finding(CLOUD_MUTATE, ASK, "az mutates cloud state")]
        return []

    if name in ("doctl", "flyctl", "fly", "heroku", "vercel", "netlify", "railway", "supabase"):
        if any(a in ("destroy", "delete", "rm", "remove", "purge") for a in args):
            return [Finding(
                CLOUD_DESTRUCTIVE, DENY, "%s removes a hosted resource" % name
            )]
    if name == "systemctl" and any(
        a in ("stop", "disable", "mask") for a in args
    ) and re.search(r"\b(?:auditd|falco|osquery|filebeat|fluentd|datadog|wazuh)\b", joined):
        return [Finding(
            SECURITY_CONTROL_DISABLE, DENY, "systemctl stops a security or audit agent"
        )]
    if name in ("ufw", "firewall-cmd", "iptables", "nft", "pfctl"):
        if re.search(r"\b(?:disable|--flush|-F|stop|off)\b", joined):
            return [Finding(
                SECURITY_CONTROL_DISABLE, DENY, "%s disables host firewalling" % name
            )]
    if name == "setenforce" and "0" in args:
        return [Finding(SECURITY_CONTROL_DISABLE, DENY, "setenforce 0 disables SELinux")]
    if name == "spctl" and "--master-disable" in args:
        return [Finding(SECURITY_CONTROL_DISABLE, DENY, "spctl disables Gatekeeper")]
    return []


def check_container(command, workspace, context) -> list[Finding]:
    name = command.name
    args = command.args
    if name not in ("docker", "podman", "nerdctl", "docker-compose"):
        return []
    joined = " ".join(args)
    if "prune" in args:
        if "volume" in args or "system" in args or _has_flag(command, "--volumes"):
            return [Finding(
                CONTAINER_PRUNE, DENY,
                "%s prune removes volumes and data outside this task" % name,
            )]
        return [Finding(CONTAINER_MUTATE, ASK, "%s prune removes shared local state" % name)]
    if "volume" in args and any(a in ("rm", "remove") for a in args):
        return [Finding(CONTAINER_PRUNE, DENY, "docker volume rm discards persisted data")]
    if ("compose" in args or name == "docker-compose") and "down" in args:
        if _has_flag(command, "-v", "--volumes"):
            return [Finding(
                CONTAINER_MUTATE, ASK, "compose down -v removes named volumes"
            )]
        return []
    if "rmi" in args or ("image" in args and "rm" in args):
        return [Finding(CONTAINER_MUTATE, ASK, "%s removes local images" % name)]
    if _has_flag(command, "--privileged") and "run" in args:
        return [Finding(CONTAINER_MUTATE, ASK, "privileged container has host-level access")]
    if "run" in args and re.search(r"-v\s*/:/|--mount[^\s]*source=/,", joined):
        return [Finding(
            CONTAINER_MUTATE, ASK, "container mounts the host root filesystem"
        )]
    return []


def is_protected_branch(branch: str, context: dict) -> bool:
    """Whether this branch is shared, per the built-in list plus configuration.

    Configured names are matched here rather than folded into the compiled
    pattern. Rebuilding a module-level regex per call grew it without bound and
    leaked one repository's configuration into the next evaluation in the same
    process.
    """
    if PROTECTED_BRANCHES.match(branch):
        return True
    extra = context.get("extra_protected_branches") or ()
    return any(branch == name for name in extra)


def _git_path_targets(command, workspace, verb: str) -> list[gp.Target]:
    """Path arguments of a git subcommand, excluding the subcommand itself."""
    positional = _positional(command)
    if positional and positional[0] == verb:
        positional = positional[1:]
    return [gp.classify(arg, workspace) for arg in positional if gp.path_like(arg)]


def check_vcs(command, workspace, context) -> list[Finding]:
    if command.name != "git":
        return []
    args = command.args
    verb = next((a for a in args if not a.startswith("-")), "")
    findings: list[Finding] = []

    if verb == "push":
        forced = _has_flag(command, "-f", "--force") or any(
            a.startswith("--force-with-lease") or a.startswith("--force-if-includes")
            for a in args
        )
        deleting = "--delete" in args or "-d" in args or any(
            a.startswith(":") and len(a) > 1 for a in args
        )
        refspecs = [a for a in args[args.index("push") + 1:] if not a.startswith("-")]
        branch = ""
        if len(refspecs) >= 2:
            branch = refspecs[1].split(":")[-1].lstrip("+")
        elif len(refspecs) == 1 and refspecs[0] not in ("origin", "upstream"):
            branch = refspecs[0].split(":")[-1].lstrip("+")
        if not branch:
            branch = context.get("branch", "") or ""
        protected = is_protected_branch(branch, context) if branch else False
        plus_refspec = any(a.startswith("+") for a in refspecs)
        if (forced or plus_refspec) and protected:
            return [Finding(
                VCS_FORCE_PUSH_PROTECTED, DENY,
                "force push to the protected branch %s" % branch, branch,
            )]
        if deleting and protected:
            return [Finding(
                VCS_FORCE_PUSH_PROTECTED, DENY,
                "deletes the protected remote branch %s" % branch, branch,
            )]
        if forced or plus_refspec:
            return [Finding(
                VCS_FORCE_PUSH, ASK,
                "force push rewrites remote history on %s" % (branch or "the current branch"),
                branch or None,
            )]
        return [Finding(VCS_PUSH, ASK, "pushes to a remote", branch or None)]

    if verb == "clean":
        force = _has_flag(command, "-f")
        include_ignored = _has_flag(command, "-x", "-X")
        dry_run = _has_flag(command, "-n", "--dry-run")
        if dry_run or not force:
            return []
        targets = _git_path_targets(command, workspace, verb)
        worst = gp.worst(targets)
        if worst is not None and worst.classification in (
            gp.SYSTEM_ROOT, gp.HOME_ROOT, gp.OUTSIDE_WORKSPACE,
        ):
            return [Finding(
                VCS_DESTRUCTIVE_CLEAN, DENY,
                "git clean targets %s, outside the repository" % worst.resolved,
                worst.display,
            )]
        return [Finding(
            VCS_LOCAL_DISCARD, ASK,
            "git clean removes untracked%s files" % (" and ignored" if include_ignored else ""),
        )]

    if verb == "reset" and _has_flag(command, "--hard"):
        return [Finding(VCS_LOCAL_DISCARD, ASK, "git reset --hard discards uncommitted work")]
    if verb == "checkout" and ("." in args or "--" in args) and not _has_flag(command, "-b"):
        return [Finding(VCS_LOCAL_DISCARD, ASK, "git checkout discards uncommitted changes")]
    if verb == "restore" and not _has_flag(command, "--staged"):
        return [Finding(VCS_LOCAL_DISCARD, ASK, "git restore discards uncommitted changes")]
    if verb == "stash" and any(a in ("drop", "clear") for a in args):
        return [Finding(VCS_LOCAL_DISCARD, ASK, "git stash drop/clear discards saved work")]
    if verb in ("filter-branch", "filter-repo"):
        return [Finding(VCS_HISTORY_REWRITE, ASK, "git %s rewrites every commit" % verb)]
    if verb == "rebase" and _has_flag(command, "-i", "--interactive"):
        return [Finding(VCS_HISTORY_REWRITE, ASK, "interactive rebase rewrites history")]
    if verb == "branch" and (_has_flag(command, "-D") or (
        _has_flag(command, "-d") and _has_flag(command, "--force")
    )):
        return [Finding(VCS_LOCAL_DISCARD, ASK, "git branch -D deletes an unmerged branch")]
    if verb == "update-ref" and "-d" in args:
        return [Finding(VCS_HISTORY_REWRITE, ASK, "git update-ref -d removes a ref")]
    return findings


def check_credentials(command, workspace, context) -> list[Finding]:
    """Reads of credential material, judged in the context of the pipeline."""
    findings: list[Finding] = []
    joined = _joined(command)
    if command.name in ("cat", "head", "tail", "less", "more", "bat", "strings", "xxd", "od"):
        for arg in _positional(command):
            if CREDENTIAL_PATHS.search(arg):
                findings.append(Finding(
                    CRED_HARVEST, ASK,
                    "reads credential material from %s" % arg, arg,
                ))
                break
    if command.name in ("grep", "rg", "ag", "ack") and _has_flag(command, "-r", "-R"):
        if SECRET_ENV_NAMES.search(joined) or re.search(
            r"(?:BEGIN [A-Z ]*PRIVATE KEY|AKIA|ghp_|xox[baprs]-)", joined
        ):
            findings.append(Finding(
                CRED_HARVEST, ASK,
                "recursive search for credential-shaped values",
            ))
    if command.name in ("security", "keyring", "secret-tool") and any(
        a in ("find-generic-password", "find-internet-password", "dump-keychain", "get")
        for a in command.args
    ):
        findings.append(Finding(CRED_HARVEST, ASK, "reads the OS credential store"))
    return findings


def check_inline_code(command, workspace, context) -> list[Finding]:
    """Behaviour patterns inside `python -c` / `node -e` style bodies."""
    if not command.inline_code:
        return []
    body = command.inline_code
    language = command.inline_language or "inline"
    findings: list[Finding] = []
    fetches = re.search(
        r"(?:urlopen|urlretrieve|requests\.(?:get|post)|http\.client|fetch\s*\(|"
        r"https?\.get|net/http|open-uri|URLSession|curl_init)",
        body,
    )
    executes = re.search(
        r"(?:\bexec\s*\(|\beval\s*\(|os\.system|subprocess\.(?:run|call|Popen|check_output)|"
        r"child_process|execSync|spawnSync|Function\s*\(|system\s*\(|`|IO\.popen)",
        body,
    )
    if fetches and executes:
        findings.append(Finding(
            REMOTE_EXEC_INLINE, DENY,
            "%s -c body downloads content and executes it" % language,
        ))
    # Native deletion calls. A shell-out — `os.system("rm -rf /")` — is not
    # matched here on purpose: the parser extracts the command string from the
    # call and re-parses it, so `rm -rf /` is judged by the rule that knows what
    # `rm -rf /` is, with the right path classification and the right message.
    destructive = re.search(
        r"(?:\brmtree\b|os\.remove|os\.unlink|\bunlink\b|rmSync|unlinkSync|"
        r"fs\.rm\b|FileUtils\.rm_rf|File\.delete|\bremove_tree\b)",
        body,
    )
    if destructive and re.search(r"""['"](?:/|~|\$HOME)""", body):
        findings.append(Finding(
            FS_ROOT_RECURSIVE_DELETE, DENY,
            "%s -c body deletes an absolute path recursively" % language,
        ))
    if re.search(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", body, re.IGNORECASE):
        findings.append(Finding(DB_DROP, DENY, "%s -c body issues a DROP" % language))
    return findings


def check_package_manager(command, workspace, context) -> list[Finding]:
    name = command.name
    args = command.args
    if name in ("npm", "pnpm", "yarn", "bun") and any(
        a in ("install", "i", "add", "ci") for a in args
    ):
        remote = [
            a for a in args
            if re.match(r"^(?:https?://|git\+|github:|git@|file:)", a)
        ]
        if remote:
            return [Finding(
                PKG_UNPINNED_REMOTE, ASK,
                "installs from %s rather than the registry" % remote[0], remote[0],
            )]
        return []
    if name in ("pip", "pip3", "uv") and any(a in ("install",) for a in args):
        remote = [a for a in args if re.match(r"^(?:https?://|git\+)", a)]
        if remote:
            return [Finding(
                PKG_UNPINNED_REMOTE, ASK,
                "installs from %s rather than an index" % remote[0], remote[0],
            )]
        if _has_flag(command, "--index-url", "--extra-index-url"):
            return [Finding(PKG_UNPINNED_REMOTE, ASK, "installs from a non-default index")]
        return []
    if name in ("gem", "go", "cargo") and any(a in ("install", "get") for a in args):
        remote = [a for a in args if a.startswith(("http://", "https://"))]
        if remote:
            return [Finding(
                PKG_UNPINNED_REMOTE, ASK, "installs from %s" % remote[0], remote[0]
            )]
    return []


def check_opaque_input(command, workspace, context) -> list[Finding]:
    """`bash < script.sh` — the program is known, its input is not."""
    if command.name not in INTERPRETERS and command.name not in SQL_CLIENTS:
        return []
    if command.inline_code:
        return []
    reads = [red for red in command.redirects if red.startswith("<")]
    if not reads:
        return []
    source = reads[0].partition(" ")[2] or reads[0]
    return [Finding(
        EXEC_OPAQUE_INPUT, ASK,
        "%s runs whatever %s contains" % (command.name, source), source,
    )]


def check_unresolved_command(command, workspace, context) -> list[Finding]:
    """A command whose program name the guard could not read.

    `$SHELL -c '…'` and `` `echo rm` -rf / `` both hide the program. The parse
    produced a command starting with a flag, which matched no rule and therefore
    read as ALLOW — a silent bypass rather than a visible unknown.
    """
    if not command.unresolved_name:
        return []
    return [Finding(
        EXEC_UNRESOLVED_COMMAND, ASK,
        "the program in %r is named by a variable or a substitution"
        % (command.raw[:80] or "this command"),
    )]


def check_eval(command, workspace, context) -> list[Finding]:
    if command.name == "eval":
        return [Finding(REMOTE_EXEC_EVAL, ASK, "eval executes a constructed string")]
    if command.name == "source" or command.name == ".":
        for arg in _positional(command):
            target = gp.classify(arg, workspace)
            if target.classification in (gp.OUTSIDE_WORKSPACE, gp.TEMP, gp.UNRESOLVED):
                return [Finding(
                    REMOTE_EXEC_EVAL, ASK,
                    "sources a script from %s" % target.display, target.display,
                )]
    return []


SINGLE_COMMAND_CHECKS = (
    check_delete,
    check_find_delete,
    check_opaque_input,
    check_unresolved_command,
    check_system_write,
    check_disk,
    check_database,
    check_infrastructure,
    check_cloud,
    check_container,
    check_vcs,
    check_credentials,
    check_inline_code,
    check_package_manager,
    check_eval,
)


# ---------------------------------------------------------------------------
# Pipeline-level checks
#
# `curl URL | sh` is safe in neither half on its own: `curl URL` is a read and
# `sh` is a shell. The danger is the edge between them, so these rules look at
# the pipeline rather than at one command.
# ---------------------------------------------------------------------------
def _is_decoder(command) -> bool:
    name = command.name
    if name not in DECODERS:
        return False
    if name == "base64":
        return _has_flag(command, "-d", "-D", "--decode")
    if name == "openssl":
        return "enc" in command.args and _has_flag(command, "-d")
    if name == "xxd":
        return _has_flag(command, "-r")
    return True


def _is_interpreter(command) -> bool:
    if command.name in SQL_CLIENTS and not command.args:
        # `cat drop.sql | psql` — the client runs the statements it is given.
        return True
    if command.name in INTERPRETERS:
        # `python -c '...'` in a pipeline is not "run whatever arrives"; the
        # body is what runs, and check_inline_code already judged it.
        return command.inline_code is None
    return False


def check_pipeline(pipeline, workspace, context) -> list[Finding]:
    findings: list[Finding] = []
    commands = pipeline.commands
    for index, command in enumerate(commands):
        downstream = commands[index + 1:]
        if not downstream:
            continue
        interpreters = [c for c in downstream if _is_interpreter(c)]
        if not interpreters:
            continue
        if command.name in NETWORK_FETCHERS:
            findings.append(Finding(
                REMOTE_EXEC_PIPELINE, DENY,
                "%s output is piped into %s, so unreviewed remote code runs"
                % (command.name, interpreters[0].name),
                _first_url(command),
            ))
        elif _is_decoder(command):
            findings.append(Finding(
                REMOTE_EXEC_DECODED, DENY,
                "%s output is piped into %s, hiding what will run"
                % (command.name, interpreters[0].name),
            ))
        elif command.name == "echo" or command.name == "printf":
            findings.append(Finding(
                REMOTE_EXEC_DECODED, DENY,
                "literal text is piped into %s" % interpreters[0].name,
            ))
        else:
            findings.append(Finding(
                EXEC_OPAQUE_INPUT, ASK,
                "%s output is piped into %s, which runs whatever it receives"
                % (command.name, interpreters[0].name),
            ))

    # Credential exfiltration: a credential read on one side, a network write on
    # the other. Either half alone is ordinary.
    reads_credentials = any(
        CREDENTIAL_PATHS.search(" ".join(c.argv))
        or (c.name == "env" and not c.args)
        or SECRET_ENV_NAMES.search(" ".join(c.argv))
        for c in commands
    )
    sends_network = any(
        c.name in NETWORK_FETCHERS or c.name in ("nc", "ncat", "netcat", "socat", "ssh", "scp")
        for c in commands
    )
    if reads_credentials and sends_network and len(commands) > 1:
        findings.append(Finding(
            CRED_EXFILTRATION, DENY,
            "credential material is read into a network command",
        ))
    return findings


def check_fetch_then_execute(commands, workspace, context) -> list[Finding]:
    """A fetch whose output file is executed later in the same command line.

    `curl URL -o /tmp/s | sh` is already caught as a pipeline. `curl URL -o
    /tmp/s && sh /tmp/s` is the same thing spelled with a file in between, and
    splitting it across two segments was enough to get past the pipeline rule.
    """
    downloaded: dict[str, str] = {}
    for command in commands:
        if command.name in NETWORK_FETCHERS:
            destination = _flag_value(command, "-o", "--output", "-O", "--output-document")
            url = _first_url(command)
            if destination and url:
                resolved = gp.classify(destination, workspace).resolved or destination
                downloaded[resolved] = url
            continue
        if not downloaded:
            continue
        runs_file = command.name in INTERPRETERS or command.name in ("source", ".")
        candidates = _positional(command)
        if command.name in ("chmod", "install"):
            candidates = _positional(command)
            runs_file = False
        for argument in candidates:
            resolved = gp.classify(argument, workspace).resolved or argument
            if resolved in downloaded and runs_file:
                return [Finding(
                    FETCH_THEN_EXECUTE, DENY,
                    "%s was downloaded from %s and is executed by %s in the same command"
                    % (argument, downloaded[resolved], command.name),
                    downloaded[resolved],
                )]
    return []


def _first_url(command) -> str | None:
    for arg in command.args:
        if arg.startswith(("http://", "https://", "ftp://")):
            return arg
    return None


def check_upload(command, workspace, context) -> list[Finding]:
    """A single command that both reads a credential and sends it somewhere."""
    if command.name not in NETWORK_FETCHERS and command.name not in (
        "scp", "rsync", "nc", "ncat", "socat",
    ):
        return []
    joined = _joined(command)
    if CREDENTIAL_PATHS.search(joined):
        return [Finding(
            CRED_EXFILTRATION, DENY,
            "%s transmits credential material" % command.name,
        )]
    if command.name in NETWORK_FETCHERS:
        for arg in command.args:
            if arg.startswith("@") and CREDENTIAL_PATHS.search(arg):
                return [Finding(
                    CRED_EXFILTRATION, DENY,
                    "%s uploads the contents of %s" % (command.name, arg.lstrip("@")),
                )]
        if SECRET_ENV_NAMES.search(joined) and _has_flag(command, "-d", "--data", "-F"):
            return [Finding(
                CRED_EXFILTRATION, DENY,
                "%s sends a secret-shaped value in a request body" % command.name,
            )]
    return []


# Raw-text signatures used only when the parser could not decompose the input.
# They are deliberately crude: this path exists so an unparseable command is
# never silently allowed, not to be the primary detector.
FALLBACK_SIGNATURES = (
    re.compile(r"""\brm\s+(?:-[a-zA-Z-]*[rR][a-zA-Z-]*\s+)+['"]?(?:/|~|\$HOME)"""),
    re.compile(r"\bmkfs(?:\.\w+)?\b"),
    re.compile(r"\bdd\b[^\n]*\bof=/dev/"),
    re.compile(r"\bDROP\s+(?:DATABASE|SCHEMA|TABLE)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bterraform\s+destroy\b"),
    re.compile(r"\bkubectl\s+delete\b"),
    re.compile(r"(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"),
    re.compile(r"\bgit\s+push\b[^\n]*(?:--force|-f)\b"),
    re.compile(r"\baws\s+\w+\s+(?:delete|terminate)-"),
    re.compile(r"\bdocker\s+(?:system|volume)\s+prune\b"),
)


def fallback_scan(text: str) -> Finding | None:
    """Crude signature scan for text the parser could not decompose."""
    for pattern in FALLBACK_SIGNATURES:
        match = pattern.search(text)
        if match:
            return Finding(
                PARSE_UNRESOLVED_HIGH_RISK, DENY,
                "the command could not be parsed and its text matches %r"
                % match.group(0)[:60],
            )
    return None
