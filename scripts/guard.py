#!/usr/bin/env python3
"""Execution Guard — the decision the runtime makes just before an action runs.

Agent Skills already says what an agent should not do. Every `SKILL.md` in this
repository inherits `docs/destructive-action-safety.md`, and that policy is the
semantic contract. This is the other half:

    skill policy  ->  agent reasoning  ->  generated action
                                                |
                                          EXECUTION GUARD
                                                |
                                     allow  /   ask   \\  deny
                                                |
                                          tool / runtime

The distinction the whole design rests on: **prompt-level safety works on
cooperative reasoning; Execution Guard works on actions.** A policy holds only
while the agent is reasoning correctly. This holds when it is not — when the
model made a mistake, when a hostile README talked it into something, when a
tool response carried steering text. Even if that succeeds at the reasoning
layer, the resulting command still has to cross this gate.

Three properties are load-bearing:

  * **Deterministic.** No model is consulted for a blocking decision. Sending
    `rm -rf /` to a language model and asking whether it looks dangerous makes
    the answer probabilistic exactly where it must not be, and puts a network
    call in front of every shell command.
  * **Structural.** The full compound command is decomposed, so
    `true && rm -rf /`, `$(rm -rf /)`, and `bash -c 'rm -rf /'` are all seen.
    See `guard_parse.py`.
  * **Never silently permissive.** A command that cannot be decomposed does not
    become ALLOW by default. See `resolve` below.

Subcommands:
  check-command   Classify one shell command.
  check-tool      Host-hook entry point: host JSON in, host decision out.
  explain         Full reasoning for one command, for a human.
  scan-content    Flag instruction-shaped or credential-shaped untrusted text.
  doctor          Per-host enforcement status.
  install         Register the pre-execution hook with hook-capable hosts.
  verify          Check those registrations without writing.
  uninstall       Remove only Agent Skills-owned entries.
  audit           Read the local, redacted decision log.
  rules           Print the rule catalogue.
  run             Wrapper mode for hosts with no pre-execution hook.

Exit codes: 0 allow, 10 ask, 20 deny, 2 usage/setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard_audit as ga  # noqa: E402
import guard_hosts as gh  # noqa: E402
import guard_paths as gp  # noqa: E402
import guard_policy as gpol  # noqa: E402
import guard_parse as gparse  # noqa: E402
import guard_rules as gr  # noqa: E402

EXIT_ALLOW = 0
EXIT_ASK = 10
EXIT_DENY = 20
EXIT_USAGE = 2

ALLOW = gr.ALLOW
ASK = gr.ASK
DENY = gr.DENY


def guard_version() -> str:
    for candidate in (
        Path(__file__).resolve().parent.parent / "VERSION",
        Path(os.environ.get("AGENT_SKILLS_HOME", "~/.agent-skills")).expanduser() / "VERSION",
    ):
        try:
            return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "unknown"


def config_dir() -> str:
    explicit = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
    if explicit:
        return explicit
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "agent-skills")
    return os.path.join(os.path.expanduser("~"), ".config", "agent-skills")


# ---------------------------------------------------------------------------
# The action abstraction
#
# Shell is the first implementation, not the model. A pre-execution hook that
# can only reason about strings has no way to gate a database MCP write or a
# structured filesystem delete, and those exist today. Everything below is
# expressed over Action so a new kind is a new classifier, not a new engine.
# ---------------------------------------------------------------------------
SHELL = "shell"
FILESYSTEM = "filesystem"
MCP = "mcp"
STRUCTURED_TOOL = "structured-tool"


@dataclass
class Action:
    kind: str
    operation: str
    arguments: dict = field(default_factory=dict)
    cwd: str = ""
    raw: str = ""
    host: str = "cli"

    @property
    def display(self) -> str:
        return self.raw or self.operation


@dataclass
class Decision:
    outcome: str
    rule: str
    category: str
    reason: str
    target: str | None = None
    alternative: str | None = None
    findings: list[gr.Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fingerprint: str = ""
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "decision": self.outcome,
            "rule": self.rule,
            "category": self.category,
            "reason": self.reason,
            "target": self.target,
            "alternative": self.alternative,
            "notes": self.notes,
            "fingerprint": self.fingerprint,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "findings": [
                {
                    "rule": finding.rule.identifier,
                    "outcome": finding.outcome,
                    "category": finding.rule.category,
                    "floor": finding.rule.floor,
                    "reason": ga.redact(finding.reason),
                    "target": ga.redact(finding.target) if finding.target else None,
                }
                for finding in self.findings
            ],
        }


ALLOWED_DECISION = Decision(
    outcome=ALLOW,
    rule="NONE",
    category="none",
    reason="no rule matched",
)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def _apply_policy(findings: list[gr.Finding], policy: gpol.Policy) -> list[gr.Finding]:
    """Re-resolve each finding's outcome through the merged policy."""
    resolved: list[gr.Finding] = []
    for finding in findings:
        outcome = policy.outcome_for(finding.rule)
        resolved.append(
            gr.Finding(
                rule=finding.rule,
                outcome=outcome,
                reason=finding.reason,
                target=finding.target,
                detail=finding.detail,
            )
        )
    return resolved


