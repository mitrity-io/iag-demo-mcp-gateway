"""Helpers shared by the runner and the phases (kept import-light so phases stay simple)."""

from __future__ import annotations

import os
import re

# The governed shell ships with the sentinel release that routes Bash into it.
GOVERNED_SHELL_MIN_VERSION = (0, 21, 0)


def gateway_version() -> tuple[int, int, int] | None:
    """The gateway's semver as exported by entrypoint.sh (`v0.20.0` -> (0, 20, 0))."""
    raw = os.environ.get("MITRITY_GATEWAY_VERSION", "")
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def governed_shell_available() -> bool:
    """Whether the gateway in this image routes built-in Bash into the governed shell."""
    if os.environ.get("MITRITY_DEMO_FORCE_PHASE9") == "1":
        return True
    version = gateway_version()
    return version is not None and version >= GOVERNED_SHELL_MIN_VERSION
