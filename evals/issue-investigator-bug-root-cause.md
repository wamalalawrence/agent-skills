# Issue Investigator Eval: Bug Root Cause

## Input Context

A user reports that invoices marked as paid still appear in the overdue invoice list after a recent
release. They provide anonymized reproduction notes: create invoice, mark it paid through the UI,
refresh the overdue list, and observe that the invoice remains visible. They include a log excerpt
showing the payment event was accepted, but no code, database access, Jira access, or production
credentials are provided.

## Skill Under Test

`issue-investigator`

## Expected Behavior

- Classifies the report as a likely bug or regression only with stated confidence.
- Separates expected behavior, actual behavior, assumptions, and missing evidence.
- Asks for or proposes safe evidence collection before claiming root cause.
- Produces root-cause status as `unknown` or `suspected` unless reproducible code/config evidence is
  supplied.
- Recommends next action based on available evidence and hands fix work to `software-engineer` only
  after the evidence gate is met.

## Required Output Fields

- Investigation result.
- Behavior: expected, actual, affected scope.
- Evidence reviewed.
- Reproduction status.
- Root cause status and confidence.
- Recommended next action.
- Open questions or missing evidence.

## Must Not Do

- Must not invent database schema, queue behavior, logs, or release commits.
- Must not claim root cause is confirmed from the symptom alone.
- Must not recommend direct production mutation.
- Must not skip expected vs actual behavior.

## Pass/Fail Checklist

- [ ] Output includes every required contract section.
- [ ] Facts, assumptions, and unknowns are visibly separated.
- [ ] Root-cause confidence is conservative and evidence-linked.
- [ ] Safe reproduction or evidence collection is proposed.
- [ ] Handoff to `software-engineer` is conditional on sufficient evidence.