def _pattern_findings(text: str, policy: gpol.Policy) -> list[gr.Finding]:
    out: list[gr.Finding] = []
    for pattern, source in policy.deny_patterns:
        if re.search(pattern, text):
            out.append(gr.Finding(
                gr.POLICY_CUSTOM_DENY, DENY,
                "matches the deny pattern %r from %s" % (pattern, source),
            ))
    for pattern, source in policy.ask_patterns:
        if re.search(pattern, text):
            out.append(gr.Finding(
                gr.POLICY_CUSTOM_ASK, ASK,
                "matches the ask pattern %r from %s" % (pattern, source),
            ))
    return out


def _context_for(workspace: gp.Workspace) -> dict:
    context: dict = {}
    branch = os.environ.get("AGENT_SKILLS_GUARD_BRANCH")
    if not branch:
        head = Path(workspace.root) / ".git" / "HEAD"
        try:
            text = head.read_text(encoding="utf-8").strip()
            if text.startswith("ref: refs/heads/"):
                branch = text.split("refs/heads/", 1)[1]
        except OSError:
            branch = ""
    context["branch"] = branch or ""
    context["environment"] = os.environ.get("AGENT_SKILLS_GUARD_ENVIRONMENT", "")
    context["kube_context"] = os.environ.get("AGENT_SKILLS_GUARD_KUBE_CONTEXT", "")
    return context


def evaluate_shell(
    command: str, workspace: gp.Workspace, policy: gpol.Policy
) -> tuple[list[gr.Finding], list[str]]:
    parsed = gparse.parse(command)
    context = _context_for(workspace)
    findings: list[gr.Finding] = []

    context["extra_protected_branches"] = list(policy.protected_branches)

    for pipeline in parsed.pipelines:
        findings.extend(gr.check_pipeline(pipeline, workspace, context))
        for simple in pipeline.commands:
            for check in gr.SINGLE_COMMAND_CHECKS:
                findings.extend(check(simple, workspace, context))
            findings.extend(gr.check_upload(simple, workspace, context))

    if parsed.unparsed:
        # An unparseable command must never resolve to ALLOW by omission. The
        # crude signature scan can escalate it to DENY; otherwise it is an ASK,
        # which is visible, rather than a silent pass.
        fallback = gr.fallback_scan(command)
        if fallback is not None:
            findings.append(fallback)
        else:
            findings.append(gr.Finding(
                gr.PARSE_UNRESOLVED, ASK,
                "; ".join(parsed.notes) or "the command could not be decomposed",
            ))

    findings.extend(_pattern_findings(command, policy))
    return _apply_policy(findings, policy), parsed.notes


def evaluate_filesystem(
    action: Action, workspace: gp.Workspace, policy: gpol.Policy
) -> list[gr.Finding]:
    """Structured file writes and deletes, as hosts expose them directly."""
    findings: list[gr.Finding] = []
    path = (
        action.arguments.get("file_path")
        or action.arguments.get("path")
        or action.arguments.get("notebook_path")
        or ""
    )
    if not path:
        return findings
    target = gp.classify(str(path), workspace)
    deleting = action.operation.lower() in ("delete", "remove", "rm", "unlink")
    if target.classification == gp.SYSTEM_ROOT:
        findings.append(gr.Finding(
            gr.FS_SYSTEM_WRITE, DENY,
            "%s targets the system path %s" % (action.operation, target.resolved),
            target.display,
        ))
    elif target.classification == gp.HOME_ROOT:
        findings.append(gr.Finding(
            gr.FS_SYSTEM_WRITE, DENY,
            "%s targets %s, a home or credential path"
            % (action.operation, target.resolved),
            target.display,
        ))
    elif target.escaped_via_symlink:
        findings.append(gr.Finding(
            gr.FS_SYMLINK_ESCAPE, DENY,
            "%s is inside the repository by name but resolves to %s"
            % (path, target.resolved),
            target.display,
        ))
    elif target.classification == gp.OUTSIDE_WORKSPACE:
        rule = gr.FS_OUTSIDE_WORKSPACE_DELETE if deleting else gr.FS_WORKSPACE_RECURSIVE_DELETE
        findings.append(gr.Finding(
            rule, DENY if deleting else ASK,
            "%s targets %s, outside the working repository"
            % (action.operation, target.resolved),
            target.display,
        ))
    return _apply_policy(findings, policy)


