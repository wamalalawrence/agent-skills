# meeting-intelligence

Say "Listen to this meeting: <link>" and a visible, named Agent Skills assistant joins the Teams,
Zoom, or Google Meet call. After the recording ends, the transcript is retrieved, redacted, and
cut into bounded windows; your assistant extracts decisions, actions, risks, and the rest as
strict JSON; the CLI validates every fact against the transcript and commits the meeting's facts
to the repository knowledge base in one write.

```bash
agent-skills meeting join https://meet.google.com/abc-defg-hij --title "Payments Architecture"
agent-skills meeting status m_7f3c12ab34cd
agent-skills meeting inspect m_7f3c12ab34cd --facts
```

- The assistant always joins visibly and posts a recording notice; a one-time acknowledgement is
  required first.
- Polling alone carries a meeting to facts; no public URL is needed.
- Facts are claims with status, confidence, and timestamps — `knowledge read` shows them as
  meeting evidence during later engineering work in the same repository.

Skill contract: [SKILL.md](./SKILL.md). Extraction schema:
[references/extraction-contract.md](./references/extraction-contract.md). Full documentation:
[docs/meeting-intelligence.md](../../docs/meeting-intelligence.md).
