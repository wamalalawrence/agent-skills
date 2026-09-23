#!/usr/bin/env python3
"""The part of TOML that a host's MCP server table uses, and nothing more.

Codex keeps its MCP servers in `~/.codex/config.toml`. Python 3.11 ships
`tomllib`; the runtime baseline is 3.8, so without this module Codex would be
the one host whose routes Access Discovery could not see.

Supported: `[table]` and `[dotted."quoted".table]` headers, `key = value` with
bare, quoted, and dotted keys, basic and literal strings (single line),
integers, floats, booleans, arrays (which may span lines), and inline tables.
Everything else - multi-line strings, dates, arrays of tables - raises
`TomlSubsetError`, and the caller reports the host as `unknown`. A config this
parser cannot read is never treated as "no servers": that would turn a parse
gap into a false `pass` on the absence of a read-only setting.

`tomllib` is used when it exists, so the subset parser only has to be right on
the machines that need it.
"""
from __future__ import annotations

import re

try:  # pragma: no cover - exercised only on 3.11+
    import tomllib as _tomllib  # type: ignore
except ImportError:  # Python 3.8 - 3.10
    _tomllib = None


class TomlSubsetError(ValueError):
    pass


_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_NUMBER = re.compile(r"[+-]?(?:\d[\d_]*)(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f"}


def loads(text: str, force_subset: bool = False) -> dict:
    if _tomllib is not None and not force_subset:
        try:
            return _tomllib.loads(text)
        except Exception as exc:  # noqa: BLE001 - normalise to one error type
            raise TomlSubsetError(str(exc))
    return _Parser(text).parse()


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1

    # -- low level ---------------------------------------------------------
    def error(self, message: str):
        raise TomlSubsetError("line %d: %s" % (self.line, message))

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def advance(self, count: int = 1) -> None:
        for _ in range(count):
            if self.peek() == "\n":
                self.line += 1
            self.pos += 1

    def skip_ws(self, newlines: bool = False) -> None:
        while True:
            ch = self.peek()
            if ch in (" ", "\t", "\r") or (newlines and ch == "\n"):
                self.advance()
            elif ch == "#":
                while self.peek() not in ("", "\n"):
                    self.advance()
            else:
                return

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            self.error("expected %r" % ch)
        self.advance()

    # -- structure ---------------------------------------------------------
    def parse(self) -> dict:
        root: dict = {}
        current = root
        while True:
            self.skip_ws(newlines=True)
            if self.pos >= len(self.text):
                return root
            if self.peek() == "[":
                self.advance()
                if self.peek() == "[":
                    self.error("arrays of tables are outside the supported subset")
                self.skip_ws()
                path = self.key_path()
                self.skip_ws()
                self.expect("]")
                current = root
                for part in path:
                    nxt = current.setdefault(part, {})
                    if not isinstance(nxt, dict):
                        self.error("table %r redefines a value" % ".".join(path))
                    current = nxt
            else:
                path = self.key_path()
                self.skip_ws()
                self.expect("=")
                self.skip_ws()
                value = self.value()
                self.assign(current, path, value)
            self.skip_ws()
            if self.peek() not in ("", "\n"):
                self.error("unexpected text after value")

    def assign(self, table: dict, path: list, value) -> None:
        for part in path[:-1]:
            table = table.setdefault(part, {})
            if not isinstance(table, dict):
                self.error("dotted key crosses a value")
        if path[-1] in table:
            self.error("duplicate key %r" % path[-1])
        table[path[-1]] = value

    def key_path(self) -> list:
        parts = [self.key()]
        while True:
            self.skip_ws()
            if self.peek() != ".":
                return parts
            self.advance()
            self.skip_ws()
            parts.append(self.key())

    def key(self) -> str:
        ch = self.peek()
        if ch == '"':
            return self.basic_string()
        if ch == "'":
            return self.literal_string()
        match = _BARE_KEY.match(self.text, self.pos)
        if not match:
            self.error("expected a key")
        self.advance(match.end() - self.pos)
        return match.group(0)

    # -- values ------------------------------------------------------------
    def value(self):
        ch = self.peek()
        if self.text.startswith('"""', self.pos) or self.text.startswith("'''", self.pos):
            self.error("multi-line strings are outside the supported subset")
        if ch == '"':
            return self.basic_string()
        if ch == "'":
            return self.literal_string()
        if ch == "[":
            return self.array()
        if ch == "{":
            return self.inline_table()
        for word, result in (("true", True), ("false", False)):
            if self.text.startswith(word, self.pos):
                self.advance(len(word))
                return result
        match = _NUMBER.match(self.text, self.pos)
        if match and match.group(0):
            raw = match.group(0).replace("_", "")
            self.advance(match.end() - self.pos)
            if self.peek() and self.peek() not in " \t\r\n,]}#":
                self.error("unsupported value (dates and special floats are outside the subset)")
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        self.error("unsupported value")

    def basic_string(self) -> str:
        self.expect('"')
        out = []
        while True:
            ch = self.peek()
            if ch in ("", "\n"):
                self.error("unterminated string")
            self.advance()
            if ch == '"':
                return "".join(out)
            if ch == "\\":
                esc = self.peek()
                self.advance()
                if esc in _ESCAPES:
                    out.append(_ESCAPES[esc])
                elif esc in ("u", "U"):
                    width = 4 if esc == "u" else 8
                    digits = self.text[self.pos:self.pos + width]
                    if not re.fullmatch(r"[0-9A-Fa-f]{%d}" % width, digits):
                        self.error("bad unicode escape")
                    out.append(chr(int(digits, 16)))
                    self.advance(width)
                else:
                    self.error("bad escape")
            else:
                out.append(ch)

    def literal_string(self) -> str:
        self.expect("'")
        start = self.pos
        while self.peek() not in ("'", "\n", ""):
            self.advance()
        if self.peek() != "'":
            self.error("unterminated literal string")
        value = self.text[start:self.pos]
        self.advance()
        return value

    def array(self) -> list:
        self.expect("[")
        items = []
        while True:
            self.skip_ws(newlines=True)
            if self.peek() == "]":
                self.advance()
                return items
            items.append(self.value())
            self.skip_ws(newlines=True)
            if self.peek() == ",":
                self.advance()
                continue
            self.skip_ws(newlines=True)
            if self.peek() != "]":
                self.error("expected ',' or ']' in array")

    def inline_table(self) -> dict:
        self.expect("{")
        table: dict = {}
        self.skip_ws()
        if self.peek() == "}":
            self.advance()
            return table
        while True:
            self.skip_ws()
            path = self.key_path()
            self.skip_ws()
            self.expect("=")
            self.skip_ws()
            self.assign(table, path, self.value())
            self.skip_ws()
            if self.peek() == ",":
                self.advance()
                continue
            if self.peek() == "}":
                self.advance()
                return table
            self.error("expected ',' or '}' in inline table")


def dump_string(value: str) -> str:
    """Render a TOML basic string. Used by `access setup` for Codex."""
    out = ['"']
    for ch in value:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dump_key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else dump_string(key)
