"""Optional encryption at rest for sensitive local JSON stores.

Session files hold raw bank statements, the ledger holds financing proposals, and the invoice
registry holds pledged receivables. Owner-only permissions are the minimum; on a shared machine or
a copied volume they are not enough.

Set ``COPILOT_DATA_KEY`` (or ``DATA_ENCRYPTION_KEY``) to a urlsafe-base64 32-byte Fernet key:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Sealed payloads carry the ``enc:v1:`` prefix, so existing plaintext files remain readable and are
re-encrypted on their next write. Local development may run without a key (owner-only permissions
are then the only control), but a deployed environment (``COPILOT_ENV=production|staging``) refuses
to start without one.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

MAGIC = "enc:v1:"


class DataDecryptionError(Exception):
    """Raised when a sealed payload cannot be opened with the configured key."""


class DataEncryptionError(Exception):
    """Raised when a deployed environment is missing the required data key."""


# Environments that must not run with plaintext statement/ledger stores.
DEPLOYED_ENVIRONMENTS = frozenset({"production", "prod", "staging", "deployed"})

_LOCAL_PLAINTEXT_WARNED = False


@lru_cache(maxsize=4)
def _fernet(key: str) -> Fernet:
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise DataDecryptionError("COPILOT_DATA_KEY is not a valid Fernet key") from exc


def _configured_key() -> str:
    return (os.getenv("COPILOT_DATA_KEY") or os.getenv("DATA_ENCRYPTION_KEY") or "").strip()


def encryption_enabled() -> bool:
    """True when a data key is configured (for startup diagnostics)."""
    return bool(_configured_key())


def deployment_environment() -> str:
    """COPILOT_ENV (or APP_ENV/ENVIRONMENT) reduced to a lowercase label; 'local' by default."""
    return (
        os.getenv("COPILOT_ENV") or os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "local"
    ).strip().lower()


def validate_configuration() -> None:
    """Fails at startup on a malformed key, or on a missing key outside local development."""
    key = _configured_key()
    if key:
        _fernet(key)
        return

    env_name = deployment_environment()
    if env_name in DEPLOYED_ENVIRONMENTS:
        raise DataEncryptionError(
            f"COPILOT_DATA_KEY is required when COPILOT_ENV={env_name}: statements, staged intents, "
            "and the invoice registry would otherwise be stored as plaintext."
        )

    global _LOCAL_PLAINTEXT_WARNED
    if not _LOCAL_PLAINTEXT_WARNED:
        _LOCAL_PLAINTEXT_WARNED = True
        logger.warning(
            "COPILOT_DATA_KEY is not set: .sessions/ and .data/ are stored as plaintext with "
            "owner-only permissions. Set a key before deploying."
        )


def seal_text(text: str) -> str:
    """Encrypts text when a key is configured; otherwise returns it unchanged."""
    key = _configured_key()
    if not key:
        return text
    return MAGIC + _fernet(key).encrypt(text.encode("utf-8")).decode("ascii")


def open_text(raw: str) -> str:
    """Decrypts a sealed payload, passes legacy plaintext through, and fails clearly on key issues."""
    if not raw.startswith(MAGIC):
        return raw
    key = _configured_key()
    if not key:
        raise DataDecryptionError("Encrypted store found but COPILOT_DATA_KEY is not set")
    try:
        return _fernet(key).decrypt(raw[len(MAGIC):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DataDecryptionError("Could not decrypt store: wrong COPILOT_DATA_KEY") from exc
