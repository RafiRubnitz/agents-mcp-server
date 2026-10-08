import os
import tempfile

# Before any inbox_mcp import: tests log into a throwaway folder, never the project's logs/.
os.environ["INBOX_LOGS"] = tempfile.mkdtemp(prefix="inbox-logs-")
