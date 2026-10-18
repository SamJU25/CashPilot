"""Points the session store at a throwaway folder: test fixtures call clear_all(), which deletes every session file."""

import os
import tempfile

# Must run before services.agent.session_store and services.security are imported anywhere.
os.environ.setdefault("COPILOT_SESSION_DIR", tempfile.mkdtemp(prefix="copilot_sessions_"))
os.environ.setdefault("COPILOT_LEDGER_DIR", tempfile.mkdtemp(prefix="copilot_ledger_"))
