"""Server route tests with NaraClient swapped via FastAPI dependency overrides."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nara.config import Config
from nara.server import create_app
from nara.server.routes.search import get_nara_client


FIXTURE = Path(__file__).parent / "fixtures" / "sample_response.json"
SEARCH_FIXTURE = json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeNaraClient:
    """Stand-in that records calls and returns the canned fixture."""

    def __init__(self) -> None:
        self.search_calls: list[dict] = []
        self.get_record_calls: list[str] = []
        self.get_children_calls: list[tuple[str, int]] = []
        # Default behaviour: return the 4-unit search fixture. Tests can rebind.
        self.search_response = SEARCH_FIXTURE
        self.record_response: dict | None = SEARCH_FIXTURE
        self.children_response = SEARCH_FIXTURE

    def search(self, params):  # type: ignore[no-untyped-def]
        self.search_calls.append(params)
        return self.search_response

    def get_record(self, naid):  # type: ignore[no-untyped-def]
        self.get_record_calls.append(naid)
        return self.record_response

    def get_children(self, naid, *, limit=300):  # type: ignore[no-untyped-def]
        self.get_children_calls.append((naid, limit))
        return self.children_response


def _config(tmp_path: Path, *, api_key: str | None = "fake-key") -> Config:
    return Config(
        api_key=api_key,
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


@pytest.fixture
def client_and_fake(tmp_path):
    app = create_app(_config(tmp_path))
    fake = FakeNaraClient()
    app.dependency_overrides[get_nara_client] = lambda: fake
    return TestClient(app), fake


def test_search_minimal_returns_normalized_hits(client_and_fake):
    client, fake = client_and_fake
    r = client.get("/api/search", params={"q": "anything"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert len(body["hits"]) == 4
    # Field flattening landed correctly.
    by_naid = {h["naid"]: h for h in body["hits"]}
    a = by_naid["10000001"]
    assert a["title"].startswith("Letter from General Smith")
    assert a["level"] == "fileUnit"
    assert a["digital_object_count"] == 3
    assert a["thumbnail_url"].endswith("page-001.jpg")
    assert a["inclusive_start_year"] == 1944


def test_search_passes_filter_params_through(client_and_fake):
    client, fake = client_and_fake
    r = client.get("/api/search", params=[
        ("q", "constitution"),
        ("level", "fileUnit"),
        ("level", "item"),
        ("year_from", "1940"),
        ("year_to", "1950"),
        ("has_digital_objects", "true"),
        ("page", "2"),
        ("page_size", "50"),
    ])
    assert r.status_code == 200, r.text
    assert len(fake.search_calls) == 1
    sent = fake.search_calls[0]
    assert sent["q"] == "constitution"
    assert sent["page"] == 2
    assert sent["limit"] == 50
    assert sent["levelOfDescription"] == "fileUnit,item"
    assert sent["startDate"] == "1940"
    assert sent["endDate"] == "1950"
    assert sent["availableOnline"] == "true"


def test_search_caps_page_size(client_and_fake):
    client, _ = client_and_fake
    r = client.get("/api/search", params={"q": "x", "page_size": 9999})
    assert r.status_code == 422  # Query(le=100)


def test_search_requires_non_empty_q(client_and_fake):
    client, _ = client_and_fake
    r = client.get("/api/search", params={"q": ""})
    assert r.status_code == 422


def test_search_502_when_nara_unreachable(tmp_path):
    from nara.api import NaraApiError

    class BrokenClient(FakeNaraClient):
        def search(self, params):
            raise NaraApiError("upstream down")

    app = create_app(_config(tmp_path))
    app.dependency_overrides[get_nara_client] = lambda: BrokenClient()
    c = TestClient(app)
    r = c.get("/api/search", params={"q": "x"})
    assert r.status_code == 502
    assert "upstream down" in r.json()["detail"]


def test_get_record_returns_first_hit(client_and_fake):
    client, fake = client_and_fake
    r = client.get("/api/records/10000001")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["naid"] == "10000001"
    assert body["title"].startswith("Letter from General Smith")
    assert body["level"] == "fileUnit"
    assert len(body["digital_objects"]) == 3
    assert body["record"]["naId"] == "10000001"


def test_get_record_404_when_no_hits(tmp_path):
    app = create_app(_config(tmp_path))
    fake = FakeNaraClient()
    fake.record_response = {"body": {"hits": {"hits": [], "total": {"value": 0}}}}
    app.dependency_overrides[get_nara_client] = lambda: fake
    c = TestClient(app)
    r = c.get("/api/records/999")
    assert r.status_code == 404


def test_get_children_delegates_to_client(client_and_fake):
    client, fake = client_and_fake
    r = client.get("/api/records/10000001/children", params={"limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_naid"] == "10000001"
    assert body["total"] == 4
    assert len(body["hits"]) == 4
    assert fake.get_children_calls == [("10000001", 10)]


def test_no_api_key_returns_503(tmp_path):
    # Don't override the dependency — exercise the real get_nara_client path.
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.get("/api/search", params={"q": "x"})
    assert r.status_code == 503
    assert "nara init" in r.json()["detail"].lower()
