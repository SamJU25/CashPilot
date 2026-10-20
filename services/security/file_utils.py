"""Filesystem helpers for sensitive local state.

Session files contain raw bank statements and the ledger and invoice registry contain financial
proposals. Default POSIX permissions (0644/0755) expose those to every
local user on a shared machine, so writes go through these helpers. On Windows chmod only
toggles the read-only bit; the calls are best-effort there and never fail a write.
"""

from __future__ import annotations

import os

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_dir(path: str) -> None:
    """Creates the directory if needed and restricts it to the owner (0700)."""
    os.makedirs(path, mode=PRIVATE_DIR_MODE, exist_ok=True)
    try:
        os.chmod(path, PRIVATE_DIR_MODE)
    except OSError:
        pass


def restrict_file(path: str) -> None:
    """Restricts a written file to the owner (0600)."""
    try:
        os.chmod(path, PRIVATE_FILE_MODE)
    except OSError:
        pass
