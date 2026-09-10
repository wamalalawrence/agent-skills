#!/usr/bin/env python3
"""Choose how much workflow a piece of work actually needs.

    agent-skills execution-profile --reads-only --size S --uncertainty low
    agent-skills execution-profile --domain security --json
    agent-skills execution-profile --size M --mutates --blast-radius service

The problem this solves is not that the workflow is too slow. It is that the
same workflow was applied to work of wildly different consequence. A request for
three read-only numbers received the same treatment as a security-sensitive
production fix: three fresh-context dispatches, three evidence dossiers over
40 KB each, for a question whose answer was a small table. The rigour was real
and it was aimed at nothing.

So the rule is: *apply the minimum workflow that reaches the required
confidence, and raise it with complexity, uncertainty, risk, blast radius, and
irreversibility.* Not "go faster". A faster wrong answer is a regression, which
is why the escalation half of this file is unconditional and the relaxation half
is hedged with conditions.

Three profiles:

  LIGHT      bounded read-only lookup, small factual retrieval, a trivial
             deterministic change. Skips delivery plans, phase decomposition,
             fresh-agent handoffs, independent review agents, and dossier-shaped
             output. Keeps every safety invariant below.
  STANDARD   ordinary engineering: investigate, implement, developer-test,
             review. The default, and what an unclassified task gets.
  RIGOROUS   security controls, cryptography, schema migrations, production
             infrastructure, payment correctness, cross-system change, anything
             irreversible. Full fresh-context isolation, independent review,
             mutation testing, complete evidence.

The invariants in `ALWAYS_REQUIRED` hold at every profile including LIGHT.
LIGHT buys less ceremony, never less safety: a lookup still resolves credentials
properly, still respects authorization, still bounds what it reads, still
verifies its answer, and still leaves evidence behind.

Determinism is the point. The same signals always produce the same profile, so
the choice can be tested, reproduced from a plan file, and argued with. A model
deciding "this feels small" is not a mechanism.

Exit codes:
  0  a profile was decided
  2  usage error
"""
from __future__ import annotations

import argparse
import json
import sys

LIGHT = "LIGHT"
STANDARD = "STANDARD"
RIGOROUS = "RIGOROUS"

ORDER = (LIGHT, STANDARD, RIGOROUS)

# Domains where the cost of being wrong is not paid by the person who was wrong.
# Naming any of these forces RIGOROUS and no combination of other signals
# lowers it. The list is deliberately short: every entry is a domain where the
# repository already refuses to take shortcuts elsewhere.
ESCALATING_DOMAINS = {
    "security": "a security control decides who can do what",
    "crypto": "cryptography fails silently and review is the only detector",
    "auth": "an authentication or authorization change is a security control",
    "migration": "a schema migration is applied once against real data",
    "infrastructure": "production infrastructure has no undo for its blast radius",
    "payments": "payment correctness is money, and reconciliation is expensive",
    "credentials": "credential handling is the boundary that cannot be un-crossed",
    "data-loss": "a change that can destroy data gets the most rigour available",
    "cross-system": "a change spanning systems fails at the seams nobody owns",
}

# Everything at every profile. This tuple is the answer to "what does LIGHT give
# up?" — nothing on this list.
ALWAYS_REQUIRED = (
    "credential-safety",
    "authorization-checks",
    "bounded-reads",
    "explicit-verification",
    "evidence-retained",
    "safety-floor",
)

REQUIREMENTS = {
    LIGHT: {
        "fresh_context_dispatch": False,
        "independent_review": False,
        "delivery_plan": False,
        "phase_decomposition": False,
        "mutation_testing": False,
        "evidence_depth": "retained-separately",
        "max_dispatches": 1,
    },
    STANDARD: {
        "fresh_context_dispatch": True,
        "independent_review": True,
        "delivery_plan": False,
        "phase_decomposition": False,
        "mutation_testing": False,
        "evidence_depth": "cited-inline",
        "max_dispatches": 3,
    },
    RIGOROUS: {
        "fresh_context_dispatch": True,
        "independent_review": True,
        "delivery_plan": True,
        "phase_decomposition": True,
        "mutation_testing": True,
        "evidence_depth": "full",
        "max_dispatches": 6,
    },
}


def _at_least(current: str, floor: str) -> str:
    return current if ORDER.index(current) >= ORDER.index(floor) else floor


