#!/usr/bin/env python3
"""Redaction and the local decision log for Execution Guard.

Two obligations meet here, and they pull against each other.

The guard must be **auditable**: when something is blocked, the operator needs
to know what was blocked, by which rule, in which directory, and when. Without
that, a denial is indistinguishable from a bug and the guard gets switched off.

The guard must also **not become the leak**. The commands it inspects are
exactly the ones most likely to carry a secret: an `Authorization` header on a
`curl`, a database URL with an inline password, an `--sse-c-key` on an object
copy, a signed URL with its signature in the query string. Writing those
verbatim into a log file would create a plaintext credential store that nobody
knows exists, populated automatically, on the machine of every user who
installed a security tool.

So nothing here stores a raw command. What is stored is:

    rule | classification | redacted target | command fingerprint | cwd | time

The fingerprint is a SHA-256 prefix of the **redacted** command, which is
enough to recognise the same command recurring and useless for recovering it.

The log is local, append-only, `0600`, and bounded. It is never uploaded, and
nothing in this repository reads it over a network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REDACTED = "[redacted]"

# Ordered most specific first: a bearer token should be recognised as a header
# value before the generic long-random-string rule reaches it.
_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"""(?i)(authorization\s*:\s*)(?:bearer|basic|token)\s+[^\s"']+"""),
        r"\1" + REDACTED,
    ),
    # The same header as a JSON member, which is how an MCP config or an HTTP
    # client's debug dump prints it: `"Authorization": "Bearer <token>"`.
    (
        re.compile(r"""(?i)("authorization"\s*:\s*")(?:bearer|basic|token)\s+[^"]+(")"""),
        r"\1" + REDACTED + r"\2",
    ),
    (re.compile(r"""(?i)(x-api-key\s*:\s*)[^\s"']+"""), r"\1" + REDACTED),
    (
        re.compile(
            r"(?i)\b(private-token|api[_-]?key|apikey|access[_-]?token|auth[_-]?token)"
            r"(\s*[:=]\s*)\S+"
        ),
        r"\1\2" + REDACTED,
    ),
    # PROBE_ANCHOR_CREDENTIAL_ASSIGNMENT
    (
        re.compile(
            r"(?i)(^|\s)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|"
            r"ACCESS_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*)=[^\s]+"
        ),
        r"\1\2=" + REDACTED,
    ),
    # `MYSQL_PWD`, `DB_PASS`, `PGPASS` — the abbreviated spellings the database
    # clients actually use. A leading segment plus `_` is required so the
    # shell's own `PWD=` is left alone; redacting the working directory out of
    # an audit line would make it unreadable to buy nothing.
    #
    # `\d` rather than `0-9`, for the same reason as the URL rule below: the
    # literal class `A-Z0-9` contains the substring `Z0-9`, which this
    # repository's own ticket-key scanner reads as a ticket reference.
    (
        re.compile(r"(?i)(^|\s)([A-Z\d]+(?:_[A-Z\d]+)*_(?:PWD|PASS))=[^\s]+"),
        r"\1\2=" + REDACTED,
    ),
    # A quoted value under a credential-shaped key, which is how an API response,
    # a config dump, or `psql -A --json` prints one.
    # PROBE_ANCHOR_JSON_CREDENTIAL_KEY
    (
        re.compile(
            r"""(?i)("[A-Za-z\d_.\-]*"""
            r"""(?:password|passwd|secret|token|api[_-]?key|credential|private[_-]?key)"""
            r"""[A-Za-z\d_.\-]*"\s*:\s*")[^"]*(")"""
        ),
        r"\1" + REDACTED + r"\2",
    ),
    # `password: "value"` and `db_password = 'value'`. The unquoted rule below
    # stops at the first quote character, so the quoted spellings — which are the
    # ones a YAML file, a `.env`, and a config dump actually use — passed
    # straight through it.
    # PROBE_ANCHOR_QUOTED_CREDENTIAL_VALUE
    (
        re.compile(
            r"(?i)\b((?:[a-z\d]+[_.\-])*(?:password|passwd|secret)s?)"
            r"""(\s*[:=]\s*)(["'])[^"'\n]*(["'])"""
        ),
        r"\1\2\3" + REDACTED + r"\4",
    ),
    # `password: value` and `db_password = value`. The rule above this one only
    # covers `=`, which left the YAML and libpq spellings intact.
    (
        re.compile(
            r"(?i)\b((?:[a-z\d]+[_.\-])*(?:password|passwd|secret)s?)"
            r"""(\s*[:=]\s*)(?!\s)([^\s,;"']+)"""
        ),
        r"\1\2" + REDACTED,
    ),
    # `mysql -u root -phunter2` — the attached short flag. Anchored to the mysql
    # client family because a bare `-p` means something different almost
    # everywhere else (`mkdir -p`, `grep -p`, `ssh -p 22`).
    #
    # `mariadb` is the same client under its current name and takes the same
    # flag; on a machine where `mysql` is a symlink to it, the name in the log is
    # whichever one the operator typed.
    # PROBE_ANCHOR_ATTACHED_PASSWORD_FLAG
    (
        re.compile(
            r"(?i)\b((?:mysql|mariadb)(?:dump|admin|sh|_config|-dump|-admin|-check)?"
            r"\b[^\n]*?\s-p)(?!\s)[^\s]+"
        ),
        r"\1" + REDACTED,
    ),
    (
        re.compile(
            r"(?i)(--(?:password|token|secret|api-key|access-key|client-secret|"
            r"sse-c-key)[= ])\S+"
        ),
        r"\1" + REDACTED,
    ),
    # Any scheme://user:secret@host form, whatever the scheme is.
    (
        # \d rather than 0-9: the literal class `a-zA-Z0-9+.-` contains the
        # substring `Z0-9-`, which the repository's own ticket-key scanner reads
        # as a ticket reference and warns about.
        re.compile(r"\b([a-zA-Z][a-zA-Z\d+.-]*://)([^/\s:@]+):([^/\s@]+)@"),
        r"\1\2:" + REDACTED + "@",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), REDACTED),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), REDACTED),
    # Atlassian API tokens (`ATATT...`) and Connect/Forge tokens (`ATCTT...`).
    # Caught before by the high-entropy rule only when long and mixed enough;
    # a truncated one in a log line slipped through.
    (re.compile(r"\bAT[AC]TT[A-Za-z0-9_=\-]{8,}"), REDACTED),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),
        REDACTED,
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        REDACTED,
    ),
    (
        re.compile(
            r"(?i)([?&](?:token|key|signature|sig|password|access_key|"
            r"x-amz-signature|se|sp|sv)=)[^&\s\"']+"
        ),
        r"\1" + REDACTED,
    ),
    # Prose: "connection failed using password hunter2Xy9q against db.internal".
    # A client that reports its own failure this way is exactly the shape that
    # leaked in the field, and none of the key=value rules above see it.
    #
    # Deliberately narrow, because this one has real false-positive potential.
    # The candidate must be at least eight characters and contain a digit, which
    # keeps "password rotation is due", "password field is required", and
    # "password expires in 30 days" intact while catching a generated value.
    (
        re.compile(r"(?i)\b(password|passwd)(\s+)(?=\S*\d)\S{8,}"),
        r"\1\2" + REDACTED,
    ),
)