# Structured-tool names whose verb is destructive whatever the server is.
_TOOL_DESTRUCTIVE = re.compile(
    r"(?:^|[_.\-/])(?:delete|destroy|drop|truncate|terminate|purge|remove|revoke|"
    r"wipe|erase|force[_-]?push|prune)(?:$|[_.\-/])",
    re.IGNORECASE,
)
_TOOL_MUTATING = re.compile(
    r"(?:^|[_.\-/])(?:create|update|write|put|patch|set|apply|insert|upsert|merge|"
    r"push|deploy|publish|send|invoke|execute|run)(?:$|[_.\-/])",
    re.IGNORECASE,
)
_TOOL_HIGH_VALUE = re.compile(
    r"(?:secret|credential|iam|role|policy|key|token|backup|snapshot|audit|"
    r"cloudtrail|billing|production)",
    re.IGNORECASE,
)
# Domains where an ordinary-looking mutation is worth a question. Without this
# every MCP write becomes an ASK — creating an issue, posting a message, saving
# a note — and a guard that asks about all of them is a guard that gets turned
# off. The host's own tool-approval prompt already covers routine MCP calls;
# this layer exists for the mutations that are hard to undo.
_TOOL_HIGH_RISK_DOMAIN = re.compile(
    r"(?:postgres|mysql|mariadb|mongo|redis|sqlite|sql|database|\bdb\b|"
    r"s3|aws|gcp|gcloud|azure|cloud|kubernetes|k8s|kubectl|helm|terraform|"
    r"pulumi|infra|deploy|cluster|prod)",
    re.IGNORECASE,
)
_SHELL_ARGUMENT_NAMES = ("command", "cmd", "script", "shell", "bash", "sh", "exec")
_SQL_ARGUMENT_NAMES = ("sql", "query", "statement", "q")


def evaluate_structured(
    action: Action, workspace: gp.Workspace, policy: gpol.Policy
) -> list[gr.Finding]:
    """Gate MCP and other structured tools with the same rule catalogue.

    A structured tool is not automatically safer than a shell command; a
    database MCP with a `query` argument can drop a table without a shell ever
    being involved. Three things are inspected: an embedded shell string, an
    embedded SQL statement, and the tool's own verb.
    """
    findings: list[gr.Finding] = []
    arguments = action.arguments if isinstance(action.arguments, dict) else {}

    for key, value in arguments.items():
        if not isinstance(value, str):
            continue
        lowered = key.lower()
        if lowered in _SHELL_ARGUMENT_NAMES:
            nested, _ = evaluate_shell(value, workspace, policy)
            findings.extend(nested)
        elif lowered in _SQL_ARGUMENT_NAMES:
            findings.extend(gr.sql_findings(value, "%s argument %r" % (action.operation, key)))

    name = action.operation
    if _TOOL_DESTRUCTIVE.search(name):
        if _TOOL_HIGH_VALUE.search(name) or _TOOL_HIGH_VALUE.search(json.dumps(arguments)[:4000]):
            findings.append(gr.Finding(
                gr.CLOUD_IAM_DESTRUCTIVE, DENY,
                "tool %s performs a destructive operation on high-value state" % name,
                name,
            ))
        else:
            findings.append(gr.Finding(
                gr.CLOUD_DESTRUCTIVE, DENY,
                "tool %s performs a destructive operation" % name,
                name,
            ))
    elif _TOOL_MUTATING.search(name) and _TOOL_HIGH_VALUE.search(name):
        findings.append(gr.Finding(
            gr.CLOUD_IAM_DESTRUCTIVE, DENY,
            "tool %s mutates identity or secret material" % name,
            name,
        ))
    elif _TOOL_MUTATING.search(name) and _TOOL_HIGH_RISK_DOMAIN.search(name):
        findings.append(gr.Finding(
            gr.CLOUD_MUTATE, ASK,
            "tool %s mutates state in a hard-to-undo domain" % name, name,
        ))

    findings.extend(_pattern_findings("%s %s" % (name, json.dumps(arguments)[:4000]), policy))
    return _apply_policy(findings, policy)


def resolve(
    action: Action, policy: gpol.Policy | None = None, workspace: gp.Workspace | None = None
) -> Decision:
    """The one entry point every host adapter calls."""
    started = time.perf_counter()
    workspace = workspace or gp.resolve_workspace(action.cwd or None)
    policy = policy or gpol.load(config_dir(), workspace.root)

    notes: list[str] = []
    if action.kind == SHELL:
        findings, parse_notes = evaluate_shell(action.raw, workspace, policy)
        notes.extend(parse_notes)
    elif action.kind == FILESYSTEM:
        findings = evaluate_filesystem(action, workspace, policy)
    else:
        findings = evaluate_structured(action, workspace, policy)

    # A refused weakening attempt is always reported as a note, and is raised to
    # a finding only when it targeted a rule this action actually triggered.
    # Attaching it to every decision instead would turn one bad key in one
    # configuration file into an ASK on every command in the session, which is
    # how a guard gets switched off.
    triggered = {finding.rule.identifier for finding in findings}
    for attempt in policy.weakening_attempts:
        notes.append(attempt)
        if any(identifier in attempt for identifier in triggered):
            findings.append(gr.Finding(
                gr.POLICY_REPOSITORY_OVERRIDE,
                policy.outcome_for(gr.POLICY_REPOSITORY_OVERRIDE),
                attempt,
            ))
    notes.extend(policy.errors)

    decision = _reduce(findings, action, notes)
    decision.elapsed_ms = (time.perf_counter() - started) * 1000.0

    # An allow-list may lower a non-floor result. It can never lower a floor
    # one, which is checked here rather than trusted to the policy loader.
    if policy.allow_commands and decision.outcome != ALLOW:
        floor_hit = any(f.rule.floor and f.outcome == DENY for f in findings)
        if not floor_hit and _matches_allow_list(action, policy.allow_commands):
            decision = Decision(
                outcome=ALLOW,
                rule="POLICY_ALLOW_LIST",
                category="policy",
                reason="matched a machine-scope allow list entry",
                findings=findings,
                notes=notes,
                fingerprint=decision.fingerprint,
                elapsed_ms=decision.elapsed_ms,
            )
    return decision


