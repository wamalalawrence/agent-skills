#!/usr/bin/env python3
"""Fail-closed sanitisation helpers for lifecycle output and persistence boundaries."""
from __future__ import annotations

import re
import sys
from typing import Any

_PATTERNS = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "pem-private-key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
            r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    (
        "url-credentials",
        re.compile(r"(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@[^\s/]+"),
    ),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "bearer-token",
        re.compile(
            r"(?i)\b(?:bearer|authorization:\s*bearer)\s+"
            r"[A-Za-z0-9._~+/=-]{16,}"
        ),
    ),
    (
        "keyed-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd|"
            r"client[_-]?secret)\b\s*[:=]\s*[^\s,;]{8,}"
        ),
    ),
)


def redact_text(value: str) -> str:
    """Redact credential-shaped substrings without retaining the original value."""
    clean = value
    for kind, pattern in _PATTERNS:
        clean = pattern.sub(f"[REDACTED:{kind}]", clean)
    return clean


def redact_boundary(value: Any) -> Any:
    """Recursively sanitise JSON-compatible data before dispatch, output, or storage."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact_text(str(key)): redact_boundary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_boundary(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_boundary(item) for item in value)
    return value


if __name__ == "__main__":
    sys.stdout.write(redact_text(sys.stdin.read()))
