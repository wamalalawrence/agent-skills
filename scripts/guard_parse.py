#!/usr/bin/env python3
"""Shell command decomposition for Execution Guard.

The guard's blocking decision is only as good as its view of what will actually
run. A rule that reads `command.startswith("rm -rf")` is defeated by
`true && rm -rf /`, by `$(rm -rf /)`, by `X=1 rm -rf /`, and by
`bash -c 'rm -rf /'`. So the first thing the engine does is stop treating the
command as a string and turn it into the set of simple commands the shell would
actually execute.

What this module produces, from one command line:

    ParsedCommand
      .pipelines -> [Pipeline]        every pipeline the shell would run
      .commands  -> [SimpleCommand]   every simple command, flattened
      .unparsed  -> bool              the parse is incomplete or failed
      .notes     -> [str]             why, in the operator's language

`unparsed` is the load-bearing field. A parser that silently returns an empty
command list on malformed input would make every rule pass, and the caller would
read that as ALLOW. Callers must treat `unparsed` as "assume the worst"; see
`guard.py` for the conservative resolution.

Coverage, in the order an attacker reaches for them:

  * operators                `&&`  `||`  `;`  `&`  newline
  * pipelines                `a | b`, `a |& b`  (kept as one Pipeline so
                             download-and-execute is visible)
  * command substitution     `$( ... )` and `` ` ... ` ``, recursively
  * process substitution     `<( ... )` and `>( ... )`
  * grouping                 `( ... )` and `{ ...; }`
  * env assignment prefixes  `FOO=bar cmd`, `env FOO=bar cmd`
  * transparent wrappers     `sudo`, `nohup`, `time`, `nice`, `command`, `exec`,
                             `doas`, `stdbuf`, `timeout`, `xargs`, `watch`
  * nested shells            `bash -c '...'`, `sh -c`, `zsh -c`, `ssh host '...'`
  * `find ... -exec CMD ;`   the inner command is extracted and re-parsed
  * redirections             targets are captured, so `> /etc/hosts` is visible

Deliberately NOT attempted: expanding globs (that would touch the filesystem),
expanding arbitrary variables, resolving aliases and shell functions (they are
not knowable from the string), or interpreting the body of `python -c`. Each of
those is reported as an unresolved element rather than guessed at, and the rules
decide what an unresolved element is worth.

Bash 3.2-era syntax is the target: this must describe what `/bin/sh`, `bash`,
and `zsh` do with the string, not what a full grammar would prefer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Recursion and size ceilings. This runs before every shell command, so a
# pathological input must cost a bounded amount rather than a stack.
MAX_DEPTH = 8
MAX_COMMANDS = 400
MAX_INPUT_CHARS = 200_000

# Wrappers that pass their remaining arguments through to another command. The
# guard must look past them: `sudo rm -rf /` is `rm -rf /` with more privilege,
# not a `sudo` invocation.
PASSTHROUGH = {
    "sudo",
    "doas",
    "nohup",
    "time",
    "nice",
    "ionice",
    "command",
    "builtin",
    "exec",
    "stdbuf",
    "setsid",
    "eatmydata",
    "watch",
    "script",
}

# Wrappers that take options before the command they run. Options are skipped
# until the first non-option token, which is the real command.
PASSTHROUGH_WITH_OPTIONS = {
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-i", "-n", "-P", "-d", "-E", "-s", "-a", "--arg-file",
              "--max-args", "--max-procs", "--delimiter", "--replace"},
    "env": set(),
    "nohup": set(),
}

# Leading positional arguments a wrapper consumes before the command starts.
# `timeout 5 rm -rf /` is the case: `5` is not a flag, so an option-skipping
# loop stops on it and mistakes the duration for the command.
PASSTHROUGH_SKIP_POSITIONAL = {"timeout": 1}

# Interpreters that run a shell string given after `-c`. The string is re-parsed
# as shell, which is what makes `bash -c 'rm -rf /'` visible.
SHELL_INTERPRETERS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "busybox"}

# Interpreters that run code in a non-shell language. The body is NOT parsed as
# shell; it is handed to the rules as opaque inline source, and the rules match
# behavioural patterns in it.
CODE_INTERPRETERS = {
    "python": "-c",
    "python2": "-c",
    "python3": "-c",
    "node": "-e",
    "nodejs": "-e",
    "deno": "eval",
    "perl": "-e",
    "ruby": "-e",
    "php": "-r",
    "osascript": "-e",
}

REDIRECT_OPERATORS = (">>", ">", "<<<", "<<", "<", "2>", "&>", ">|")

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@dataclass
class SimpleCommand:
    """One command the shell would execute, after wrappers are stripped."""

    argv: list[str]
    raw: str
    env: dict[str, str] = field(default_factory=dict)
    redirects: list[str] = field(default_factory=list)
    origin: str = "top"
    depth: int = 0
    quoted_argv: list[bool] = field(default_factory=list)
    inline_code: str | None = None
    inline_language: str | None = None

    @property
    def name(self) -> str:
        """The executable name, without its directory."""
        if not self.argv:
            return ""
        head = self.argv[0]
        # `/usr/bin/rm` and `./rm` are both `rm`. A leading directory is not a
        # disguise the guard should accept.
        head = head.rsplit("/", 1)[-1]
        return head

    @property
    def args(self) -> list[str]:
        return self.argv[1:] if self.argv else []


@dataclass
class Pipeline:
    """`a | b | c` — kept together so upstream/downstream pairs stay visible."""

    commands: list[SimpleCommand]
    raw: str = ""


@dataclass
class ParsedCommand:
    pipelines: list[Pipeline] = field(default_factory=list)
    unparsed: bool = False
    notes: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def commands(self) -> list[SimpleCommand]:
        out: list[SimpleCommand] = []
        for pipeline in self.pipelines:
            out.extend(pipeline.commands)
        return out

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


# ---------------------------------------------------------------------------
# Tokenizer
#
# Returns a flat token stream where each token is (kind, text, quoted). Kinds:
#   word      a literal word (quotes already removed)
#   op        a control operator: && || ; | |& & \n
#   redirect  a redirection operator
#   subst     a nested command string from $( ) ` ` <( ) >( ) ( ) { }
# ---------------------------------------------------------------------------
class TokenizeError(Exception):
    """The string cannot be split into tokens without guessing."""


def _read_matching(text: str, start: int, opener: str, closer: str) -> tuple[str, int]:
    """Read a nested `opener`...`closer` region, honouring quotes inside it.

    Returns the inner text and the index just past the closer. Raises
    TokenizeError when the region never closes, because an unterminated
    substitution means the rest of the parse is a guess.
    """
    depth = 0
    index = start
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char == "\\":
            index += 2
            continue
        if char in ("'", '"'):
            quote = char
            index += 1
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    raise TokenizeError("unterminated %s...%s" % (opener, closer))


def _read_backticks(text: str, start: int) -> tuple[str, int]:
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "`":
            return text[start + 1:index], index + 1
        index += 1
    raise TokenizeError("unterminated backtick substitution")


def tokenize(text: str) -> list[tuple[str, str, bool]]:
    """Split one shell string into control operators, words, and nested regions.

    Quoting is honoured, so `echo "rm -rf /"` yields one word whose content is
    inert data rather than a command. That is the whole reason the guard parses
    instead of grepping.
    """
    tokens: list[tuple[str, str, bool]] = []
    buffer: list[str] = []
    quoted = False
    index = 0
    length = len(text)

    def flush() -> None:
        nonlocal quoted
        if buffer:
            tokens.append(("word", "".join(buffer), quoted))
            buffer.clear()
        quoted = False

    while index < length:
        char = text[index]

        if char == "\\":
            if index + 1 < length:
                nxt = text[index + 1]
                if nxt == "\n":
                    # Line continuation: the shell removes it entirely.
                    index += 2
                    continue
                buffer.append(nxt)
                index += 2
                continue
            buffer.append("\\")
            index += 1
            continue

        if char == "'":
            end = text.find("'", index + 1)
            if end < 0:
                raise TokenizeError("unterminated single quote")
            buffer.append(text[index + 1:end])
            quoted = True
            index = end + 1
            continue

        if char == '"':
            index += 1
            while index < length and text[index] != '"':
                if text[index] == "\\" and index + 1 < length:
                    buffer.append(text[index + 1])
                    index += 2
                    continue
                if text[index] == "$" and index + 1 < length and text[index + 1] == "(":
                    inner, index = _read_matching(text, index + 1, "(", ")")
                    flush()
                    tokens.append(("subst", inner, False))
                    continue
                if text[index] == "`":
                    inner, index = _read_backticks(text, index)
                    flush()
                    tokens.append(("subst", inner, False))
                    continue
                buffer.append(text[index])
                index += 1
            if index >= length:
                raise TokenizeError("unterminated double quote")
            quoted = True
            index += 1
            continue

        if char == "$" and index + 1 < length and text[index + 1] == "(":
            # `$((...))` is arithmetic, not a command substitution.
            if text.startswith("$((", index):
                inner, index = _read_matching(text, index + 2, "(", ")")
                buffer.append("0")
                continue
            inner, index = _read_matching(text, index + 1, "(", ")")
            flush()
            tokens.append(("subst", inner, False))
            continue

        if char == "`":
            inner, index = _read_backticks(text, index)
            flush()
            tokens.append(("subst", inner, False))
            continue

        if char in ("<", ">") and index + 1 < length and text[index + 1] == "(":
            inner, index = _read_matching(text, index + 1, "(", ")")
            flush()
            tokens.append(("subst", inner, False))
            continue

        if char == "(" and not buffer:
            inner, index = _read_matching(text, index, "(", ")")
            flush()
            tokens.append(("subst", inner, False))
            continue

        if char == "{" and not buffer and index + 1 < length and text[index + 1] in " \t\n":
            inner, index = _read_matching(text, index, "{", "}")
            flush()
            tokens.append(("subst", inner, False))
            continue

        if char in " \t":
            flush()
            index += 1
            continue

        if char == "\n":
            flush()
            tokens.append(("op", "\n", False))
            index += 1
            continue

        two = text[index:index + 2]
        if two in ("&&", "||", "|&", ">>", "2>", "&>"):
            flush()
            kind = "redirect" if two in (">>", "2>", "&>") else "op"
            tokens.append((kind, two, False))
            index += 2
            continue

        if char in ";|&":
            flush()
            tokens.append(("op", char, False))
            index += 1
            continue

        if char in "<>":
            flush()
            tokens.append(("redirect", char, False))
            index += 1
            continue

        buffer.append(char)
        index += 1

    flush()
    return tokens


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _strip_wrappers(argv: list[str], quoted: list[bool]) -> tuple[list[str], list[bool], dict]:
    """Remove env assignments and transparent wrappers from the front of argv.

    Returns the real command, its quoting flags, and the environment assignments
    that were stripped. The assignments are kept because they can themselves be
    the payload (`LD_PRELOAD=...`, `AWS_PROFILE=production`).
    """
    env: dict[str, str] = {}
    index = 0
    guard = 0
    while index < len(argv) and guard < 32:
        guard += 1
        token = argv[index]
        if _ASSIGNMENT_RE.match(token):
            key, _, value = token.partition("=")
            env[key] = value
            index += 1
            continue
        head = token.rsplit("/", 1)[-1]
        if head in PASSTHROUGH_WITH_OPTIONS:
            index += 1
            flags = PASSTHROUGH_WITH_OPTIONS[head]
            while index < len(argv):
                candidate = argv[index]
                if _ASSIGNMENT_RE.match(candidate):
                    key, _, value = candidate.partition("=")
                    env[key] = value
                    index += 1
                    continue
                if candidate.startswith("-"):
                    takes_value = candidate in flags
                    index += 1
                    if takes_value and index < len(argv):
                        index += 1
                    continue
                break
            index += PASSTHROUGH_SKIP_POSITIONAL.get(head, 0)
            continue
        if head in PASSTHROUGH:
            index += 1
            while index < len(argv) and argv[index].startswith("-"):
                index += 1
            continue
        break
    if index >= len(argv) and argv:
        # Stripping consumed everything, which means the "wrapper" was the
        # command: bare `env`, bare `timeout`. Returning an empty argv would
        # erase the command from the analysis, so keep the original.
        return argv, quoted, env
    return argv[index:], quoted[index:], env


def _split_on_operators(
    tokens: list[tuple[str, str, bool]],
) -> tuple[list[list[list[tuple[str, str, bool]]]], list[str]]:
    """Group tokens into pipelines, each a list of simple-command token runs.

    `a && b | c ; d` becomes [[a]], [[b], [c]], [[d]] — three pipelines, the
    second with two stages. Substitution tokens are carried through so the
    caller can recurse into them.
    """
    pipelines: list[list[list[tuple[str, str, bool]]]] = []
    substitutions: list[str] = []
    current_pipeline: list[list[tuple[str, str, bool]]] = []
    current: list[tuple[str, str, bool]] = []

    def end_command() -> None:
        if current:
            current_pipeline.append(list(current))
            current.clear()

    def end_pipeline() -> None:
        end_command()
        if current_pipeline:
            pipelines.append(list(current_pipeline))
            current_pipeline.clear()

    for kind, text, quoted in tokens:
        if kind == "op":
            if text in ("|", "|&"):
                end_command()
            else:
                end_pipeline()
            continue
        if kind == "subst":
            substitutions.append(text)
            continue
        current.append((kind, text, quoted))

    end_pipeline()
    return pipelines, substitutions


def _build_simple_command(
    run: list[tuple[str, str, bool]], origin: str, depth: int
) -> SimpleCommand | None:
    words: list[str] = []
    quoted: list[bool] = []
    redirects: list[str] = []
    expecting_redirect: str | bool = False
    for kind, text, is_quoted in run:
        if kind == "redirect":
            expecting_redirect = text
            continue
        if expecting_redirect:
            # The operator is kept with the target: `< input.txt` reads and
            # `> /etc/hosts` destroys, and a rule that cannot tell them apart
            # flags every command that reads a file.
            redirects.append("%s %s" % (expecting_redirect, text))
            expecting_redirect = False
            continue
        words.append(text)
        quoted.append(is_quoted)
    if not words:
        if redirects:
            # A bare redirection still writes: `> /etc/hosts` truncates a file.
            return SimpleCommand(
                argv=[], raw=" ".join(redirects), redirects=redirects,
                origin=origin, depth=depth,
            )
        return None
    argv, quoted, env = _strip_wrappers(words, quoted)
    if not argv:
        # Nothing but assignments: `FOO=bar`. Keep it, the env may be the payload.
        return SimpleCommand(
            argv=[], raw=" ".join(words), env=env, redirects=redirects,
            origin=origin, depth=depth,
        )
    return SimpleCommand(
        argv=argv,
        raw=" ".join(words),
        env=env,
        redirects=redirects,
        origin=origin,
        depth=depth,
        quoted_argv=quoted,
    )


def _nested_shell_body(command: SimpleCommand) -> str | None:
    """The shell string a nested interpreter would run, if there is one."""
    name = command.name
    if name not in SHELL_INTERPRETERS:
        return None
    args = command.args
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-c":
            return args[index + 1] if index + 1 < len(args) else ""
        if token.startswith("-") and token != "--" and "c" in token[1:]:
            # Combined flags such as `sh -ec 'cmd'`.
            return args[index + 1] if index + 1 < len(args) else ""
        index += 1
    return None


def _remote_shell_body(command: SimpleCommand) -> str | None:
    """The command string an `ssh host '...'` invocation would run remotely."""
    if command.name != "ssh":
        return None
    args = command.args
    index = 0
    value_flags = {"-i", "-p", "-l", "-o", "-F", "-J", "-b", "-c", "-E", "-L", "-R", "-D"}
    while index < len(args):
        token = args[index]
        if token in value_flags:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        # First non-option is the destination; everything after is the command.
        remainder = args[index + 1:]
        return " ".join(remainder) if remainder else None
    return None


# Filters whose value bounds what `find` can hand to `-exec`.
_FIND_NAME_FLAGS = ("-name", "-iname", "-path", "-ipath", "-wholename")


def _find_substitution(args: list[str]) -> str:
    """What `{}` should be judged as, for a given `find` invocation.

    `{}` on its own is meaningless to a path classifier, and judging it as the
    working directory would flag every cache cleanup in every repository. What
    `find` can actually produce is bounded by two things: the roots it walks and
    the name filters it applies. So `find . -name '__pycache__' -exec rm -rf {}`
    is judged as `./__pycache__`, and a find with no filter is judged as its
    roots, which is the honest wider answer.
    """
    roots: list[str] = []
    names: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in _FIND_NAME_FLAGS and index + 1 < len(args):
            names.append(args[index + 1])
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            if token in ("-type", "-maxdepth", "-mindepth", "-newer", "-size",
                         "-perm", "-user", "-group", "-mtime", "-regex"):
                index += 1
            continue
        if token in ("(", ")", "!", ",", "{}", ";", "+"):
            index += 1
            continue
        roots.append(token)
        index += 1
    if not roots:
        roots = ["."]
    if names:
        return " ".join(
            "%s/%s" % (root.rstrip("/"), name) for root in roots for name in names
        )
    return " ".join(roots)


def _find_exec_body(command: SimpleCommand) -> str | None:
    """The command `find ... -exec CMD {} ;` would run for each match."""
    if command.name != "find":
        return None
    args = command.args
    for index, token in enumerate(args):
        if token in ("-exec", "-execdir", "-ok", "-okdir"):
            substitution = _find_substitution(args[:index])
            body: list[str] = []
            for follow in args[index + 1:]:
                if follow in (";", "+", "\\;"):
                    break
                body.append(substitution if follow == "{}" else follow)
            if body:
                return " ".join(body)
    return None


def _inline_code(command: SimpleCommand) -> tuple[str, str] | None:
    """`(language, source)` when the command runs inline non-shell code."""
    name = command.name
    flag = CODE_INTERPRETERS.get(name)
    if flag is None:
        return None
    args = command.args
    for index, token in enumerate(args):
        if token == flag and index + 1 < len(args):
            return name, args[index + 1]
        if name.startswith("python") and token.startswith("-") and "c" in token[1:]:
            if index + 1 < len(args):
                return name, args[index + 1]
    return None


def parse(command: str) -> ParsedCommand:
    """Decompose a shell command line into every simple command it would run."""
    result = ParsedCommand()
    if command is None:
        result.unparsed = True
        result.note("no command supplied")
        return result
    text = command.strip()
    if not text:
        return result
    if len(text) > MAX_INPUT_CHARS:
        result.unparsed = True
        result.truncated = True
        result.note(
            "command is %d chars, past the %d-char parse ceiling"
            % (len(text), MAX_INPUT_CHARS)
        )
        text = text[:MAX_INPUT_CHARS]

    # Work queue of (source text, origin label, depth) so recursion into
    # substitutions and nested shells is breadth-first and bounded.
    queue: list[tuple[str, str, int]] = [(text, "top", 0)]
    total = 0

    while queue:
        source, origin, depth = queue.pop(0)
        if depth > MAX_DEPTH:
            result.unparsed = True
            result.note("nesting deeper than %d levels was not followed" % MAX_DEPTH)
            continue
        try:
            tokens = tokenize(source)
        except TokenizeError as exc:
            result.unparsed = True
            result.note("%s (in %s)" % (exc, origin))
            continue

        groups, substitutions = _split_on_operators(tokens)
        for inner in substitutions:
            queue.append((inner, "substitution", depth + 1))

        for group in groups:
            stages: list[SimpleCommand] = []
            for run in group:
                built = _build_simple_command(run, origin, depth)
                if built is None:
                    continue
                total += 1
                if total > MAX_COMMANDS:
                    result.unparsed = True
                    result.truncated = True
                    result.note(
                        "stopped after %d simple commands; the rest was not inspected"
                        % MAX_COMMANDS
                    )
                    queue.clear()
                    break
                nested = _nested_shell_body(built)
                if nested is not None:
                    queue.append((nested, "%s -c" % built.name, depth + 1))
                remote = _remote_shell_body(built)
                if remote:
                    queue.append((remote, "ssh remote", depth + 1))
                found = _find_exec_body(built)
                if found:
                    queue.append((found, "find -exec", depth + 1))
                inline = _inline_code(built)
                if inline is not None:
                    built.inline_language, built.inline_code = inline
                stages.append(built)
            if stages:
                result.pipelines.append(Pipeline(commands=stages, raw=source))
            if result.truncated and not queue:
                break

    return result
