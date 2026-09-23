# meeting-intelligence

Say "Listen to this meeting: <link>" and Agent Skills captures the Teams, Zoom, or Google Meet
meeting the way **you** chose: the platform's own transcript (`native`, no bot), a visible, named
Recall bot (`recall`), or a local recording on your computer transcribed with whisper.cpp
(`desktop`). The transcript is redacted and cut into bounded windows; your assistant extracts
decisions, actions, risks, and the rest as strict JSON; the CLI validates every fact against the
transcript and commits the meeting's facts to the repository knowledge base in one write.

```bash
agent-skills meeting setup --compare          # the three options: cost, data flow, consent
agent-skills meeting setup native             # or recall, or desktop — guided, with a self-test
agent-skills meeting join https://meet.google.com/abc-defg-hij --title "Payments Architecture"
agent-skills meeting status m_7f3c12ab34cd
agent-skills meeting inspect m_7f3c12ab34cd --facts
```

- Nothing is captured until you choose a provider; with none chosen, the assistant shows you the
  options instead of failing.
- A provider that cannot serve a meeting says why and what else exists. Nothing switches providers
  on its own.
- A local recording is started only by you, in your terminal, after you tell the participants.
- Facts are claims with status, confidence, and timestamps — `knowledge read` shows them as
  meeting evidence during later engineering work in the same repository.

Skill contract: [SKILL.md](./SKILL.md). Extraction schema:
[references/extraction-contract.md](./references/extraction-contract.md). Capture options, setup
guides, and privacy: [docs/meeting-intelligence/](../../docs/meeting-intelligence/README.md).