# Long opaque strings that survive the specific rules above. Deliberately last,
# and deliberately narrow: a 32-character path component is common, a
# 32-character mixed-case-and-digit blob is not.
_HIGH_ENTROPY = re.compile(
    r"(?i)(?<![\w/.-])(?=[A-Za-z0-9+/_=-]{32,})(?=[^\s]*[A-Z])(?=[^\s]*[0-9])"
    r"[A-Za-z0-9+/_=-]{32,}(?![\w/.-])"
)


def redact(text: str) -> str:
    """Remove credential-shaped values from a string, keeping its shape.

    Structure is preserved on purpose. A record that still reads as a `curl` to
    a known host, with the header value gone, is a useful audit line; an opaque
    hash is not.
    """
    if not text:
        return text
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    out = _HIGH_ENTROPY.sub(REDACTED, out)
    return out


def contains_secret_shape(text: str) -> bool:
    """Whether redaction would change this text — used by tests and scanners."""
    return redact(text) != text


def fingerprint(command: str) -> str:
    """A stable, non-reversible identifier for a command.

    Computed over the redacted, whitespace-normalised form, so the same command
    with a different token still fingerprints the same and neither form can be
    recovered from the digest.
    """
    normalised = " ".join(redact(command or "").split())
    digest = hashlib.sha256(normalised.encode("utf-8", "replace")).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# The log
# ---------------------------------------------------------------------------
MAX_RECORDS = 5000


def audit_path(config_dir: str) -> Path:
    return Path(config_dir) / "guard" / "decisions.ndjson"


def _trim(path: Path) -> None:
    """Bound the log. Retention is a fixed record count, documented, and local."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_RECORDS:
        return
    keep = lines[-MAX_RECORDS:]
    tmp = path.with_suffix(".ndjson.tmp")
    try:
        tmp.write_text("\n".join(keep) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    except OSError:
        pass


def record(config_dir: str, entry: dict, mode: str = "decisions") -> Path | None:
    """Append one decision. Returns the log path, or None when disabled.

    `mode` is `decisions` (ASK and DENY only, the default), `all`, or `off`.
    Recording every ALLOW on every shell command would make the log enormous and
    slow the hot path for no security benefit, so it is opt-in.
    """
    if mode == "off":
        return None
    if mode != "all" and entry.get("decision") == "ALLOW":
        return None
    path = audit_path(config_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    except OSError:
        return None

    payload = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": entry.get("host", "cli"),
        "kind": entry.get("kind", "shell"),
        "decision": entry.get("decision", "ALLOW"),
        "rule": entry.get("rule"),
        "category": entry.get("category"),
        "cwd": entry.get("cwd"),
        "target": entry.get("target"),
        "fingerprint": entry.get("fingerprint"),
        "guard_version": entry.get("guard_version"),
    }
    # Defence in depth against a future caller passing something raw: every
    # string value goes through redaction on the way out, not just the ones
    # believed to be risky.
    for key, value in list(payload.items()):
        if isinstance(value, str):
            payload[key] = redact(value)

    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
        os.chmod(path, 0o600)
    except OSError:
        return None
    _trim(path)
    return path


def read_tail(config_dir: str, count: int = 20) -> list[dict]:
    path = audit_path(config_dir)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-count:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def clear(config_dir: str) -> bool:
    path = audit_path(config_dir)
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
