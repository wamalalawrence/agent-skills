# Recall adapter fixtures

Sanitised Recall.ai response and webhook bodies used by `scripts/test-meeting.py` to exercise
`scripts/meeting_recall.py` without network access.

They were **constructed from Recall's published API reference** (bot, status-change, transcript,
and webhook schemas at docs.recall.ai), not captured from a live account: no Recall key was used to
build this release. Identifiers are random placeholders, participant names are fictional, and the
download URLs point at `storage.example.com` with a placeholder signature. When a live smoke run
(`AGENT_SKILLS_MEETING_LIVE_SMOKE=1`) shows a difference from the real API, update the fixture and
the adapter together.
