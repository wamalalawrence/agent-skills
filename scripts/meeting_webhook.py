#!/usr/bin/env python3
"""Optional webhook listener for `agent-skills meeting status --listen`.

Polling is the lifecycle channel; this is only an accelerator for a user who
has their own stable public URL (a tunnel, or a host they operate) pointed at
this loopback listener. A missed webhook is always recovered by the next poll.

Every request is handled in this order, and nothing later runs unless the step
before it passed:

  1. size-bounded read of the raw body (1 MB)
  2. provider signature verification over the raw bytes, constant-time, with a
     signed-timestamp tolerance window — before the body is parsed
  3. dedupe on the provider's event id (a duplicate is acknowledged, ignored)
  4. acknowledge immediately; the event goes on a queue, and a worker runs the
     ordinary reconciler for the correlated meeting

The event body is never trusted for state. It says "look at this meeting now";
the reconciler asks the provider what is actually true. So a replayed, stale,
duplicated, or out-of-order event cannot move a meeting backwards.

Nothing here logs a header, a signature, a secret, or a body.
"""
from __future__ import annotations

import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

import meeting_capture as mc
import meeting_store as store


def make_handler(
    path: str,
    provider: mc.MeetingCaptureProvider,
    enqueue: Callable[[mc.ProviderEvent], None],
    max_bytes: int,
    counter: dict,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "agent-skills-meeting"
        sys_version = ""

        def _reply(self, code: int, outcome: str) -> None:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
            sys.stderr.write("webhook {}\n".format(outcome))
            counter["handled"] = counter.get("handled", 0) + 1

        def do_POST(self) -> None:  # noqa: N802 - http.server naming
            if self.path.split("?", 1)[0] != path:
                self._reply(404, "ignored: unknown path")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > max_bytes:
                self._reply(413, "rejected: size")
                return
            body = self.rfile.read(length)
            headers = {key: value for key, value in self.headers.items()}
            event = provider.verify_event(headers, body, time.time())
            if event is None:
                self._reply(401, "rejected: not verified")
                return
            if not store.remember_event(event.event_id):
                self._reply(200, "duplicate: ignored")
                return
            enqueue(event)
            self._reply(202, "accepted")

        def do_GET(self) -> None:  # noqa: N802
            self._reply(405, "ignored: method")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # the default logger prints request lines; nothing is logged here

    return Handler


def serve(
    host: str,
    port: int,
    path: str,
    provider: mc.MeetingCaptureProvider,
    enqueue: Callable[[mc.ProviderEvent], None],
    max_bytes: int,
    max_events: Optional[int] = None,
    ready: Optional[Callable[[int], None]] = None,
) -> None:
    counter: dict = {}
    server = ThreadingHTTPServer((host, port), make_handler(path, provider, enqueue, max_bytes, counter))
    server.timeout = 0.5
    if ready is not None:
        ready(server.server_address[1])
    try:
        while max_events is None or counter.get("handled", 0) < max_events:
            server.handle_request()
    finally:
        server.server_close()
