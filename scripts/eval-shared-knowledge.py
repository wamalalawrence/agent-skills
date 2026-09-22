#!/usr/bin/env python3
"""Evals 18 and 19 of the shared-knowledge brief: three installations, one source.

What this measures, and what it does not: it measures what each installation's
agent is **given** when it asks the question — the ranked, labelled knowledge
`agent-skills knowledge read --brief` returns at task start. It does not
measure how a model phrases its answer. The CLI never calls a model
(docs/meeting-intelligence/DISCOVERY.md §2), so "the three agents answer
consistently" is reduced to the part the runtime controls: the three agents
are handed the same current fact, labelled the same way, and never handed a
superseded one as current.

Offline, like the test suite: remotes are local bare repositories behind git's
`insteadOf`, reusing the suite's harness.

  18. Before approval only the proposer sees the meeting-derived decision, and
      it is labelled `local, unshared`. After one engineer proposes it, a
      reviewer merges it, and everyone syncs, all three installations get the
      same top answer to "how are payment retries implemented?".
  19. Once the superseding fact is synced, the superseded decision is never
      presented as current, across every installation and a set of phrasings.

Run: python3 scripts/eval-shared-knowledge.py [--out eval-runs/<release>/shared-knowledge]
Exit status is 0 only when every rate meets its target.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sk_harness", HERE / "test-shared-knowledge.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)  # type: ignore[union-attr]

km = harness.km
QUESTION = "how are payment retries implemented?"
PHRASINGS = (QUESTION, "where are payment retries stored", "retry queue table", "retry_queue",
             "payment retry design", "kafka retries")
OLD = "Retries are stored in the retry_queue table."
NEW = "Payment retries use Kafka."
INSTALLATIONS = (("a", "https://example.com/acme/payments-service.git"),
                 ("b", "git@example.com:acme/payments-service.git"),
                 ("c", "https://example.com/acme/payments-service"))


def top_current(text: str) -> str:
    """The first shared/local fact line of the knowledge section, as an agent sees it."""
    for line in text.splitlines():
        if line.startswith("- [") and "conflict" not in line:
            return line
    return ""


def presented_as_current(text: str, statement: str) -> bool:
    for line in text.splitlines():
        if statement in line and "superseded" not in line.lower() and "history" not in line:
            return True
    return False


def run(out_dir: Path) -> dict:
    box = harness.Box(Path(tempfile.mkdtemp(prefix="as-shared-eval-")))
    saved = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(box.env("a"))
        old = harness.fact(OLD, scope="team:payments")
        url = box.source("acme")
        box.admin_commit(url, lambda c: (c / km.fact_location(old)).parent.mkdir(parents=True, exist_ok=True)
                         or (c / km.fact_location(old)).write_text(km.canonical_json(old)), merge=True)
        repos = {}
        for name, remote in INSTALLATIONS:
            repos[name] = box.code_repo("payments-service", remote, inst=name)
            box.connect(repos[name], url, name)
        # Engineer A's meeting decides the replacement; it lands in A's repository tier only.
        with box.use("a"):
            payload = harness.meeting_payload(repos["a"], NEW)
            harness.knowledge_resolver.write_meeting_facts(repos["a"], payload)
        meeting_fact_id = payload["facts"][0]["id"]

        before = {name: box.ok("read", "--brief", QUESTION, cwd=repos[name], inst=name) for name, _ in INSTALLATIONS}
        proposer_line = [l for l in before["a"].splitlines() if NEW in l]
        before_ok = {
            "proposer_sees_it_labelled_local_unshared": bool(proposer_line) and "[local, unshared]" in proposer_line[0],
            "others_do_not_see_it": [NEW not in before[n] for n in ("b", "c")],
        }

        # Engineer B still believes decision Y and has it recorded locally.
        box.ok("record", "--type", "DECISION", "--statement", OLD, "--scope", "team:payments", "--status",
               "CONFIRMED", "--source", "manual:old-design-doc", cwd=repos["b"], inst="b")
        box.ok("propose", meeting_fact_id, "--scope", "team:payments", "--supersedes", old["id"], "--yes",
               cwd=repos["a"], inst="a")
        box.merge_proposal(url, reviewer=("Rita Reviewer", "rita@example.com"), number=31)
        sync_output = {}
        for name, _ in INSTALLATIONS:
            sync_output[name] = box.ok("sync", cwd=repos[name], inst=name)
        b_notified = "now SUPERSEDED: {}".format(old["id"]) in sync_output["b"]

        answers = {}
        for name, _ in INSTALLATIONS:
            text = box.ok("read", "--brief", QUESTION, cwd=repos[name], inst=name)
            answers[name] = top_current(text)
        consistent = [NEW in line and "CONFIRMED" in line and "shared:acme" in line and "Rita Reviewer" in line
                      for line in answers.values()]
        normalised = {re.sub(r"\s+", " ", line) for line in answers.values()}

        leaks = []
        trials = 0
        for name, _ in INSTALLATIONS:
            for phrase in PHRASINGS:
                trials += 1
                text = box.ok("read", "--brief", phrase, cwd=repos[name], inst=name)
                if presented_as_current(text, OLD):
                    leaks.append({"installation": name, "brief": phrase})
        history = box.ok("inspect", old["id"], "--json", cwd=repos["b"], inst="b")
        successor = json.loads(history)["successors"]

        result = {
            "eval_18": {
                "before_approval": before_ok,
                "after_approval": {"answers": answers, "consistent": sum(consistent), "installations": len(consistent),
                                   "identical_lines": len(normalised) == 1},
                "rate": sum(consistent) / len(consistent),
                "target": 1.0,
            },
            "eval_19": {
                "trials": trials, "presented_as_current": len(leaks), "leaks": leaks,
                "rate": 1 - (len(leaks) / trials), "target": 1.0,
                "old_fact_links_forward": [s["id"] for s in successor],
                "engineer_b_told_on_sync": b_notified,
            },
        }
        result["met"] = (
            result["eval_18"]["rate"] == 1.0 and before_ok["proposer_sees_it_labelled_local_unshared"]
            and all(before_ok["others_do_not_see_it"]) and result["eval_19"]["rate"] == 1.0
            and result["eval_18"]["after_approval"]["identical_lines"] and b_notified
        )
    finally:
        os.environ.clear()
        os.environ.update(saved)
        shutil.rmtree(box.path, ignore_errors=True)
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        (out_dir / "scores.md").write_text(render(result))
    return result


def render(result: dict) -> str:
    e18, e19 = result["eval_18"], result["eval_19"]
    before = e18["before_approval"]
    lines = [
        "# Shared knowledge evals (18, 19)", "",
        "Produced by `python3 scripts/eval-shared-knowledge.py`. Deterministic and offline: three simulated",
        "installations share one bare-repository source. What is measured is what each agent is given",
        "by `knowledge read --brief`, not how a model phrases its answer.", "",
        "| Eval | Property | Result | Target | Met |", "| --- | --- | --- | --- | --- |",
        "| 18 | before approval, the proposer sees it labelled `local, unshared` | {} | yes | {} |".format(
            "yes" if before["proposer_sees_it_labelled_local_unshared"] else "no",
            "yes" if before["proposer_sees_it_labelled_local_unshared"] else "no"),
        "| 18 | before approval, the other two do not see it | {}/2 | 2/2 | {} |".format(
            sum(before["others_do_not_see_it"]), "yes" if all(before["others_do_not_see_it"]) else "no"),
        "| 18 | after approval + sync, the same CONFIRMED shared top answer | {}/{} ({:.0%}) | 100% | {} |".format(
            e18["after_approval"]["consistent"], e18["after_approval"]["installations"], e18["rate"],
            "yes" if e18["rate"] == 1.0 else "no"),
        "| 19 | superseded decision never presented as current | {}/{} clean ({:.0%}) | 100% | {} |".format(
            e19["trials"] - e19["presented_as_current"], e19["trials"], e19["rate"],
            "yes" if e19["rate"] == 1.0 else "no"),
        "| 19 | engineer B, who held the old decision locally, is told on sync | {} | yes | {} |".format(
            "yes" if e19["engineer_b_told_on_sync"] else "no", "yes" if e19["engineer_b_told_on_sync"] else "no"),
        "",
        "Top answer each installation was given after approval:", "",
    ]
    for name, line in sorted(e18["after_approval"]["answers"].items()):
        lines.append("- `{}`: {}".format(name, line.replace("|", "\\|")))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evals 18-19: shared knowledge across installations.")
    parser.add_argument("--out", default="", help="Directory for results.json and scores.md.")
    args = parser.parse_args()
    result = run(Path(args.out) if args.out else None)
    print(render(result))
    print("SHARED_KNOWLEDGE_EVALS: {}".format("PASS" if result["met"] else "FAIL"))
    return 0 if result["met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
