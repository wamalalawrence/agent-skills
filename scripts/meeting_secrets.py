#!/usr/bin/env python3
"""Redaction for secrets that were *spoken*, layered on the shared redactor.

`guard_audit.redact()` is the one pattern set every durable tier uses, and it
runs first here too. It recognises secrets that were typed: a token-shaped
string, `password=…`, a URL with credentials. A meeting transcript carries
secrets in shapes no typed pattern matches:

  * **cue + value**: "the staging password is hunter two two"
  * **spelled out**: "it's h u n t e r 2 2", "alpha bravo seven niner"
  * **split across utterances**: "the token is" … (next segment) "g h p …"
  * **a machine token cut in two** by the transcriber's segmentation

These rules live here, not in the shared set, on purpose: adding them there
would move the Execution Guard's false-positive corpus, which the release
checklist treats as a regression. They run only on transcripts and on facts
extracted from them.

The posture is the brief's: **when detection is uncertain, redact.** A lost
word in a transcript costs little; a spoken password in a committed knowledge
file is permanent. Nothing here ever logs, prints, or returns the value it
removed — only a count.
"""
from __future__ import annotations

import re
from typing import Callable, List, Sequence, Tuple

from guard_audit import contains_secret_shape, redact

REDACTED = "[redacted:spoken-secret]"

# Words that announce a secret is about to be said.
_CUE = (
    r"(?:pass(?:word|code|phrase)|pass\s+(?:word|code)|pin(?:\s+code)?|api\s*key|"
    r"access\s+key|secret(?:\s+key)?|private\s+key|token|credentials?|"
    r"connection\s+string|client\s+secret|signing\s+key)"
)
_CUE_RE = re.compile(r"(?i)\b" + _CUE + r"\b")

# "<cue> is|was|:|=|equals|would be|it's <value>"
_CUE_VALUE_RE = re.compile(
    r"(?i)\b(" + _CUE + r")(\s*(?:is|was|=|:|equals|would be|should be|will be|reads)\s+)"
    r"(?!(?:stored|kept|in|at|on|managed|rotated|required|expired|wrong|incorrect|not|"
    r"set|reset|changed|going|being|the same|a secret|in the|also|still|now|fine|"
    r"missing|empty|valid|invalid|there)\b)"
    r"([^.?!]+)"
)

# A cue with nothing after it: the value is in the next utterance.
_TRAILING_CUE_RE = re.compile(
    r"(?i)\b" + _CUE + r"\s*(?:is|was|=|:|equals|would be|it's)?\s*[,:]?\s*$"
)

_SPELL_TOKEN = (
    r"(?:[a-z0-9]|alpha|alfa|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliet|"
    r"juliett|kilo|lima|mike|november|oscar|papa|quebec|romeo|sierra|tango|uniform|"
    r"victor|whiskey|x-ray|xray|yankee|zulu|zero|one|two|three|four|five|six|seven|"
    r"eight|nine|niner|capital|uppercase|lowercase|underscore|dash|hyphen|dot|at|"
    r"hash|dollar|percent|ampersand|exclamation)"
)
_SPELLED_RE = re.compile(
    r"(?i)(?<![\w-])" + _SPELL_TOKEN + r"(?:[\s,.-]+" + _SPELL_TOKEN + r"){%d,}(?![\w-])"
)
# Spoken URL credentials: "postgres colon slash slash admin colon …"
_SPOKEN_URL_RE = re.compile(r"(?i)\bcolon\s+slash\s+slash\b[^.?!]*")

# A word that looks like part of a generated value: letters and digits mixed,
# or mixed case, with no vowels-and-spaces shape of ordinary speech.
_TOKEN_FRAGMENT = re.compile(
    r"^(?=[A-Za-z0-9_\-+/=]{6,}[.,;:!?]?$)(?:(?=\S*\d)(?=\S*[A-Za-z])|(?=\S*[a-z])(?=\S*[A-Z]\S*[A-Z]))\S+$"
)

_SPELLED_WITH_CUE = 4
_SPELLED_ALWAYS = 8
_SPELLED_WITH_CUE_RE = re.compile(_SPELLED_RE.pattern % (_SPELLED_WITH_CUE - 1))
_SPELLED_ALWAYS_RE = re.compile(_SPELLED_RE.pattern % (_SPELLED_ALWAYS - 1))


def _count(pattern: re.Pattern, text: str, replacement: str | Callable) -> Tuple[str, int]:
    out, hits = pattern.subn(replacement, text)
    return out, hits


def redact_text(text: str, cue_nearby: bool = False) -> Tuple[str, int]:
    """Redact one utterance. Returns (text, number of values removed)."""
    if not text:
        return text, 0
    hits = 0
    shared = redact(text)
    if shared != text:
        hits += 1
    out = shared
    out, n = _count(_CUE_VALUE_RE, out, lambda m: m.group(1) + m.group(2) + REDACTED)
    hits += n
    out, n = _count(_SPOKEN_URL_RE, out, REDACTED)
    hits += n
    has_cue = cue_nearby or bool(_CUE_RE.search(text))
    spelled = _SPELLED_WITH_CUE_RE if has_cue else _SPELLED_ALWAYS_RE
    out, n = _count(spelled, out, REDACTED)
    hits += n
    return out, hits


def _redact_head(text: str) -> Tuple[str, int]:
    """Redact the first sentence of an utterance whose value a prior cue announced."""
    if not text.strip():
        return text, 0
    match = re.match(r"\s*([^.?!]+)(.*)", text, re.S)
    if not match or REDACTED in match.group(1):
        return text, 0
    return REDACTED + match.group(2), 1


def redact_segments(
    texts: Sequence[str], speakers: Sequence[str] | None = None
) -> Tuple[List[str], int]:
    """Redact an ordered list of utterances, including secrets split between two.

    `speakers` (same length) narrows the split-token rule to consecutive
    utterances by the same speaker; a cue carries to the next utterance whoever
    speaks it, because "what's the key?" / "it's …" is the common shape.
    """
    out: List[str] = []
    total = 0
    carry_cue = False
    for text in texts:
        cleaned, hits = redact_text(text, cue_nearby=carry_cue)
        if carry_cue:
            cleaned, head_hits = _redact_head(cleaned)
            hits += head_hits
        total += hits
        out.append(cleaned)
        carry_cue = bool(_TRAILING_CUE_RE.search(text)) or bool(
            _CUE_RE.search(text) and text.rstrip().endswith("?")
        )

    # A machine-shaped token the transcriber cut across two utterances: neither
    # half is secret-shaped alone, the join is. Remove the tail and head words.
    # And once a value has been redacted, a token-shaped fragment opening the
    # same speaker's next utterance is its continuation, not new speech.
    for index in range(len(out) - 1):
        if speakers is not None and speakers[index] != speakers[index + 1]:
            continue
        left, right = out[index].rstrip(), out[index + 1].lstrip()
        if not left or not right:
            continue
        left_word = left.split()[-1]
        right_word = right.split()[0]
        if REDACTED in right_word:
            continue
        if REDACTED in left_word:
            if _TOKEN_FRAGMENT.match(right_word):
                out[index + 1] = REDACTED + right[len(right_word):]
                total += 1
            continue
        joined = left_word + right_word
        if contains_secret_shape(joined) and not contains_secret_shape(left_word) \
                and not contains_secret_shape(right_word):
            out[index] = left[: len(left) - len(left_word)] + REDACTED
            out[index + 1] = REDACTED + right[len(right_word):]
            total += 1
    return out, total