def decide(args: argparse.Namespace) -> dict:
    """Map signals to a profile. Pure, ordered, and total."""
    reasons: list[str] = []
    floor = LIGHT
    floor_triggered = False

    # ---- Escalation. Unconditional, evaluated first, never undone. ----------
    for domain in sorted(set(args.domain or [])):
        why = ESCALATING_DOMAINS.get(domain)
        if why:
            floor = RIGOROUS
            floor_triggered = True
            reasons.append(f"domain '{domain}' forces RIGOROUS: {why}")

    if args.reversible == "no":
        floor = RIGOROUS
        floor_triggered = True
        reasons.append("the change is irreversible, so review has to happen before it lands")

    if args.blast_radius in {"production", "cross-system"}:
        floor = RIGOROUS
        floor_triggered = True
        reasons.append(
            f"blast radius '{args.blast_radius}' reaches beyond the change's own component"
        )

    if args.require == RIGOROUS:
        floor = RIGOROUS
        floor_triggered = True
        reasons.append("RIGOROUS was requested explicitly")

    # ---- Relaxation. Only from a clean floor, and only when every condition
    # holds. Any unknown leaves it at STANDARD, because "not stated" is not
    # "not risky". -----------------------------------------------------------
    if floor_triggered:
        profile = RIGOROUS
    else:
        light_conditions = {
            "the work only reads": args.reads_only and not args.mutates,
            "it is sized S": args.size == "S",
            "uncertainty is low": args.uncertainty == "low",
            "no shared mutable state is touched": not args.shared_state,
            "blast radius is contained": args.blast_radius == "contained",
            "nothing depends on it": args.dependencies == 0,
            "verification is cheap": args.verification_cost == "low",
        }
        unmet = [name for name, held in light_conditions.items() if not held]
        if not unmet:
            profile = LIGHT
            reasons.append(
                "LIGHT: every relaxation condition holds — "
                + ", ".join(sorted(light_conditions))
            )
        else:
            profile = STANDARD
            reasons.append("STANDARD: " + "; ".join(f"not true that {name}" for name in unmet))

    # An explicit request can raise the profile but never lower a floor. Asking
    # for LIGHT on a migration is exactly the mistake this refuses to make.
    if args.require:
        raised = _at_least(profile, args.require)
        if raised != profile:
            reasons.append(f"raised to {raised} because it was requested")
            profile = raised
        elif ORDER.index(args.require) < ORDER.index(profile):
            reasons.append(
                f"requested {args.require} was NOT applied: "
                f"{profile} is a floor here and a floor does not come down"
            )

    return {
        "profile": profile,
        "floor_triggered": floor_triggered,
        "reasons": reasons,
        "requires": dict(REQUIREMENTS[profile]),
        "always_required": list(ALWAYS_REQUIRED),
    }


def render_text(decision: dict) -> str:
    lines = [f"profile: {decision['profile']}"]
    if decision["floor_triggered"]:
        lines.append("floor:   RIGOROUS — escalated by a signal that cannot be overridden")
    lines.append("")
    lines.append("why:")
    for reason in decision["reasons"]:
        lines.append(f"  - {reason}")
    lines.append("")
    lines.append("this profile requires:")
    for key, value in decision["requires"].items():
        lines.append(f"  {key:<26} {value}")
    lines.append("")
    lines.append("required at every profile, including LIGHT:")
    lines.append("  " + ", ".join(decision["always_required"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Choose LIGHT, STANDARD, or RIGOROUS for one task or phase.",
        epilog=(
            "Unstated signals are treated as risky, not as safe. A bare "
            "invocation returns STANDARD."
        ),
    )
    parser.add_argument(
        "--reads-only",
        action="store_true",
        help="the work reads and does not write anything",
    )
    parser.add_argument(
        "--mutates",
        action="store_true",
        help="the work changes state; cancels --reads-only",
    )
    parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help=(
            "subject area, repeatable. Any of "
            + ", ".join(sorted(ESCALATING_DOMAINS))
            + " forces RIGOROUS."
        ),
    )
    parser.add_argument(
        "--reversible",
        choices=("yes", "no", "unknown"),
        default="unknown",
        help="can the change be undone? 'no' forces RIGOROUS",
    )
    parser.add_argument(
        "--blast-radius",
        choices=("contained", "service", "cross-system", "production"),
        default="service",
        help="how far a mistake reaches",
    )
    parser.add_argument(
        "--uncertainty",
        choices=("low", "medium", "high"),
        default="medium",
        help="how well understood the work is",
    )
    parser.add_argument(
        "--size",
        choices=("S", "M", "L"),
        default="M",
        help="rough effort",
    )
    parser.add_argument(
        "--shared-state",
        action="store_true",
        help="the work touches state other work also touches",
    )
    parser.add_argument(
        "--verification-cost",
        choices=("low", "medium", "high"),
        default="medium",
        help="how expensive it is to prove the result correct",
    )
    parser.add_argument(
        "--dependencies",
        type=int,
        default=0,
        help="how many other pieces of work depend on this one",
    )
    parser.add_argument(
        "--require",
        choices=ORDER,
        default=None,
        help="request a profile. It can raise the result; it cannot lower a floor",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args(argv)
    if args.dependencies < 0:
        sys.stderr.write("execution-profile: --dependencies cannot be negative\n")
        return 2

    unknown = sorted(set(args.domain or []) - set(ESCALATING_DOMAINS))
    if unknown:
        # Not an error. A domain nobody escalated on is ordinary work, and
        # rejecting it would push callers towards omitting the flag entirely.
        sys.stderr.write(
            "execution-profile: no escalation rule for domain(s) "
            + ", ".join(repr(name) for name in unknown)
            + "; they did not affect the result\n"
        )

    decision = decide(args)
    if args.json:
        sys.stdout.write(json.dumps(decision, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(decision) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
