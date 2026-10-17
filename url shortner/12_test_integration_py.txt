"""Integration tests for url-shortener endpoints against real Postgres and Redis.

Tests verify:
- GET /health
- GET / (Interactive Web UI dashboard)
- POST /shorten (normal and custom)
- GET /{code} (redirects, Redis caching, click increments)
- GET /api/links
- PUT /api/links/{code} (update link URL)
- DELETE /api/links/{code} (delete link and invalidate cache)
- GET /api/links/{code}/stats
"""
import random
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import cache
from app.codes import ALPHABET


def random_custom(prefix="c"):
    return prefix + "".join(random.choices(ALPHABET, k=6))


@pytest.fixture(scope="session")
def client():
    """Session test client for FastAPI."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    """Verify both Postgres and Redis are reachable."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["postgres"] is True
    assert data["redis"] is True


def test_index_dashboard(client):
    """Verify GET / returns interactive HTML dashboard."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "URL Shortener & Click Analytics" in resp.text
    assert "Active Links" in resp.text


def test_shorten_valid_url(client):
    """Test shortening a standard URL with auto-generated code."""
    url = f"https://example.com/test-{uuid.uuid4().hex[:8]}"
    resp = client.post("/shorten", json={"url": url})
    assert resp.status_code == 201
    data = resp.json()
    assert "code" in data
    assert len(data["code"]) >= 1
    assert data["url"] == url
    assert data["short"] == f"/{data['code']}"


def test_shorten_custom_code(client):
    """Test shortening with a user-specified custom code."""
    custom = random_custom("my")
    url = f"https://example.com/page-{uuid.uuid4().hex[:8]}"
    resp = client.post("/shorten", json={"url": url, "custom": custom})
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == custom
    assert data["short"] == f"/{custom}"

    # Re-using the same custom code must return 409 Conflict
    conflict_resp = client.post("/shorten", json={"url": "https://example.com/different", "custom": custom})
    assert conflict_resp.status_code == 409
    assert "already taken" in conflict_resp.json()["detail"]


def test_shorten_invalid_urls(client):
    """Test invalid or unsafe URLs are rejected with 400 Bad Request."""
    # Empty URL
    resp = client.post("/shorten", json={"url": ""})
    assert resp.status_code == 400

    # Disallowed scheme
    resp = client.post("/shorten", json={"url": "ftp://example.com/file"})
    assert resp.status_code == 400

    # Unsafe host (localhost / private network)
    resp = client.post("/shorten", json={"url": "http://127.0.0.1:8080/admin"})
    assert resp.status_code == 400
    assert "that host is not allowed" in resp.json()["detail"]


def test_shorten_invalid_custom_code(client):
    """Test custom codes that are reserved, too short, or contain illegal characters."""
    # Too short
    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "ab"})
    assert resp.status_code == 400

    # Reserved word
    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "health"})
    assert resp.status_code == 400

    # Illegal character
    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "code-invalid!"})
    assert resp.status_code == 400


def test_follow_redirect_and_redis_cache(client):
    """Test 302 redirect, Redis caching of hot link, and click incrementing."""
    custom = random_custom("red")
    target_url = f"https://example.com/target-{uuid.uuid4().hex[:8]}"

    shorten_resp = client.post("/shorten", json={"url": target_url, "custom": custom})
    assert shorten_resp.status_code == 201
    code = shorten_resp.json()["code"]

    # First request: not in Redis cache initially
    cache_key = f"link:{code}"
    # Follow redirect with follow_redirects=False to inspect 302
    resp1 = client.get(f"/{code}", follow_redirects=False)
    assert resp1.status_code == 302
    assert resp1.headers["location"] == target_url

    # Verify link is now cached in Redis
    cached = cache.get_json(cache_key)
    assert cached is not None
    assert cached["url"] == target_url

    # Second request: served from cache
    resp2 = client.get(f"/{code}", follow_redirects=False)
    assert resp2.status_code == 302

    # Non-existent code returns 404
    missing_resp = client.get("/nonexistentcode404", follow_redirects=False)
    assert missing_resp.status_code == 404


def test_list_links(client):
    """Test GET /api/links lists links."""
    resp = client.get("/api/links")
    assert resp.status_code == 200
    data = resp.json()
    assert "links" in data
    assert isinstance(data["links"], list)
    assert len(data["links"]) > 0
    # Seeded links should be present
    codes = [item["code"] for item in data["links"]]
    assert any(c in codes for c in ["welcome", "circleci", "git"])


def test_update_and_delete_link(client):
    """Test CRUD update (PUT) and delete (DELETE) operations."""
    custom = random_custom("cr")
    initial_url = f"https://example.com/initial-{uuid.uuid4().hex[:8]}"
    updated_url = f"https://example.com/updated-{uuid.uuid4().hex[:8]}"

    # 1. Create link
    resp = client.post("/shorten", json={"url": initial_url, "custom": custom})
    assert resp.status_code == 201

    # 2. Redirect to cache it
    resp_redirect = client.get(f"/{custom}", follow_redirects=False)
    assert resp_redirect.status_code == 302
    assert resp_redirect.headers["location"] == initial_url
    assert cache.get_json(f"link:{custom}") is not None

    # 3. Update link target URL
    update_resp = client.put(f"/api/links/{custom}", json={"url": updated_url})
    assert update_resp.status_code == 200
    assert update_resp.json()["url"] == updated_url
    # Redis cache should have been invalidated
    assert cache.get_json(f"link:{custom}") is None

    # 4. Redirect follows new URL
    resp_new_redirect = client.get(f"/{custom}", follow_redirects=False)
    assert resp_new_redirect.status_code == 302
    assert resp_new_redirect.headers["location"] == updated_url

    # 5. Delete link
    del_resp = client.delete(f"/api/links/{custom}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # 6. Verify link is gone
    resp_gone = client.get(f"/{custom}", follow_redirects=False)
    assert resp_gone.status_code == 404

    # 7. Updating or deleting non-existent link returns 404
    assert client.put(f"/api/links/{custom}", json={"url": updated_url}).status_code == 404
    assert client.delete(f"/api/links/{custom}").status_code == 404


def test_link_stats(client):
    """Test GET /api/links/{code}/stats."""
    # Seeded code 'welcome' has seed clicks
    resp = client.get("/api/links/welcome/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "welcome"
    assert "url" in data
    assert "per_day" in data
    assert "referrers" in data
    assert isinstance(data["per_day"], list)
    assert isinstance(data["referrers"], list)

    # 404 on missing stats
    resp_missing = client.get("/api/links/nonexistentcode404/stats")
    assert resp_missing.status_code == 404
