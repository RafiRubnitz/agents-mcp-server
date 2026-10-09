import os
import tempfile

# Before any inbox_mcp import: tests log into a throwaway folder, never the project's logs/.
os.environ["INBOX_LOGS"] = tempfile.mkdtemp(prefix="inbox-logs-")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from inbox_mcp.server import create_app  # noqa: E402
from inbox_mcp.store import Store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "inbox.db")
    s.register("sid-a", "alice", "builds the api")
    s.register("sid-b", "bob", "writes the tests")
    yield s
    s.close()


@pytest.fixture
def client(store):
    return TestClient(create_app(store))
