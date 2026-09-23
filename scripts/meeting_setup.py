#!/usr/bin/env python3
"""`agent-skills meeting setup [native|recall|desktop] [--compare] [--import <file>]`.

A guided, re-runnable setup per capture provider. Each run checks every
prerequisite in order, prints the next step, and ends with a self-test that
proves the provider works without capturing anything real:

    recall   account → region → API key (hidden) → [verification secret] →
             authenticated read that creates no bot
    native   admin config (--import, never a secret) → [client secret, hidden] →
             browser sign-in (PKCE, loopback) → a harmless read, no transcript
    desktop  ffmpeg → whisper-cli → model download (on request, checksum) →
             system-audio devices → 5-second two-channel record + transcription

Then it records the user's default and the versioned acknowledgement of that
provider's cost / data-flow / consent notice.

Steps that need the person — typing a secret, signing in in a browser,
acknowledging a notice, recording a self-test — run only at an interactive
terminal. Anywhere else (an assistant running this for the user) setup prints
the instructions and stops: nothing is automated or answered on the user's
behalf.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import meeting_capture as mc
import meeting_providers as providers
import meeting_store as store

EXIT_OK, EXIT_USAGE, EXIT_AUTH, EXIT_NETWORK = 0, 2, 3, 4

# Replaced by the tests; there is no flag or variable that skips a person.
INTERACTIVE: Callable[[], bool] = lambda: sys.stdin.isatty() and sys.stdout.isatty()  # noqa: E731
ASK: Callable[[str], str] = input
ASK_SECRET: Callable[[str], str] = getpass.getpass
OPEN_BROWSER: Optional[Callable[[str], object]] = None


def out(text: str = "") -> None:
    print(text)


class Steps:
    def __init__(self, title: str) -> None:
        self.n = 0
        out(title)

    def step(self, text: str) -> None:
        self.n += 1
        out("[{}] {}".format(self.n, text))

    @staticmethod
    def ok(text: str) -> None:
        out("    ok  " + text)

    @staticmethod
    def todo(text: str) -> None:
        out("    ->  " + text)


def _needs_person(steps: Steps, provider: str, what: List[str]) -> int:
    steps.todo("The next step needs you at a terminal: " + ", ".join(what) + ".")
    out("")
    out("Run this yourself, in your own terminal (an assistant must not do it for you):")
    out("    agent-skills meeting setup " + provider)
    out("It is safe to re-run; finished steps are skipped.")
    return EXIT_USAGE


def _confirm(prompt: str, word: str = "yes") -> bool:
    return ASK(prompt).strip().lower() == word


def _acknowledge(steps: Steps, config: Dict[str, object], provider: str) -> bool:
    steps.step("Cost, data flow, and consent")
    out(providers.notice_text(config, provider))
    if providers.notice_current(config, provider) and \
            (config.get("provider_notices") or {}).get(provider, {}).get("how") == "setup":  # type: ignore[union-attr]
        steps.ok("already acknowledged (notice v{})".format(providers.NOTICE_VERSIONS[provider]))
        return True
    if not _confirm("Type 'yes' if you have read this and want to use {}: ".format(provider)):
        steps.todo("not acknowledged; nothing was changed")
        return False
    providers.record_notice(config, provider, "setup", store.now_iso())
    return True


def _finish(steps: Steps, config: Dict[str, object], provider: str, make_default: bool) -> int:
    if make_default:
        config["default_provider"] = provider
    store.save_config(config)
    state = providers.readiness(config, provider)
    out("")
    if state.ready:
        out("{} is ready{}.".format(provider, " and is now your default" if make_default else ""))
        out("Capture a meeting: agent-skills meeting join <meeting-url>{}".format(
            "" if make_default else " --via " + provider))
        return EXIT_OK
    out("{} is not ready yet: {} → {}".format(provider, state.reason, state.fix_command))
    return EXIT_USAGE


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------
def setup_recall(args, config: Dict[str, object]) -> int:
    import access
    import meeting_recall as recall

    steps = Steps("Set up: recall (a visible Recall.ai bot joins your meetings)")
    steps.step("A Recall.ai account")
    out("    Create one at https://www.recall.ai (pay as you go; the first hours are free).")
    out("    " + providers.cost_line(config, "recall"))
    key, secret, stored_region = recall.credential_presence()
    steps.step("Region (keys, bots, and recordings are region-local)")
    suggested = recall.suggest_region()
    region = args.region or str(config.get("region") or "") or stored_region
    if region and region not in recall.REGIONS:
        steps.todo("unknown region {!r}; choose one of {}".format(region, ", ".join(recall.REGIONS)))
        return EXIT_USAGE
    if not region:
        out("    Regions: {}. Suggested for you: {}{}".format(", ".join(recall.REGIONS), suggested,
                                                             " (keeps data in the EU)" if suggested == recall.EU_REGION else ""))
        if not INTERACTIVE():
            return _needs_person(steps, "recall", ["choose a region", "type the API key", "acknowledge the notice"])
        region = ASK("Region [{}]: ".format(suggested)).strip() or suggested
        if region not in recall.REGIONS:
            steps.todo("unknown region {!r}".format(region))
            return EXIT_USAGE
    steps.ok(region)
    steps.step("API key (stored in your OS keychain, or a 0600 file; never in config or logs)")
    new_secrets: Dict[str, str] = {}
    if key:
        steps.ok("an API key is already stored")
    else:
        if not INTERACTIVE():
            return _needs_person(steps, "recall", ["type the API key (hidden input)", "acknowledge the notice"])
        out("    Create a key in the Recall dashboard for region {}.".format(region))
        value = ASK_SECRET("Recall API key (hidden): ").strip()
        if not value:
            steps.todo("no key entered; nothing was stored")
            return EXIT_USAGE
        new_secrets["api_key"] = value
    steps.step("Workspace verification secret (only for the optional webhook listener)")
    if secret:
        steps.ok("already stored")
    elif INTERACTIVE():
        value = ASK_SECRET("Verification secret (hidden; Enter to skip): ").strip()
        if value:
            new_secrets["verification_secret"] = value
        else:
            steps.ok("skipped (polling needs none)")
    else:
        steps.ok("skipped (polling needs none)")
    profile = _recall_profile()
    access.store_identity(profile, "recall", {"region": region}, new_secrets)
    if config.get("region") and config.get("region") != region:
        config["region"] = region  # the choice made now; a stale value would be a region mismatch
    steps.step("Self-test: an authenticated read in {} (no bot is created)".format(region))
    try:
        recall.from_config(config).probe()
    except mc.ProviderAuthError as exc:
        steps.todo("Recall refused the key: {}. Is the key from region {}?".format(exc.message, region))
        return EXIT_AUTH
    except mc.ProviderError as exc:
        steps.todo("Recall could not be reached: " + exc.message)
        return EXIT_NETWORK
    steps.ok("key and region accepted; no bot was created")
    if not INTERACTIVE():
        return _needs_person(steps, "recall", ["acknowledge the cost and data notice"])
    if not _acknowledge(steps, config, "recall"):
        return EXIT_USAGE
    return _finish(steps, config, "recall", not args.no_default)


def _recall_profile() -> str:
    import access

    for name, entry in (access.load_profiles().get("profiles") or {}).items():
        if isinstance(entry, dict) and entry.get("service") == "recall":
            return name
    return "recall"


# ---------------------------------------------------------------------------
# native
# ---------------------------------------------------------------------------
def setup_native(args, config: Dict[str, object]) -> int:
    import access
    import meeting_native as native

    steps = Steps("Set up: native (download the transcript Teams / Meet / Zoom already makes)")
    native_config = dict(config.get("native") or {})  # type: ignore[arg-type]
    steps.step("The organisation's app registration (non-secret; from your admin)")
    if args.import_file:
        try:
            imported = native.parse_import(Path(args.import_file).read_text(encoding="utf-8"))
        except OSError:
            steps.todo("cannot read {}".format(args.import_file))
            return EXIT_USAGE
        except ValueError as exc:
            steps.todo("refused: {}".format(exc))
            return EXIT_USAGE
        for platform, values in imported.items():
            native_config[platform] = values
            steps.ok("imported {} (client id …{})".format(mc.PLATFORM_LABELS[platform], values["client_id"][-4:]))
        config["native"] = native_config
        store.save_config(config)
    configured = [p for p in mc.PLATFORMS if native.platform_config(config, p).get("client_id")]
    if not configured:
        steps.todo("no platform is configured. Ask your admin for the Agent Skills config file, then run:")
        out("        agent-skills meeting setup native --import <file>")
        out("    Admin guides: docs/meeting-intelligence/SETUP-native-teams.md, SETUP-native-google-meet.md,")
        out("                  SETUP-native-zoom.md")
        return EXIT_USAGE
    platforms = [args.platform] if args.platform else configured
    if args.platform and args.platform not in configured:
        steps.todo("{} is not configured; import its config first".format(mc.PLATFORM_LABELS[args.platform]))
        return EXIT_USAGE
    if not INTERACTIVE():
        for platform in platforms:
            state = native.platform_readiness(config, platform)
            out("    {}: {}".format(mc.PLATFORM_LABELS[platform], "ready" if state.ready else state.reason))
        return _needs_person(steps, "native", ["sign in with your browser", "acknowledge the notice"])
    if not _acknowledge(steps, config, "native"):
        return EXIT_USAGE
    store.save_config(config)
    failures = 0
    for platform in platforms:
        label = mc.PLATFORM_LABELS[platform]
        profile = native.profile_name(platform)
        meta = access.identity_metadata(profile)
        if native.CLIENT_SECRET[platform] != "never" and "client_secret" not in (meta.get("secret_fields") or []):
            steps.step("{}: the app's client secret (hidden; distributed like any credential)".format(label))
            value = ASK_SECRET("{} client secret{} (hidden): ".format(
                label, "" if native.CLIENT_SECRET[platform] == "required" else " (Enter if none)")).strip()
            if value:
                access.store_identity(profile, profile, {}, {"client_secret": value})
            elif native.CLIENT_SECRET[platform] == "required":
                steps.todo("{} needs its client secret; skipped".format(label))
                failures += 1
                continue
        steps.step("{}: sign in with your browser (delegated, read-only)".format(label))
        adapter = native.build_adapter(config, platform)
        try:
            client = adapter.oauth_client()
            kwargs = {"announce": out}
            if OPEN_BROWSER is not None:
                kwargs["open_browser"] = OPEN_BROWSER
            tokens = client.sign_in(**kwargs)  # type: ignore[arg-type]
            adapter.store.save(tokens)
            steps.ok("signed in; tokens stored in the credential store")
            steps.step("{}: self-test".format(label))
            adapter._token = None
            steps.ok(adapter.self_test())
        except mc.ProviderError as exc:
            steps.todo("{}: {}".format(label, exc.message))
            failures += 1
    if failures == len(platforms):
        return EXIT_AUTH
    return _finish(steps, config, "native", not args.no_default)


# ---------------------------------------------------------------------------
# desktop
# ---------------------------------------------------------------------------
def setup_desktop(args, config: Dict[str, object]) -> int:
    import meeting_desktop as desktop

    steps = Steps("Set up: desktop (record on this computer, transcribe locally with whisper.cpp)")
    section = dict(config.get("desktop") or {})  # type: ignore[arg-type]
    steps.step("Operating system")
    reason = desktop.unsupported_reason()
    if reason:
        steps.todo(reason + ". Use native or recall instead: agent-skills meeting setup --compare")
        return EXIT_USAGE
    steps.ok(sys.platform)
    steps.step("ffmpeg (records the audio)")
    if not desktop.ffmpeg_path():
        steps.todo("install it: " + desktop.install_hint("ffmpeg") + ", then re-run this setup")
        return EXIT_USAGE
    steps.ok(desktop.ffmpeg_path())
    steps.step("whisper.cpp (whisper-cli, transcribes locally)")
    if not desktop.whisper_path():
        steps.todo("install it: " + desktop.install_hint("whisper") + ", then re-run this setup")
        return EXIT_USAGE
    steps.ok(desktop.whisper_path())
    if args.model:
        if args.model not in desktop.MODELS:
            steps.todo("unknown model {!r}; choose one of {}".format(args.model, ", ".join(desktop.MODELS)))
            return EXIT_USAGE
        section["model"] = args.model
    if args.language:
        section["language"] = args.language.lower()
    config["desktop"] = section
    opts = desktop.settings(config)
    steps.step("Model: ggml-{} ({}), language {}".format(opts["model"], desktop.MODELS[str(opts["model"])][1],
                                                          opts["language"]))
    if desktop.model_verified(str(opts["model"])):
        steps.ok("present and checksum-verified")
    else:
        out("    Downloaded only on your request, from huggingface.co (the whisper.cpp source), and")
        out("    verified against the published checksum. Other sizes: --model " + " | ".join(desktop.MODELS))
        if not INTERACTIVE():
            return _needs_person(steps, "desktop", ["approve the model download", "set up system audio",
                                                     "acknowledge the notice", "run the 5-second self-test"])
        if not _confirm("Download ggml-{}.bin now? [y/N] ".format(opts["model"]), "y"):
            steps.todo("not downloaded; re-run when ready")
            return EXIT_USAGE
        try:
            desktop.download_model(str(opts["model"]), report=lambda t: out("    " + t))
        except (ValueError, OSError) as exc:
            steps.todo(str(exc))
            return EXIT_USAGE
        steps.ok("downloaded and verified")
    steps.step("System audio (what the other participants say)")
    if sys.platform == "darwin":
        devices = desktop.list_audio_devices()
        loopbacks = [name for _, name in devices if desktop.LOOPBACK_NAMES.search(name)]
        if not loopbacks:
            steps.todo("no loopback input found. Install a free virtual audio driver (e.g. BlackHole 2ch),")
            out("        then in Audio MIDI Setup create a Multi-Output Device (your speakers/headphones +")
            out("        BlackHole) and select it as the output, so you still hear the meeting.")
            out("        Step-by-step: docs/meeting-intelligence/SETUP-desktop.md")
            return EXIT_USAGE
        chosen = str(section.get("system_device") or "")
        if chosen not in loopbacks:
            chosen = loopbacks[0]
        section["system_device"] = chosen
        steps.ok("loopback input: " + chosen)
    else:
        steps.ok("PulseAudio/PipeWire: default microphone + the default output's monitor")
    config["desktop"] = section
    if not INTERACTIVE():
        store.save_config(config)
        return _needs_person(steps, "desktop", ["acknowledge the notice", "run the 5-second self-test"])
    if not _acknowledge(steps, config, "desktop"):
        return EXIT_USAGE
    steps.step("Self-test: 5 seconds from both channels, then local transcription")
    out("    Start some audio playing (a video will do) and say a sentence.")
    ASK("Press Enter to record 5 seconds... ")
    try:
        result = desktop.self_test(config, store.home_dir() / "cache" / "desktop-self-test", report=out)
    except (RuntimeError, OSError, mc.ProviderError) as exc:
        steps.todo(str(getattr(exc, "message", exc)))
        return EXIT_USAGE
    out("    microphone level {mic_rms}, system-audio level {system_rms}; recorded in {record_seconds}s, "
        "transcribed in {transcribe_seconds}s".format(**result))
    for label, text in result["texts"].items():
        out("    {}: {}".format(label, text or "(nothing recognised)"))
    silent = [name for name, level in (("microphone", result["mic_rms"]), ("system audio", result["system_rms"]))
              if level < desktop.SIGNAL_FLOOR]
    if silent:
        steps.todo("no signal on: {}. Check the devices (SETUP-desktop.md) and re-run.".format(", ".join(silent)))
        store.save_config(config)
        return EXIT_USAGE
    steps.ok("both channels carry audio; the chain works end to end")
    section["configured_at"] = store.now_iso()
    config["desktop"] = section
    return _finish(steps, config, "desktop", not args.no_default)


# ---------------------------------------------------------------------------
def run(args) -> int:
    config = store.load_config()
    if args.compare:
        out(providers.compare_text(config))
        return EXIT_OK
    provider = args.provider
    if provider is None:
        out(providers.compare_text(config))
        out("")
        if not INTERACTIVE():
            out("Choose one and run it yourself: agent-skills meeting setup native|recall|desktop")
            return EXIT_OK
        provider = ASK("Which provider? [native/recall/desktop]: ").strip().lower()
        if provider not in providers.PROVIDERS:
            out("Nothing chosen; nothing changed.")
            return EXIT_USAGE
    if args.import_file and provider != "native":
        out("--import is for the native provider.")
        return EXIT_USAGE
    return {"recall": setup_recall, "native": setup_native, "desktop": setup_desktop}[provider](args, config)
