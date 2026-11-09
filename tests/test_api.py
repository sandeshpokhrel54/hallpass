import pytest
from fastapi.testclient import TestClient

from hallpass.api import app

client = TestClient(app)


@pytest.mark.parametrize("size", [-1, 0, 101])
def test_search_rejects_out_of_range_size(size):
    # Validation happens before any Elasticsearch call, so no cluster is needed.
    assert client.get("/search", params={"q": "diffusion", "size": size}).status_code == 422


def test_health():
    assert client.get("/health").json() == {"ok": True}
