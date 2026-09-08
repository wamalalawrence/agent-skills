#!/usr/bin/env python3
"""Configuration trust levels for Execution Guard.

The point of a guard is that the thing it guards against cannot turn it off. A
repository is exactly that thing: the agent reads it, an attacker can open a
pull request against it, and a compromised dependency can write into it. So a
file inside the repository must never be able to say

    guard:
      allow_rm_rf: true

and get it.

Four layers, in decreasing authority:

    1. Agent Skills hard floor   compiled into guard_rules.py, not configurable
    2. organisation policy       outside any repository; may ADD and ESCALATE
    3. machine / user policy     the user's own machine; may ADD, ESCALATE, and
                                 RELAX a non-floor rule down to the org level
    4. repository policy         committed or repo-local; may ADD and ESCALATE
                                 ONLY

Escalation is always allowed from every layer, because tightening cannot be an
attack. Relaxation is the privileged direction and is available in exactly one
place: the user's own machine-scope file, and never below the floor or below
what the organisation set.

A repository layer that tries to relax anything is not an error that stops the
run — that would let a hostile file deny service. It is *ignored and reported*:
the attempt is recorded in `weakening_attempts`, surfaced by `guard doctor` and
`guard verify`, and attached to every decision made under that configuration.

This mirrors the rule the access resolver already enforces for credentials: a
committed file may describe what a service is, but may never choose which
identity unlocks it. See docs/access-resolution.md.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import guard_rules as gr

SCHEMA = "agent-skills.guard-policy/v1"

FLOOR = "floor"
ORG = "organisation"
USER = "user"
REPO = "repository"

# Which layers may lower an outcome. The whole trust model is this one set.
RELAXING_LAYERS = {USER}

_ORDER = {gr.ALLOW: 0, gr.ASK: 1, gr.DENY: 2}
_VALID_OUTCOMES = {"allow": gr.ALLOW, "ask": gr.ASK, "deny": gr.DENY}


@dataclass
class Layer:
    """One configuration file that was read, and where it came from."""

    scope: str
    path: str
    rules: dict[str, str] = field(default_factory=dict)
    deny_patterns: list[str] = field(default_factory=list)
    ask_patterns: list[str] = field(default_factory=list)
    allow_commands: list[str] = field(default_factory=list)
    protected_branches: list[str] = field(default_factory=list)
    audit: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class Policy:
    """The merged, trust-resolved policy the engine evaluates against."""

    outcomes: dict[str, str] = field(default_factory=dict)
    deny_patterns: list[tuple[str, str]] = field(default_factory=list)
    ask_patterns: list[tuple[str, str]] = field(default_factory=list)
    allow_commands: list[str] = field(default_factory=list)
    protected_branches: list[str] = field(default_factory=list)
    audit: str = "decisions"
    layers: list[Layer] = field(default_factory=list)
    weakening_attempts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def outcome_for(self, rule: gr.Rule) -> str:
        return self.outcomes.get(rule.identifier, rule.outcome)

    def is_floor(self, rule: gr.Rule) -> bool:
        return rule.floor


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _coerce_outcome(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _VALID_OUTCOMES.get(value.strip().lower())


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _layer_from_mapping(scope: str, path: str, data: dict) -> Layer:
    layer = Layer(scope=scope, path=path)
    rules = data.get("rules")
    if isinstance(rules, dict):
        for key, value in rules.items():
            outcome = _coerce_outcome(value)
            if outcome is None:
                layer.errors.append("rules.%s: %r is not allow/ask/deny" % (key, value))
                continue
            if key not in gr.CATALOGUE:
                layer.errors.append("rules.%s: no such rule" % key)
                continue
            layer.rules[key] = outcome
    layer.deny_patterns = _string_list(data.get("deny_patterns"))
    layer.ask_patterns = _string_list(data.get("ask_patterns"))
    layer.allow_commands = _string_list(data.get("allow_commands"))
    layer.protected_branches = _string_list(data.get("protected_branches"))
    audit = data.get("audit")
    if isinstance(audit, str) and audit in ("decisions", "all", "off"):
        layer.audit = audit
    elif audit is not None:
        layer.errors.append("audit: %r is not decisions/all/off" % audit)

    # Any key that reads like a capability grant is refused by name, so a file
    # that invents `allow_rm_rf: true` gets an explicit answer rather than
    # silence. Silence looks like acceptance to whoever wrote it.
    for key, value in data.items():
        if key in ("schema", "rules", "deny_patterns", "ask_patterns", "allow_commands",
                   "protected_branches", "audit"):
            continue
        layer.errors.append("unknown key %r ignored" % key)
        if re.match(r"^(?:allow|enable|disable|skip|bypass|permit)_", str(key)):
            layer.errors.append(
                "%r is not a supported knob; capabilities are not grantable from "
                "configuration" % key
            )
    return layer


def _read_json_layer(scope: str, path: Path) -> Layer | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        layer = Layer(scope=scope, path=str(path))
        layer.errors.append("could not be read: %s" % exc)
        return layer
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        layer = Layer(scope=scope, path=str(path))
        layer.errors.append("is not valid JSON: %s" % exc)
        return layer
    if not isinstance(data, dict):
        layer = Layer(scope=scope, path=str(path))
        layer.errors.append("top level is not an object")
        return layer
    return _layer_from_mapping(scope, str(path), data)


# A deliberately small YAML reader for one shape: a top-level `guard:` block
# with scalar values, string lists, and a one-level `rules:` mapping. Anything
# richer is not supported, and saying so is better than half-parsing it.
def _read_yaml_guard_block(path: Path) -> dict | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    block: list[str] = []
    inside = False
    for line in lines:
        if not inside:
            if re.match(r"^guard\s*:\s*$", line):
                inside = True
            continue
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
    if not inside:
        return None

    data: dict[str, object] = {}
    current_key: str | None = None
    current_list: list[str] = []
    current_map: dict[str, str] = {}
    base_indent: int | None = None

    def close() -> None:
        nonlocal current_key, current_list, current_map
        if current_key is None:
            return
        if current_map:
            data[current_key] = dict(current_map)
        elif current_list:
            data[current_key] = list(current_list)
        current_key = None
        current_list = []
        current_map = {}

    for line in block:
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is None:
            base_indent = indent
        stripped = line.strip()
        if indent == base_indent and not stripped.startswith("- "):
            close()
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            if value:
                data[key] = _yaml_scalar(value)
            else:
                current_key = key
            continue
        if current_key is None:
            continue
        if stripped.startswith("- "):
            current_list.append(stripped[2:].strip().strip("'\""))
        elif ":" in stripped:
            key, _, value = stripped.partition(":")
            current_map[key.strip()] = value.strip().strip("'\"")
    close()
    return data


def _yaml_scalar(value: str) -> object:
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    return value


def _repo_layers(workspace_root: str) -> list[Layer]:
    layers: list[Layer] = []
    root = Path(workspace_root)
    json_layer = _read_json_layer(REPO, root / ".agent-skills" / "guard-policy.json")
    if json_layer is not None:
        layers.append(json_layer)
    for name in (".agent-skills.yml", ".agent-skills.local.yml"):
        path = root / name
        if not path.is_file():
            continue
        block = _read_yaml_guard_block(path)
        if block is None:
            continue
        layers.append(_layer_from_mapping(REPO, str(path), block))
    return layers


def default_user_policy_path(config_dir: str) -> Path:
    return Path(config_dir) / "guard" / "policy.json"


def _org_policy_paths() -> list[Path]:
    override = os.environ.get("AGENT_SKILLS_GUARD_ORG_POLICY")
    if override:
        return [Path(override).expanduser()]
    return [Path("/etc/agent-skills/guard-policy.json")]


def load(config_dir: str, workspace_root: str) -> Policy:
    """Read every layer and merge it under the trust rules above."""
    policy = Policy()
    layers: list[Layer] = []

    for path in _org_policy_paths():
        layer = _read_json_layer(ORG, path)
        if layer is not None:
            layers.append(layer)

    user_layer = _read_json_layer(USER, default_user_policy_path(config_dir))
    if user_layer is not None:
        layers.append(user_layer)

    layers.extend(_repo_layers(workspace_root))
    policy.layers = layers

    # Floor first. Every rule starts at its compiled outcome.
    for identifier, rule in gr.CATALOGUE.items():
        policy.outcomes[identifier] = rule.outcome

    # The floor a user relaxation may not drop below. It starts at DENY for a
    # hard-floor rule and at ALLOW for everything else — starting it at each
    # rule's compiled default instead would clamp every relaxation back to that
    # default and make machine-scope policy silently inert.
    ceiling: dict[str, str] = {
        identifier: (rule.outcome if rule.floor else gr.ALLOW)
        for identifier, rule in gr.CATALOGUE.items()
    }

    for layer in layers:
        for message in layer.errors:
            policy.errors.append("%s (%s): %s" % (layer.path, layer.scope, message))
        for identifier, requested in layer.rules.items():
            rule = gr.CATALOGUE[identifier]
            current = policy.outcomes.get(identifier, rule.outcome)
            if _ORDER[requested] >= _ORDER[current]:
                policy.outcomes[identifier] = requested
                if layer.scope not in RELAXING_LAYERS:
                    ceiling[identifier] = gr.strictest(ceiling[identifier], requested)
                continue
            # A request to relax.
            if rule.floor:
                policy.weakening_attempts.append(
                    "%s (%s) tried to set the hard-floor rule %s to %s; ignored"
                    % (layer.path, layer.scope, identifier, requested.lower())
                )
                continue
            if layer.scope not in RELAXING_LAYERS:
                policy.weakening_attempts.append(
                    "%s (%s) tried to relax %s to %s; repository and organisation "
                    "configuration may only add restrictions"
                    % (layer.path, layer.scope, identifier, requested.lower())
                )
                continue
            floor_value = ceiling.get(identifier, rule.outcome)
            if _ORDER[requested] < _ORDER[floor_value]:
                policy.weakening_attempts.append(
                    "%s (%s) tried to relax %s below the organisation setting %s; "
                    "clamped" % (layer.path, layer.scope, identifier, floor_value.lower())
                )
                policy.outcomes[identifier] = floor_value
                continue
            policy.outcomes[identifier] = requested

        for pattern in layer.deny_patterns:
            if _valid_regex(pattern, layer, policy):
                policy.deny_patterns.append((pattern, layer.path))
        for pattern in layer.ask_patterns:
            if _valid_regex(pattern, layer, policy):
                policy.ask_patterns.append((pattern, layer.path))
        policy.protected_branches.extend(layer.protected_branches)

        if layer.allow_commands:
            if layer.scope in RELAXING_LAYERS:
                policy.allow_commands.extend(layer.allow_commands)
            else:
                policy.weakening_attempts.append(
                    "%s (%s) supplied allow_commands; only machine-scope policy may "
                    "add an allow list" % (layer.path, layer.scope)
                )
        if layer.audit:
            if layer.scope in (USER, ORG):
                policy.audit = layer.audit
            elif layer.audit == "off":
                policy.weakening_attempts.append(
                    "%s (%s) tried to disable the audit log; ignored"
                    % (layer.path, layer.scope)
                )
            else:
                policy.audit = layer.audit

    env_audit = os.environ.get("AGENT_SKILLS_GUARD_AUDIT")
    if env_audit in ("decisions", "all", "off"):
        policy.audit = env_audit
    return policy


def _valid_regex(pattern: str, layer: Layer, policy: Policy) -> bool:
    try:
        re.compile(pattern)
    except re.error as exc:
        policy.errors.append(
            "%s (%s): pattern %r is not a valid regular expression: %s"
            % (layer.path, layer.scope, pattern, exc)
        )
        return False
    return True
