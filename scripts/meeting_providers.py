#!/usr/bin/env python3
"""The capture providers the user can choose from, and the words that explain them.

This is the one composition root for capture providers: the only module that
imports `meeting_recall`, `meeting_native`, or `meeting_desktop`, and only
inside the functions that need them. Meeting Intelligence (`meeting.py`,
`meeting_intel.py`, `meeting_store.py`) asks this module three things:

  * which provider the user chose (`default_provider`, or `--via`),
  * whether it can run on this machine (`readiness`, local checks only), and
  * to build it (`build`).

It also owns the texts a user must see before a provider is used: the
no-provider preflight, the side-by-side comparison, and each provider's
versioned cost / data-flow / consent notice. A notice records the version the
user acknowledged; when the text changes, the version moves and the notice is
shown again.

Nothing here ever picks a provider for the user, and nothing falls back from
one provider to another.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict, List, Optional

import meeting_capture as mc

PROVIDERS = ("native", "recall", "desktop")
# Printed as full paths inside this release, so they open from any directory.
_DOCS_ROOT = Path(__file__).resolve().parent.parent / "docs" / "meeting-intelligence"
DOCS = str(_DOCS_ROOT / "README.md")
PRIVACY_DOCS = str(_DOCS_ROOT / "PRIVACY.md")
DEFAULT_RECALL_COST_PER_HOUR = 0.65  # USD: $0.50 recording + $0.15 transcription (recall.ai/pricing, 2026-09-23)

HOST_MODEL_NOTE = ("In every mode, fact extraction runs in your AI assistant (Claude Code, Cursor, Codex, "
                   "Copilot, ...), so transcript text is sent to that assistant's model provider during "
                   "extraction.")

NOTICE_VERSIONS = {"native": 1, "recall": 1, "desktop": 1}


def recall_cost_per_hour(config: Dict[str, object]) -> float:
    section = config.get("recall") if isinstance(config.get("recall"), dict) else {}
    try:
        value = float(section.get("cost_per_hour_usd", DEFAULT_RECALL_COST_PER_HOUR))  # type: ignore[union-attr]
    except (TypeError, ValueError):
        value = DEFAULT_RECALL_COST_PER_HOUR
    return max(0.0, min(100.0, value))


def cost_line(config: Dict[str, object], provider: str) -> str:
    if provider == "recall":
        return "Billed by Recall to your account, ≈ ${:.2f}/meeting hour.".format(recall_cost_per_hour(config))
    if provider == "native":
        return "No extra cost beyond your existing Teams / Google Workspace / Zoom licence."
    return "No extra cost: your computer's CPU/GPU time only."


def data_line(provider: str) -> str:
    if provider == "recall":
        return ("Audio and transcript are processed by Recall.ai (a third party) in your chosen region; "
                "media is deleted there once the transcript is stored.")
    if provider == "native":
        return ("The transcript stays in your organisation's tenant; Agent Skills downloads a copy "
                "with your own sign-in.")
    return "Audio never leaves this computer; it is deleted after local transcription."


def notice_text(config: Dict[str, object], provider: str) -> str:
    """The versioned notice `meeting setup <provider>` shows and records."""
    lines = {
        "native": [
            "Native transcript — what you are agreeing to:",
            "  • No bot joins. The meeting platform makes the transcript; someone in the meeting",
            "    switches transcription on, and every participant sees the platform's own banner.",
            "  • " + cost_line(config, "native"),
            "  • " + data_line("native"),
            "  • Agent Skills reads only what your account can read (delegated sign-in) and never",
            "    deletes anything in the platform; the transcript follows your organisation's retention.",
        ],
        "recall": [
            "Recall bot — what you are agreeing to:",
            "  • A visible participant named \"{}\" joins and posts a recording notice in chat.".format(
                config.get("bot_name", "Agent Skills Meeting Assistant")),
            "  • " + cost_line(config, "recall") + " Recall bills your own account; a few hours are",
            "    free at signup. Agent Skills never sees the bill.",
            "  • " + data_line("recall"),
            "  • Recall processes every participant's voice as your data processor. Your organisation",
            "    may need a data processing agreement (DPA) with Recall and, in Germany, often a",
            "    works-council agreement before using it.",
        ],
        "desktop": [
            "Local desktop capture — what you are agreeing to:",
            "  • This computer records the meeting's audio (your microphone and the system audio)",
            "    and transcribes it locally with whisper.cpp. No bot joins.",
            "  • NO ONE IN THE MEETING IS NOTIFIED AUTOMATICALLY. Before every recording you must tell",
            "    all participants and get their agreement; you will be asked to confirm that each time.",
            "    Recording people without their knowledge can be unlawful (e.g. §201 StGB in Germany).",
            "  • " + cost_line(config, "desktop"),
            "  • " + data_line("desktop"),
            "  • Speakers are not identified individually: only \"You\" and \"Remote participants\".",
        ],
    }[provider]
    lines += ["  • " + HOST_MODEL_NOTE, "  Details: " + PRIVACY_DOCS]
    return "\n".join(lines)


def notice_current(config: Dict[str, object], provider: str) -> bool:
    notices = config.get("provider_notices") if isinstance(config.get("provider_notices"), dict) else {}
    entry = notices.get(provider) if isinstance(notices, dict) else None
    return isinstance(entry, dict) and entry.get("version") == NOTICE_VERSIONS[provider]


def record_notice(config: Dict[str, object], provider: str, how: str, when: str) -> None:
    notices = config.get("provider_notices") if isinstance(config.get("provider_notices"), dict) else {}
    notices = dict(notices)  # type: ignore[arg-type]
    notices[provider] = {"version": NOTICE_VERSIONS[provider], "at": when, "how": how}
    config["provider_notices"] = notices


# ---------------------------------------------------------------------------
# Readiness and construction
# ---------------------------------------------------------------------------
def readiness(config: Dict[str, object], provider: str) -> mc.Readiness:
    try:
        if provider == "recall":
            import meeting_recall

            return meeting_recall.readiness(config)
        if provider == "native":
            import meeting_native

            return meeting_native.readiness(config)
        if provider == "desktop":
            import meeting_desktop

            return meeting_desktop.readiness(config)
    except Exception as exc:  # noqa: BLE001 - readiness is a report, never a crash
        return mc.Readiness(mc.BROKEN, "readiness check failed ({})".format(type(exc).__name__),
                            "agent-skills meeting setup " + provider)
    raise ValueError("unknown provider {!r}".format(provider))


def build(config: Dict[str, object], provider: str, need_secret: bool = False) -> mc.MeetingCaptureProvider:
    if provider == "recall":
        import meeting_recall

        return meeting_recall.from_config(config, need_secret)
    if provider == "native":
        import meeting_native

        return meeting_native.from_config(config)
    if provider == "desktop":
        import meeting_desktop

        return meeting_desktop.DesktopCaptureProvider(config)
    raise mc.ProviderRequestError("unknown capture provider {!r}".format(provider))


def default_provider(config: Dict[str, object]) -> Optional[str]:
    """The user's chosen default; for a 1.3.0 installation with Recall configured, recall.

    Returns None when nothing was chosen. Never guesses between providers.
    """
    chosen = str(config.get("default_provider") or "")
    if chosen in PROVIDERS:
        return chosen
    if readiness(config, "recall").state != mc.NOT_CONFIGURED:
        return "recall"  # migration: Recall was the only provider before 1.4.0
    return None


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------
def preflight_text(config: Dict[str, object]) -> str:
    return "\n".join([
        "Meeting Intelligence isn't set up yet. Choose how meetings are captured:",
        "",
        "  native   Download the transcript Teams/Meet/Zoom already makes.",
        "           No bot, no extra cost, data stays in your org.",
        "           Needs: your org admin to register Agent Skills once (guide below),",
        "           and transcription switched on in the meeting.",
        "",
        "  recall   A visible \"{}\" bot joins the call.".format(config.get("bot_name", "Agent Skills Meeting Assistant")),
        "           Works for any meeting, including other companies'.",
        "           Needs: your own Recall.ai account. Cost ≈ ${:.2f} per meeting hour,".format(
            recall_cost_per_hour(config)),
        "           billed by Recall. Recall processes the audio (EU region available).",
        "",
        "  desktop  Your computer records the meeting and transcribes it locally.",
        "           No bot, no extra cost, audio never leaves your machine.",
        "           Needs: ffmpeg, whisper.cpp, a model download, system-audio setup.",
        "           No one in the meeting is notified automatically; you must tell them.",
        "",
        "In every mode your AI assistant extracts the facts, so transcript text reaches its model provider.",
        "",
        "Set up one:   agent-skills meeting setup native|recall|desktop",
        "Compare:      agent-skills meeting setup --compare",
        "Full guide:   " + DOCS,
    ])


COMPARE_ROWS = [
    ("", "native", "recall", "desktop"),
    ("What happens", "platform transcribes;", "visible bot joins", "this computer records"),
    ("", "fetched after meeting", "and transcribes", "whisper.cpp transcribes"),
    ("Bot in meeting", "no", "yes, named, visible", "no"),
    ("Extra cost", "none (platform licence)", "≈ ${cost:.2f}/h, Recall bills you", "none (local CPU/GPU)"),
    ("Audio/transcript leaves org", "no (org tenant)", "yes, to Recall", "no"),
    ("Setup", "admin: app registration", "you: Recall account,", "you: ffmpeg, whisper.cpp,"),
    ("", "you: browser sign-in", "key, region", "model, system audio"),
    ("Other orgs' meetings", "no", "yes", "yes"),
    ("Speaker names", "yes", "yes", "no: You / Remote"),
    ("Participants notified by", "platform banner", "bot + chat notice", "NOBODY: you must tell them"),
    ("Platforms", "Teams, Meet, Zoom (host)", "Teams, Meet, Zoom", "any (macOS, Linux)"),
]


def compare_text(config: Dict[str, object]) -> str:
    cost = recall_cost_per_hour(config)
    widths = (28, 25, 30, 27)
    out = []
    for row in COMPARE_ROWS:
        cells = [c.format(cost=cost) for c in row]
        out.append("  " + "".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip())
    out += [""] + textwrap.wrap(HOST_MODEL_NOTE, 100, initial_indent="  ", subsequent_indent="  ") + [
        "",
        "  Set up one:  agent-skills meeting setup native|recall|desktop",
        "  Guides:      " + DOCS + " (per-provider setup, data flow, costs, privacy)",
    ]
    return "\n".join(out)


def status_rows(config: Dict[str, object]) -> List[dict]:
    default = default_provider(config)
    rows = []
    for provider in PROVIDERS:
        state = readiness(config, provider)
        rows.append({
            "provider": provider,
            "default": provider == default,
            "state": state.state,
            "reason": state.reason,
            "fix_command": state.fix_command,
            "detail": state.detail,
            "notice_acknowledged": notice_current(config, provider),
        })
    return rows


def status_line(row: dict) -> str:
    if row["state"] == mc.READY:
        text = "ready"
    elif row["state"] == mc.NOT_CONFIGURED:
        text = "not configured"
    else:
        text = "broken: {} → {}".format(row["reason"], row["fix_command"])
    detail = "  ({})".format(row["detail"]) if row["detail"] and row["state"] == mc.READY else ""
    return "{:<8} {}{}{}".format(row["provider"], text, detail, "   [default]" if row["default"] else "")


def alternatives(provider: str) -> str:
    others = [p for p in PROVIDERS if p != provider]
    return "Alternatives: --via {} or --via {} (each needs its own setup; nothing switches automatically).".format(
        *others)


def probe_desktop_loopback(config: Dict[str, object]) -> str:
    """doctor --probe-meeting only: is the system-audio input present and carrying audio?

    Records one second from the loopback/monitor input — never the microphone —
    and keeps nothing.
    """
    try:
        import meeting_desktop

        return meeting_desktop.probe_loopback(config)
    except Exception as exc:  # noqa: BLE001 - a report, never a crash
        return "probe failed ({})".format(type(exc).__name__)
