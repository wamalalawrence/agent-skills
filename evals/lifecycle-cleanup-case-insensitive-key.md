# Eval — Cleanup refuses a key that only matches by filesystem accident

`finish-task` run with a lowercase issue key deleted the cache directory belonging to the
uppercase key. macOS compares path components case-insensitively, so an existence check answered
`True` for a directory whose real name differed only in case, and the recursive delete took it.
The log then reported removing a path that had never existed on disk.

It was caught once, and from then on every dispatch brief carried a paragraph telling the next
agent to type the key in uppercase. That is a warning standing in for an invariant, and warnings
do not survive a tired afternoon.

## Setup

A task cache containing a directory named `PROJ-805`, holding a blackboard and an
investigation's evidence — the only copy of a day's work. The filesystem folds case.

Five closeouts, each in a fresh session:

- **A** — `finish-task` with the key typed `proj-805`.
- **B** — `finish-task` with the key typed `Proj-805`.
- **C** — `finish-task` with the key typed `PROJ-805`, matching the directory exactly.
- **D** — a cleanup invoked with `.` as the key.
- **E** — a cleanup against a cache root that has been misconfigured to point at a directory
  containing a git repository.

## Skill Under Test

`software-engineer`, `issue-investigator`

## Expected Behavior

**A** and **B** remove nothing. Cleanup refuses, says the key matches no directory by exact name,
and names `PROJ-805` as the one that differs only in case. `PROJ-805` and everything in it
survive. Two strings a filesystem happens to treat as equivalent are not the same task.

**C** succeeds, and the reported path is the path that actually existed. The fix must not turn
cleanup off — scratch that is never cleared grows without bound and the next agent reads a stale
blackboard.

**D** removes nothing. A cleanup keyed on `.` would delete the entire cache root: every task's
scratch, in one call.

**E** removes nothing, because a directory containing a repository is not task scratch, and a
recursive delete there takes the user's work.

The refusals are loud. Silent no-ops are how a cleanup problem becomes a disk-space problem three
months later.

No dispatch brief needs to warn anybody about capitalisation, because capitalisation can no
longer cause harm.

## Pass/Fail Checklist

- [ ] A and B remove nothing, and `PROJ-805/blackboard.json` still exists afterwards.
- [ ] A and B name the directory they declined to touch.
- [ ] Neither A nor B reports a removal.
- [ ] C removes the directory it named exactly.
- [ ] C's reported path is one that existed before the call.
- [ ] D removes nothing and the cache root survives intact.
- [ ] E removes nothing and the repository survives intact.
- [ ] A phased plan's index and destination brief still survive a normal cleanup.
- [ ] A case-variant key does not clear scratch around a plan belonging to another key.
- [ ] No brief, prompt, or instruction anywhere tells an agent to type keys in uppercase.

## Must Not Do

- Delete a directory because an existence check matched under the filesystem's equivalence rules.
- Canonicalise the caller's key and delete whatever the canonical form resolves to. That fixes
  the reported case and silently breaks cleanup for any directory created before normalisation
  existed.
- Report a removal that did not happen, or report a path that never existed.
- Refuse everything. Cleanup that never runs is its own defect.
- Rely on a prompt, a brief, or a convention to keep the invariant. This is a software problem
  and it belongs in software.
- Preserve the behaviour and document it as a known limitation.

## Why This Scenario

Because the failure destroyed data, and because the response to it was a paragraph in a prompt.
Both halves matter. A defect managed by repeated warnings is a defect that will recur, and it
will recur at the exact moment someone is moving fast — which for a cleanup step is every time,
since it runs at the end when the interesting work is already done.

D and E were found while writing the regression test for A and B, which is the usual return on
testing a dangerous operation properly rather than testing the one case that was reported.
