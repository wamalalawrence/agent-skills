"""Stable process exit codes for the Agent Skills CLI.

These are a public contract. Scripts and CI branch on them, so they are frozen
at 1.0 and may not be renumbered afterwards. Adding a new code is allowed;
changing the meaning of an existing one is not.

Every non-zero code answers a different operator question, because "it failed"
is not actionable and a single code forces log-scraping:

  2   the command was wrong          -> fix the invocation
  3   the source needs credentials   -> authenticate, then retry
  4   the source was unreachable     -> retry later, check the network
  5   the payload was not what it    -> do not retry blindly; this is either a
      claimed to be                     corrupt download or an attack
  6   the machine could not be       -> the previous version is still active
      changed
  7   the machine is in a bad state  -> run doctor
  10  an update is available         -> informational, not a failure
  11  the route exists and is        -> not retryable as-is: the route's mode,
      authenticated, but this           scope, or policy excludes this operation;
      operation is not available        change the route (e.g. a write profile)
                                        or hand the change to the user.
                                        Added in 1.5.0 for `access check`.
"""

from __future__ import annotations


class Exit:
    """Process exit codes. See the module docstring before changing one."""

    OK = 0
    USAGE = 2
    AUTH_REQUIRED = 3
    NETWORK = 4
    INTEGRITY = 5
    INSTALL_FAILED = 6
    VERIFY_FAILED = 7
    UPDATE_AVAILABLE = 10
    CAPABILITY_UNAVAILABLE = 11

    # Human-readable names, used by `agent-skills verify --explain-codes` and by
    # the test suite so a renumbering cannot pass silently.
    NAMES = {
        0: "ok",
        2: "usage-error",
        3: "authentication-required",
        4: "network-failure",
        5: "integrity-failure",
        6: "installation-failure",
        7: "verification-failure",
        10: "update-available",
        11: "capability-unavailable",
    }


class ExitError(Exception):
    """An error that carries the exit code the process should end with.

    Raised instead of calling ``sys.exit`` deep in the call stack so that the
    install transaction can catch it, roll back, and only then exit.
    """

    def __init__(self, message: str, code: int = Exit.INSTALL_FAILED, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint

    def render(self) -> str:
        out = "agent-skills: {}".format(self.message)
        if self.hint:
            out += "\n  {}".format(self.hint)
        return out
