#!/usr/bin/env python3
"""Anchor-check tests for scripts/validate-repo.py.

A link to a real Markdown file used to pass even when its `#fragment` named no
heading. These cases pin the slug rules the validator uses and prove the check
itself is what makes them pass: the probe at the end runs the same cases against
a sandboxed copy with the fragment comparison disabled, and the missing-anchor
case has to fail there.

Stdlib only, offline, and everything happens under a temporary directory.

Run: python3 scripts/test-validate-links.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validate-repo.py"
CHECK_LINE = "if unquote(fragment) not in heading_anchors(destination):"

TARGET_DOC = """# Target

### 1.5 Reproduce-before-fix gate (bug fixes only)

## Notes

## Notes

## The `--json` flag

## \U0001F680 Launch plan

## Read [the guide](guide.md) first

```markdown
## Not a heading
```

<a id="explicit-anchor"></a>

**A bold paragraph, not a heading.**
"""

# (name, link text in the source file, number of errors expected)
CASES = [
    ("punctuation is dropped", "[x](target.md#15-reproduce-before-fix-gate-bug-fixes-only)", 0),
    ("first duplicate keeps the bare slug", "[x](target.md#notes)", 0),
    ("second duplicate gets -1", "[x](target.md#notes-1)", 0),
    ("third duplicate does not exist", "[x](target.md#notes-2)", 1),
    ("code span contents stay, backticks go", "[x](target.md#the---json-flag)", 0),
    ("emoji is dropped, its space stays", "[x](target.md#-launch-plan)", 0),
    ("link text is kept, the URL is not", "[x](target.md#read-the-guide-first)", 0),
    ("a heading inside a fence is not a heading", "[x](target.md#not-a-heading)", 1),
    ("an explicit <a id> is an anchor", "[x](target.md#explicit-anchor)", 0),
    ("an empty fragment is an error", "[x](#)", 1),
    ("a missing anchor is an error", "[x](target.md#no-such-heading)", 1),
    ("a same-file fragment resolves", "[x](#source)", 0),
    ("a link inside a code span is not a link", "`[x](target.md#no-such-heading)`", 0),
    ("a link inside a fence is not a link", "```text\n[x](target.md#no-such-heading)\n```", 0),
    ("a fragment on a non-Markdown file is not checked", "[x](script.py#anything)", 0),
    ("an external fragment is not checked", "[x](https://example.com/page#anything)", 0),
]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_cases(module, box: Path) -> list[tuple[str, str]]:
    """Run every case against `module`; return (name, detail) for each that fails."""
    box = box.resolve()
    module.ROOT = box
    module._ANCHOR_CACHE.clear()
    (box / "target.md").write_text(TARGET_DOC, encoding="utf-8")
    (box / "script.py").write_text("print('x')\n", encoding="utf-8")
    failures = []
    for index, (name, link, expected) in enumerate(CASES):
        source = box / f"source-{index}.md"
        text = f"# Source\n\n{link}\n"
        source.write_text(text, encoding="utf-8")
        result = module.Result(errors=[], warnings=[])
        module.check_link_fragments(source, text, result)
        if len(result.errors) != expected:
            failures.append((name, f"expected {expected} error(s), got {result.errors}"))
    return failures


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="as-links-") as tmp:
        box = Path(tmp)
        validator = load(VALIDATOR, "validate_repo_under_test")
        (box / "real").mkdir()
        failures = run_cases(validator, box / "real")
        for name, _link, _expected in CASES:
            if name not in {failed for failed, _ in failures}:
                print(f"  ok    {name}")
        for name, detail in failures:
            print(f"  FAIL  {name}: {detail}")

        source = VALIDATOR.read_text(encoding="utf-8")
        if source.count(CHECK_LINE) != 1:
            print(f"  FAIL  probe: could not find the fragment check line in {VALIDATOR.name}")
            return 1
        weakened_path = box / "validate-repo-weakened.py"
        weakened_path.write_text(source.replace(CHECK_LINE, "if False:"), encoding="utf-8")
        weakened = load(weakened_path, "validate_repo_weakened")
        (box / "weak").mkdir()
        weak_failures = {name for name, _ in run_cases(weakened, box / "weak")}
        probe_ok = "a missing anchor is an error" in weak_failures
        if probe_ok:
            print("  ok    probe: with the fragment check disabled, the missing-anchor case fails")
        else:
            print("  FAIL  probe: the missing-anchor case passed without the fragment check")

    print("")
    print(f"{len(CASES) - len(failures)} passed, {len(failures)} failed, probe {'ok' if probe_ok else 'FAILED'}")
    return 0 if not failures and probe_ok else 1


if __name__ == "__main__":
    sys.exit(main())
