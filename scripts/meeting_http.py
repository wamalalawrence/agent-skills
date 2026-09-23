#!/usr/bin/env python3
"""HTTPS plumbing shared by the meeting capture providers.

Every provider that talks to an API (Recall, Microsoft Graph, Google Meet,
Zoom, and the OAuth token endpoints) goes through here, so the rules are
written once:

  * certificate verification stays on (`ssl.create_default_context()`);
  * a redirect never carries `Authorization` to another host, and an https to
    http downgrade is refused;
  * responses are size-bounded, and an exception text (which can carry a URL
    with a token in it) is never kept;
  * a transport is injectable, so the test suite replays recorded fixtures and
    never opens a connection.

A base-URL override exists only for the offline test harness, and it may point
at loopback or at the provider's own domain, nothing else: the override decides
where a credential is sent.

Standard library only, like the rest of the runtime.
"""
from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

import meeting_capture as mc

MAX_RESPONSE_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 20

# (method, url, headers, body) -> (status, body)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes]]


class CredentialSafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects without carrying a credential anywhere it was not sent.

    urllib's default handler copies every non-content header onto the
    redirected request, `Authorization` included, whatever host the redirect
    points at. So a cross-host hop drops the header, and a downgrade from https
    to http is refused outright.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib API
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and (new.hostname or "").lower() != (old.hostname or "").lower():
            for name in list(redirected.headers):
                if name.lower() == "authorization":
                    del redirected.headers[name]
            redirected.unredirected_hdrs.pop("Authorization", None)
        return redirected


def make_transport(label: str) -> Transport:
    """A real HTTPS transport whose network failures name `label`, nothing more."""

    def transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes]) -> Tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        context = ssl.create_default_context()  # certificate verification stays on
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), CredentialSafeRedirect()
        )
        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                data = exc.read(64 * 1024)
            except OSError:
                data = b""
            return exc.code, data
        except (urllib.error.URLError, OSError, ValueError):
            # The exception text can carry the URL; it is deliberately not kept.
            raise mc.ProviderNetworkError("{} could not be reached".format(label)) from None

    return transport


def base_override(env_name: str, allowed_suffixes: Tuple[str, ...]) -> str:
    """An env base-URL override, validated. Empty when unset.

    Allowed: http(s) on loopback (the offline harness), or https on a host
    ending in one of `allowed_suffixes`. Anything else is refused, because the
    override decides where a credential is sent.
    """
    override = os.environ.get(env_name, "").strip().rstrip("/")
    if not override:
        return ""
    parts = urlsplit(override)
    host = (parts.hostname or "").lower()
    loopback = parts.scheme in ("http", "https") and host in ("127.0.0.1", "localhost", "::1")
    trusted = parts.scheme == "https" and any(host == s.lstrip(".") or host.endswith(s) for s in allowed_suffixes)
    if not (loopback or trusted) or parts.username or parts.password:
        raise mc.ProviderRequestError(
            "{} must be an https URL on {} or loopback".format(env_name, " / ".join(allowed_suffixes))
        )
    return override


def is_loopback(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() in ("127.0.0.1", "localhost", "::1")