def _matches_allow_list(action: Action, entries: list[str]) -> bool:
    text = action.display.strip()
    for entry in entries:
        if text == entry or text.startswith(entry.rstrip() + " "):
            return True
    return False


def _reduce(findings: list[gr.Finding], action: Action, notes: list[str]) -> Decision:
    if not findings:
        return Decision(
            outcome=ALLOW,
            rule="NONE",
            category="none",
            reason="no rule matched",
            findings=[],
            notes=notes,
            fingerprint=ga.fingerprint(action.display),
        )
    order = {ALLOW: 0, ASK: 1, DENY: 2}
    # Worst outcome wins; among equals, a hard-floor rule is the one to report.
    ranked = sorted(
        findings,
        key=lambda f: (order.get(f.outcome, 0), 1 if f.rule.floor else 0),
        reverse=True,
    )
    top = ranked[0]
    return Decision(
        outcome=top.outcome,
        rule=top.rule.identifier,
        category=top.rule.category,
        reason="%s: %s" % (top.rule.summary, ga.redact(top.reason)),
        target=ga.redact(top.target) if top.target else None,
        alternative=top.rule.alternative,
        findings=ranked,
        notes=notes,
        fingerprint=ga.fingerprint(action.display),
    )


def log_decision(action: Action, decision: Decision, policy: gpol.Policy) -> None:
    ga.record(
        config_dir(),
        {
            "host": action.host,
            "kind": action.kind,
            "decision": decision.outcome,
            "rule": decision.rule,
            "category": decision.category,
            "cwd": action.cwd,
            "target": decision.target,
            "fingerprint": decision.fingerprint,
            "guard_version": guard_version(),
        },
        mode=policy.audit,
    )


def exit_code_for(outcome: str) -> int:
    return {ALLOW: EXIT_ALLOW, ASK: EXIT_ASK, DENY: EXIT_DENY}.get(outcome, EXIT_ASK)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_text(action: Action, decision: Decision, verbose: bool = False) -> str:
    lines = [decision.outcome]
    lines.append("  rule       : %s" % decision.rule)
    lines.append("  category   : %s" % decision.category)
    lines.append("  reason     : %s" % decision.reason)
    if decision.target:
        lines.append("  target     : %s" % decision.target)
    if decision.outcome != ALLOW and decision.alternative:
        lines.append("  instead    : %s" % decision.alternative)
    if verbose:
        lines.append("  command    : %s" % ga.redact(action.display))
        lines.append("  cwd        : %s" % action.cwd)
        lines.append("  fingerprint: %s" % decision.fingerprint)
        lines.append("  elapsed    : %.2f ms" % decision.elapsed_ms)
        if len(decision.findings) > 1:
            lines.append("  all findings:")
            for finding in decision.findings:
                lines.append(
                    "    %-5s %-32s %s"
                    % (finding.outcome, finding.rule.identifier, ga.redact(finding.reason))
                )
        for note in decision.notes:
            lines.append("  note       : %s" % note)
    return "\n".join(lines)


def hook_message(decision: Decision) -> str:
    """The sentence a host shows the user and the agent when it blocks."""
    parts = ["Execution Guard: %s (%s)." % (decision.outcome, decision.rule)]
    parts.append(decision.reason)
    if decision.alternative:
        parts.append("Safe alternative: %s" % decision.alternative)
    parts.append("Explain with: agent-skills guard explain -- '<command>'")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Host dialects
#
# One engine, several dialects. Every adapter below converts the host's own
# request shape into an Action, calls `resolve`, and converts the Decision back
# into the host's own response shape. No adapter contains a rule.
# ---------------------------------------------------------------------------
def _read_stdin_json(explicit: str | None) -> dict:
    if explicit and explicit != "-":
        raw = Path(explicit).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


