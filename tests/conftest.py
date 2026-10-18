"""Points the session store at a throwaway folder: test fixtures call clear_all(), which deletes every session file."""

import os
import tempfile

# Must run before services.agent.session_store is imported anywhere.
os.environ.setdefault("COPILOT_SESSION_DIR", tempfile.mkdtemp(prefix="copilot_sessions_"))
