"""Points the session/ledger stores at throwaway folders and configures test-only security env.

COPILOT_SESSION_DIR / COPILOT_LEDGER_DIR must be set before services.agent.session_store and
services.security are imported anywhere.

TENANT_ENROLLMENT_KEY enables the token-issuance endpoint for the suite (production requires an
explicit key). RATE_LIMIT_PER_MINUTE=0 disables the API limiter so hundreds of in-process test
requests are not throttled; the limiter itself is covered by tests/security/test_rate_limit.py.
"""

import os
import tempfile

os.environ.setdefault("COPILOT_SESSION_DIR", tempfile.mkdtemp(prefix="copilot_sessions_"))
os.environ.setdefault("COPILOT_LEDGER_DIR", tempfile.mkdtemp(prefix="copilot_ledger_"))
os.environ.setdefault("TENANT_ENROLLMENT_KEY", "test-enrollment-key")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
