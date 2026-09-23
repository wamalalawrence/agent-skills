#!/usr/bin/env python3
"""Delegated OAuth for the native transcript provider: authorization code + PKCE.

One flow for Microsoft Entra, Google, and Zoom, because they differ only in
URLs, scopes, and whether the token endpoint wants a client secret:

    browser  ── authorize?client_id&code_challenge(S256)&state ──▶  identity provider
    loopback ◀── redirect ?code&state ── (a one-shot listener on 127.0.0.1)
    here     ── token (code + code_verifier) ──▶  access + refresh token

Rules this module keeps:

  * The user signs in, in their own browser. Nothing here types a password,
    answers a consent screen, or runs without a person at the keyboard: the
    caller refuses to start a sign-in without an interactive terminal.
  * Tokens are delegated: the app can read only what the signed-in user can.
  * The refresh token (and the short-lived access token) go only into the
    Access Resolver's credential store, the same one `access set` writes: OS
    keychain, else a 0600 file under ~/.config/agent-skills/secrets/. Never
    into meeting state, logs, argv, or a config file meant for sharing.
  * `state` is checked, the code verifier never leaves this process except to
    the token endpoint, and the listener binds loopback only.
  * A rotated refresh token replaces the old one at once. `invalid_grant` marks
    the identity expired so readiness can say "sign in again" instead of
    failing mysteriously on the next meeting.

Standard library only.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import meeting_capture as mc
import meeting_http

SIGN_IN_TIMEOUT_SECONDS = 300
EXPIRY_SKEW_SECONDS = 120
OAUTH_BASE_ENV = "AGENT_SKILLS_MEETING_OAUTH_BASE_URL"


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pkce_pair() -> tuple:
    """(verifier, S256 challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _rebase(url: str) -> str:
    """Point an identity-provider URL at the offline harness, loopback only."""
    override = meeting_http.base_override(OAUTH_BASE_ENV, ())
    if not override:
        return url
    base, target = urlsplit(override), urlsplit(url)
    return urlunsplit((base.scheme, base.netloc, base.path.rstrip("/") + target.path, target.query, ""))


class OAuthClient:
    def __init__(
        self,
        label: str,
        authorize_url: str,
        token_url: str,
        client_id: str,
        scopes: str,
        redirect_uri: str,
        client_secret: str = "",
        secret_in_basic_auth: bool = False,
        extra_authorize: Optional[Dict[str, str]] = None,
        transport: Optional[meeting_http.Transport] = None,
    ) -> None:
        parts = urlsplit(redirect_uri)
        if parts.scheme != "http" or (parts.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
            raise mc.ProviderRequestError("the redirect URI must be an http loopback address")
        self.label = label
        self.authorize_url = _rebase(authorize_url)
        self.token_url = _rebase(token_url)
        self.client_id = client_id
        self.scopes = scopes
        self.redirect_uri = redirect_uri
        self._client_secret = client_secret
        self._basic = secret_in_basic_auth
        self.extra_authorize = dict(extra_authorize or {})
        self._transport = transport or meeting_http.make_transport(label + " sign-in")

    # ---- the browser step -------------------------------------------------------
    def sign_in(self, open_browser: Callable[[str], object] = webbrowser.open,
                timeout: float = SIGN_IN_TIMEOUT_SECONDS, announce: Callable[[str], None] = print) -> dict:
        """Run the loopback flow once. Returns the token response (dict)."""
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        parts = urlsplit(self.redirect_uri)
        box: Dict[str, str] = {}
        done = threading.Event()
        path = parts.path or "/"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                request = urlsplit(self.path)
                if request.path != path:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(request.query)
                if not done.is_set():
                    box["code"] = (query.get("code") or [""])[0]
                    box["state"] = (query.get("state") or [""])[0]
                    box["error"] = (query.get("error") or [""])[0][:64]
                    done.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><p>Agent Skills: sign-in received. "
                                 b"You can close this window.</p></body></html>")

            def log_message(self, *_args) -> None:  # the query holds the code; never log it
                return

        server = HTTPServer(("127.0.0.1", parts.port or 0), Handler)
        port = server.server_address[1]
        redirect = urlunsplit(("http", "{}:{}".format(parts.hostname, port), path, "", ""))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        thread.start()
        try:
            params = {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": redirect,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            if self.scopes:
                params["scope"] = self.scopes
            params.update(self.extra_authorize)
            url = self.authorize_url + ("&" if "?" in self.authorize_url else "?") + urlencode(params)
            announce("Opening your browser to sign in to {}. If it does not open, visit:\n  {}".format(
                self.label, url))
            open_browser(url)
            if not done.wait(timeout):
                raise mc.ProviderAuthError("sign-in to {} timed out; nothing was stored".format(self.label))
        finally:
            server.shutdown()
            server.server_close()
        if box.get("error"):
            raise mc.ProviderAuthError("{} refused the sign-in ({})".format(self.label, box["error"]))
        if not box.get("code") or not secrets.compare_digest(box.get("state", ""), state):
            raise mc.ProviderAuthError("the sign-in response did not match this request; nothing was stored")
        return self._token({
            "grant_type": "authorization_code",
            "code": box["code"],
            "redirect_uri": redirect,
            "code_verifier": verifier,
        })

    # ---- the token endpoint -----------------------------------------------------
    def refresh(self, refresh_token: str) -> dict:
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        if self.scopes:
            data["scope"] = self.scopes
        return self._token(data)

    def _token(self, form: Dict[str, str]) -> dict:
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                   "User-Agent": "agent-skills-meeting"}
        form = dict(form)
        if self._basic:
            raw = "{}:{}".format(self.client_id, self._client_secret).encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        else:
            form["client_id"] = self.client_id
            if self._client_secret:
                form["client_secret"] = self._client_secret
        status, body = self._transport("POST", self.token_url, headers, urlencode(form).encode("utf-8"))
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
            payload = {}
        if status >= 500 or status == 429:
            raise mc.ProviderNetworkError("{} sign-in service is unavailable (HTTP {})".format(self.label, status))
        if status >= 400 or not isinstance(payload, dict) or not payload.get("access_token"):
            error = str(payload.get("error", "")) if isinstance(payload, dict) else ""
            if error == "invalid_grant":
                raise ExpiredGrant("{} sign-in has expired or was revoked".format(self.label))
            raise mc.ProviderAuthError("{} refused the token request ({})".format(
                self.label, error[:40] or "HTTP {}".format(status)))
        return payload


class ExpiredGrant(mc.ProviderAuthError):
    """The refresh token no longer works: the user must sign in again."""


class TokenStore:
    """One platform's tokens in the Access Resolver's credential store."""

    SECRET_FIELDS = ("refresh_token", "access_token")

    def __init__(self, profile: str, service: str) -> None:
        self.profile = profile
        self.service = service

    def metadata(self) -> dict:
        import access

        return access.identity_metadata(self.profile)

    def signed_in(self) -> bool:
        return "refresh_token" in (self.metadata().get("secret_fields") or [])

    def auth_state(self) -> str:
        return str((self.metadata().get("fields") or {}).get("auth_state", ""))

    def save(self, tokens: dict, account: str = "") -> None:
        import access

        now = _now()
        secrets_out = {"access_token": str(tokens["access_token"])}
        if tokens.get("refresh_token"):
            secrets_out["refresh_token"] = str(tokens["refresh_token"])
        expires = now + max(60, int(tokens.get("expires_in") or 3600))
        plain = {"access_expires_at": _iso(expires), "auth_state": "ok", "refreshed_at": _iso(now)}
        if account:
            plain["account"] = account[:120]
        access.store_identity(self.profile, self.service, plain, secrets_out)

    def mark_expired(self) -> None:
        import access

        access.store_identity(self.profile, self.service, {"auth_state": "expired"}, {})

    def load(self) -> dict:
        import access

        try:
            return access.fetch_identity(self.profile, ["refresh_token", "access_token", "access_expires_at"])
        except access.BackendError as exc:
            raise mc.ProviderAuthError(str(exc)) from None

    def access_token(self, client: OAuthClient, fix_command: str) -> str:
        """A valid access token, refreshing (and rotating) when needed."""
        stored = self.load()
        expires = stored.get("access_expires_at", "")
        try:
            expires_ts = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            expires_ts = 0.0
        if stored.get("access_token") and expires_ts - EXPIRY_SKEW_SECONDS > _now():
            return stored["access_token"]
        if not stored.get("refresh_token"):
            raise mc.ProviderAuthError("not signed in to {}; run: {}".format(client.label, fix_command))
        try:
            tokens = client.refresh(stored["refresh_token"])
        except ExpiredGrant:
            self.mark_expired()
            raise mc.ProviderAuthError("{} sign-in has expired; run: {}".format(client.label, fix_command)) from None
        self.save(tokens)
        return str(tokens["access_token"])