class PayloadShapeError(Exception):
    """The hook payload did not contain the fields this dialect expects.

    Raised rather than returning an empty Action. An empty Action matches no
    rule and therefore reads as ALLOW, which would turn any future change to a
    host's payload schema into a silent, total bypass — the guard would keep
    answering "allow" to every command and look healthy doing it.
    """


SHELL_TOOL_NAMES = (
    "Bash", "BashOutput", "Shell", "shell", "run_terminal_cmd", "local_shell",
    "execute_command", "terminal",
)


def _action_from_claude_shape(payload: dict, host: str) -> Action:
    tool_name = str(payload.get("tool_name", "") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    cwd = str(payload.get("cwd") or os.getcwd())
    if not tool_name:
        raise PayloadShapeError("the payload carries no tool_name")
    if tool_name in SHELL_TOOL_NAMES:
        if "command" not in tool_input:
            raise PayloadShapeError(
                "%s payload carries no 'command' field; the host's schema may have "
                "changed" % tool_name
            )
        return Action(
            kind=SHELL,
            operation="bash",
            arguments=tool_input,
            cwd=cwd,
            raw=str(tool_input.get("command", "")),
            host=host,
        )
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "create_file"):
        return Action(
            kind=FILESYSTEM,
            operation=tool_name,
            arguments=tool_input,
            cwd=cwd,
            raw="%s %s" % (tool_name, tool_input.get("file_path", "")),
            host=host,
        )
    kind = MCP if tool_name.startswith("mcp__") or "/" in tool_name else STRUCTURED_TOOL
    return Action(
        kind=kind,
        operation=tool_name,
        arguments=tool_input,
        cwd=cwd,
        raw="%s %s" % (tool_name, json.dumps(tool_input)[:400]),
        host=host,
    )


def _action_from_cursor_shape(payload: dict) -> Action:
    cwd = str(payload.get("cwd") or payload.get("workspace_roots", [os.getcwd()])[0]
              if payload.get("workspace_roots") else payload.get("cwd") or os.getcwd())
    if "command" in payload and payload.get("command"):
        return Action(
            kind=SHELL,
            operation="shell",
            arguments={"command": payload.get("command")},
            cwd=str(cwd),
            raw=str(payload.get("command")),
            host="cursor",
        )
    tool_name = str(payload.get("tool_name", "") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    if not tool_name:
        raise PayloadShapeError(
            "the payload carries neither a 'command' nor a 'tool_name' field"
        )
    server = str(payload.get("mcp_server_name", "") or "")
    qualified = "%s/%s" % (server, tool_name) if server else tool_name
    return Action(
        kind=MCP,
        operation=qualified,
        arguments=tool_input,
        cwd=str(cwd),
        raw="%s %s" % (qualified, json.dumps(tool_input)[:400]),
        host="cursor",
    )


def _ask_fallback() -> str:
    """What ASK becomes on a host whose hook contract has only allow and block."""
    value = os.environ.get("AGENT_SKILLS_GUARD_ASK_FALLBACK", "warn").lower()
    return "deny" if value == "deny" else "warn"


def _on_error() -> str:
    value = os.environ.get("AGENT_SKILLS_GUARD_ON_ERROR", "ask").lower()
    return "deny" if value == "deny" else "ask"


def emit_claude_shape(decision: Decision, host: str) -> int:
    mapping = {ALLOW: "allow", ASK: "ask", DENY: "deny"}
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": mapping[decision.outcome],
            "permissionDecisionReason": hook_message(decision),
        }
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    if decision.outcome == DENY:
        # Belt and braces. The JSON above is the contract; exit 2 blocks the
        # call even if the JSON is ever rejected by a schema change, and the
        # documented precedence is that exit 2 cannot be overridden.
        sys.stderr.write(hook_message(decision) + "\n")
        return 2
    return 0


def emit_cursor_shape(decision: Decision, host: str = "cursor") -> int:
    mapping = {ALLOW: "allow", ASK: "ask", DENY: "deny"}
    message = hook_message(decision)
    payload = {
        "continue": True,
        "permission": mapping[decision.outcome],
        # Both spellings are emitted deliberately: the published examples differ
        # between snake_case and camelCase, and an unknown extra key is ignored
        # while a missing expected key silently loses the explanation.
        "user_message": message,
        "agent_message": message,
        "userMessage": message,
        "agentMessage": message,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


def emit_exit_code_shape(decision: Decision, host: str = "kiro") -> int:
    """For hosts whose only contract is the exit code (Kiro command actions)."""
    message = hook_message(decision)
    if decision.outcome == DENY:
        sys.stderr.write(message + "\n")
        return 2
    if decision.outcome == ASK:
        if _ask_fallback() == "deny":
            sys.stderr.write(message + "\n")
            return 2
        # This host has no "ask". Surfacing the reason into the agent's context
        # is weaker than blocking and is reported as such by `guard doctor`.
        sys.stdout.write(message + "\n")
        return 0
    return 0


def emit_generic_shape(decision: Decision, host: str = "generic") -> int:
    """The guard's own schema, for a host with no published hook contract."""
    sys.stdout.write(json.dumps(decision.as_dict(), indent=2) + "\n")
    return exit_code_for(decision.outcome)


# host id -> (request shape, response emitter). The emitter takes the decision
# and the host id, so one table drives every dialect with no branching at the
# call site.
HOST_DIALECTS = {
    "claude-code": ("claude", emit_claude_shape),
    "codex": ("claude", emit_claude_shape),
    "cursor": ("cursor", emit_cursor_shape),
    "kiro": ("claude", emit_exit_code_shape),
    "generic": ("claude", emit_generic_shape),
}


# ---------------------------------------------------------------------------
# Content scanner
#
# This is evidence, not a verdict. Regex cannot decide whether a paragraph is an
# attack, and claiming otherwise would be the same overreach the repository
# already refuses elsewhere. What it can do is say "this untrusted file contains
# text shaped like an instruction to an agent", which is a thing a reviewer
# should look at.
# ---------------------------------------------------------------------------
CONTENT_SIGNALS = (
    (
        "SUSPICIOUS_INSTRUCTION_SHAPED_CONTENT",
        (
            re.compile(r"\bignore (?:all |any )?(?:previous|prior|above)\b", re.I),
            re.compile(r"\bdisregard\b.*\b(?:instruction|rule|guardrail|policy)", re.I),
            re.compile(r"\byou are (?:now|actually)\b", re.I),
            re.compile(r"\bsystem prompt\b", re.I),
            re.compile(r"\bnew instructions?\b\s*[:\-]", re.I),
            re.compile(r"\bas an ai\b.*\byou must\b", re.I),
        ),
    ),
    (
        "SUSPICIOUS_POLICY_WAIVER_LANGUAGE",
        (
            re.compile(r"\b(?:skip|bypass|disable|turn off)\b.*"
                       r"\b(?:review|validation|check|guard|safety|approval|gate)", re.I),
            re.compile(r"\bwithout (?:asking|confirming|approval|permission)\b", re.I),
            re.compile(r"\bdo not (?:tell|inform|surface|report|log)\b", re.I),
            re.compile(r"\byou (?:have|are given) (?:full |explicit )?permission\b", re.I),
            re.compile(r"\bthis is (?:pre-?)?authoris?zed\b", re.I),
        ),
    ),
    (
        "SUSPICIOUS_DOWNLOAD_AND_EXECUTE_INSTRUCTION",
        (
            re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", re.I),
            re.compile(r"\bbase64\s+(?:-d|--decode)\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
            re.compile(r"\bpython3?\s+-c\b[^\n]*urlopen", re.I),
        ),
    ),
    (
        "SUSPICIOUS_CREDENTIAL_SHAPED_CONTENT",
        (
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
            re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
            re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*\S{16,}"),
        ),
    ),
    (
        "SUSPICIOUS_DESTRUCTIVE_COMMAND_IN_TEXT",
        (
            re.compile(r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(?:/|~|\$HOME)"),
            re.compile(r"\bDROP\s+(?:DATABASE|TABLE|SCHEMA)\b", re.I),
            re.compile(r"\bterraform\s+destroy\b", re.I),
        ),
    ),
)

SCAN_MAX_BYTES = 2_000_000


def scan_content(path: Path) -> list[dict]:
    """Classify one untrusted file. Reads only; never executes anything."""
    findings: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(SCAN_MAX_BYTES)
    except OSError as exc:
        return [{
            "path": str(path),
            "line": 0,
            "signal": "UNREADABLE",
            "evidence": str(exc),
        }]
    for number, line in enumerate(text.splitlines(), start=1):
        # Every matching signal is reported, not just the first. One sentence
        # can be a policy waiver *and* a destructive command, and stopping at
        # the first match hides the more concrete of the two.
        for signal, patterns in CONTENT_SIGNALS:
            if any(pattern.search(line) for pattern in patterns):
                findings.append({
                    "path": str(path),
                    "line": number,
                    "signal": signal,
                    # The evidence is redacted and truncated: a scanner that
                    # prints the secret it found has moved the leak, not fixed it.
                    "evidence": ga.redact(line.strip())[:200],
                })
    return findings


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_check_command(args: argparse.Namespace) -> int:
    command = " ".join(args.command).strip()
    if not command:
        sys.stderr.write("guard: no command supplied\n")
        return EXIT_USAGE
    cwd = args.cwd or os.getcwd()
    workspace = gp.resolve_workspace(cwd)
    policy = gpol.load(config_dir(), workspace.root)
    action = Action(kind=SHELL, operation="bash", cwd=cwd, raw=command, host=args.host)
    decision = resolve(action, policy, workspace)
    log_decision(action, decision, policy)
    if args.format == "json":
        payload = decision.as_dict()
        payload["command"] = ga.redact(command)
        payload["cwd"] = cwd
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(action, decision, verbose=args.verbose) + "\n")
    return exit_code_for(decision.outcome)


def cmd_explain(args: argparse.Namespace) -> int:
    args.format = "text"
    args.verbose = True
    return cmd_check_command(args)


def cmd_check_tool(args: argparse.Namespace) -> int:
    host = args.host
    dialect = HOST_DIALECTS.get(host)
    if dialect is None:
        sys.stderr.write(
            "guard: unknown host %r; expected one of %s\n"
            % (host, ", ".join(sorted(HOST_DIALECTS)))
        )
        return EXIT_USAGE
    shape, emitter = dialect

    try:
        payload = _read_stdin_json(args.input_json)
    except (OSError, json.JSONDecodeError) as exc:
        return _fail_closed(host, emitter, "guard could not read the hook payload: %s" % exc)

    try:
        if shape == "cursor":
            action = _action_from_cursor_shape(payload)
        else:
            action = _action_from_claude_shape(payload, host)
        if args.cwd:
            action.cwd = args.cwd
        workspace = gp.resolve_workspace(action.cwd or None)
        policy = gpol.load(config_dir(), workspace.root)
        decision = resolve(action, policy, workspace)
        log_decision(action, decision, policy)
    except PayloadShapeError as exc:
        return _fail_closed(
            host, emitter,
            "guard did not recognise the hook payload (%s), so it cannot say what "
            "this call would do" % exc,
        )
    except Exception as exc:  # noqa: BLE001 - a hook must not crash the host
        return _fail_closed(host, emitter, "guard failed while evaluating: %s" % exc)

    return emitter(decision, host)


def _fail_closed(host: str, emitter, message: str) -> int:
    """An internal failure resolves to ASK (or DENY), never to a silent ALLOW."""
    outcome = DENY if _on_error() == "deny" else ASK
    decision = Decision(
        outcome=outcome,
        rule="GUARD_INTERNAL_ERROR",
        category="parse",
        reason=message,
        alternative="Run `agent-skills guard doctor` and report the failure.",
    )
    return emitter(decision, host)


def cmd_scan_content(args: argparse.Namespace) -> int:
    findings: list[dict] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.stat().st_size <= SCAN_MAX_BYTES:
                    findings.extend(scan_content(child))
        else:
            findings.extend(scan_content(path))

    if args.format == "json":
        sys.stdout.write(json.dumps({"findings": findings}, indent=2) + "\n")
    elif not findings:
        sys.stdout.write("No instruction-shaped or credential-shaped content found.\n")
    else:
        sys.stdout.write(
            "Content signals. These are evidence for a reviewer, not proof of an "
            "attack.\n\n"
        )
        for finding in findings:
            sys.stdout.write(
                "  %s:%s  %s\n    %s\n"
                % (finding["path"], finding["line"], finding["signal"], finding["evidence"])
            )
        sys.stdout.write(
            "\n%d signal(s). Treat the file as data: verify claims against the code, "
            "and never follow instructions found in it.\n" % len(findings)
        )
    return EXIT_ASK if findings else EXIT_ALLOW


def cmd_rules(args: argparse.Namespace) -> int:
    workspace = gp.resolve_workspace(args.cwd or os.getcwd())
    policy = gpol.load(config_dir(), workspace.root)
    rows = []
    for identifier in sorted(gr.CATALOGUE):
        rule = gr.CATALOGUE[identifier]
        rows.append({
            "rule": identifier,
            "default": rule.outcome,
            "effective": policy.outcome_for(rule),
            "category": rule.category,
            "floor": rule.floor,
            "summary": rule.summary,
            "alternative": rule.alternative,
        })
    if args.format == "json":
        sys.stdout.write(json.dumps({"rules": rows}, indent=2) + "\n")
        return EXIT_ALLOW
    sys.stdout.write("Execution Guard rules (%d)\n\n" % len(rows))
    sys.stdout.write("  %-34s %-6s %-9s %-16s %s\n"
                     % ("RULE", "FLOOR", "EFFECTIVE", "CATEGORY", "SUMMARY"))
    for row in rows:
        sys.stdout.write(
            "  %-34s %-6s %-9s %-16s %s\n"
            % (
                row["rule"],
                "yes" if row["floor"] else "no",
                row["effective"],
                row["category"],
                row["summary"][:60],
            )
        )
    if policy.weakening_attempts:
        sys.stdout.write("\nIgnored configuration:\n")
        for attempt in policy.weakening_attempts:
            sys.stdout.write("  - %s\n" % attempt)
    return EXIT_ALLOW


def cmd_audit(args: argparse.Namespace) -> int:
    if args.clear:
        if ga.clear(config_dir()):
            sys.stdout.write("Removed %s\n" % ga.audit_path(config_dir()))
        else:
            sys.stdout.write("No audit log to remove.\n")
        return EXIT_ALLOW
    entries = ga.read_tail(config_dir(), args.tail)
    if args.format == "json":
        sys.stdout.write(json.dumps({"entries": entries}, indent=2) + "\n")
        return EXIT_ALLOW
    if not entries:
        sys.stdout.write("No decisions recorded at %s\n" % ga.audit_path(config_dir()))
        return EXIT_ALLOW
    sys.stdout.write("%s\n\n" % ga.audit_path(config_dir()))
    for entry in entries:
        sys.stdout.write(
            "  %s  %-5s  %-32s %-10s %s\n"
            % (
                entry.get("at", ""),
                entry.get("decision", ""),
                entry.get("rule", ""),
                entry.get("host", ""),
                entry.get("fingerprint", ""),
            )
        )
    sys.stdout.write(
        "\nCommands are never stored. The fingerprint is a digest of the redacted "
        "form.\nRetention: the last %d records.\n" % ga.MAX_RECORDS
    )
    return EXIT_ALLOW


def cmd_run(args: argparse.Namespace) -> int:
    """Wrapper mode: for hosts with no pre-execution hook at all."""
    command = " ".join(args.command).strip()
    if not command:
        sys.stderr.write("guard: no command supplied\n")
        return EXIT_USAGE
    cwd = args.cwd or os.getcwd()
    workspace = gp.resolve_workspace(cwd)
    policy = gpol.load(config_dir(), workspace.root)
    action = Action(kind=SHELL, operation="bash", cwd=cwd, raw=command, host="wrapper")
    decision = resolve(action, policy, workspace)
    log_decision(action, decision, policy)

    if decision.outcome == DENY:
        sys.stderr.write(render_text(action, decision) + "\n")
        return EXIT_DENY
    if decision.outcome == ASK:
        sys.stderr.write(render_text(action, decision) + "\n")
        if not sys.stdin.isatty():
            sys.stderr.write("guard: no terminal to ask on; refusing.\n")
            return EXIT_ASK
        sys.stderr.write("Run it anyway? [y/N] ")
        sys.stderr.flush()
        reply = sys.stdin.readline().strip().lower()
        if reply not in ("y", "yes"):
            return EXIT_ASK
    os.execvp(os.environ.get("SHELL", "/bin/sh"), [
        os.environ.get("SHELL", "/bin/sh"), "-c", command,
    ])
    return EXIT_USAGE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-skills guard",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    check = sub.add_parser("check-command", help="classify one shell command")
    check.add_argument("--cwd", default=None)
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument("--host", default="cli")
    check.add_argument("--verbose", action="store_true")
    check.add_argument("command", nargs=argparse.REMAINDER)
    check.set_defaults(func=cmd_check_command)

    explain = sub.add_parser("explain", help="full reasoning for one command")
    explain.add_argument("--cwd", default=None)
    explain.add_argument("--host", default="cli")
    explain.add_argument("command", nargs=argparse.REMAINDER)
    explain.set_defaults(func=cmd_explain)

    tool = sub.add_parser("check-tool", help="host pre-execution hook entry point")
    tool.add_argument("--host", required=True)
    tool.add_argument("--input-json", default=None)
    tool.add_argument("--cwd", default=None)
    tool.set_defaults(func=cmd_check_tool)

    scan = sub.add_parser("scan-content", help="flag instruction-shaped untrusted text")
    scan.add_argument("paths", nargs="+")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.set_defaults(func=cmd_scan_content)

    rules = sub.add_parser("rules", help="print the rule catalogue")
    rules.add_argument("--format", choices=("text", "json"), default="text")
    rules.add_argument("--cwd", default=None)
    rules.set_defaults(func=cmd_rules)

    audit = sub.add_parser("audit", help="read the local decision log")
    audit.add_argument("--tail", type=int, default=20)
    audit.add_argument("--format", choices=("text", "json"), default="text")
    audit.add_argument("--clear", action="store_true")
    audit.set_defaults(func=cmd_audit)

    runner = sub.add_parser("run", help="wrapper mode for hosts without hooks")
    runner.add_argument("--cwd", default=None)
    runner.add_argument("command", nargs=argparse.REMAINDER)
    runner.set_defaults(func=cmd_run)

    gh.register_cli(sub)
    return parser


def strip_separator(argv: list[str]) -> list[str]:
    """Drop the leading `--` separating guard options from the command.

    Only the leading one. `git log --` and `rm -- -weird-file` carry their own
    separator, and removing every occurrence would change the command the guard
    inspects into one the shell would not run.
    """
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(raw)
    if hasattr(args, "command") and isinstance(getattr(args, "command", None), list):
        args.command = strip_separator(args.command)
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as error:  # noqa: BLE001 - report, never traceback
        # `check-tool` handles its own failures fail-closed. This is the CLI
        # path, where a traceback and an undocumented exit code help nobody.
        sys.stderr.write("guard: unexpected failure: %s\n" % error)
        sys.exit(EXIT_USAGE)
