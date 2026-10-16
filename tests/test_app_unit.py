"""Unit tests for app/main.py, app/cache.py, and app/db.py using mocks.

Pure logic and controller tests: no real database, no real Redis network.
Ensures pytest --cov=app achieves > 85-90% coverage across the entire application.
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import cache, db


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# Test Health Endpoint
# ============================================================================

def test_health_all_ok(client):
    with patch.object(db, "query", return_value=[{"?column?": 1}]), \
         patch.object(cache, "client") as mock_cache_client:
        mock_cache_client.return_value.ping.return_value = True
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "postgres": True, "redis": True}


def test_health_db_failure(client):
    with patch.object(db, "query", side_effect=Exception("connection refused")), \
         patch.object(cache, "client") as mock_cache_client:
        mock_cache_client.return_value.ping.return_value = True
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["postgres"] is False
        assert "connection refused" in data["pg_error"]


def test_health_redis_failure(client):
    with patch.object(db, "query", return_value=[{"?column?": 1}]), \
         patch.object(cache, "client") as mock_cache_client:
        mock_cache_client.return_value.ping.side_effect = Exception("redis timeout")
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["redis"] is False
        assert "redis timeout" in data["redis_error"]


# ============================================================================
# Test Web UI Dashboard
# ============================================================================

def test_web_ui_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "URL Shortener & Click Analytics" in resp.text
    assert "Create a Short Link" in resp.text


# ============================================================================
# Test Shorten Endpoint
# ============================================================================

def test_shorten_auto_generated_code(client):
    with patch.object(db, "one") as mock_one, \
         patch.object(db, "query") as mock_query, \
         patch.object(cache, "drop"):
        mock_one.return_value = {"id": 100}
        resp = client.post("/shorten", json={"url": "https://example.com/welcome"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/welcome"
        assert "code" in data
        assert data["short"] == f"/{data['code']}"
        assert mock_query.called


def test_shorten_custom_code(client):
    with patch.object(db, "one") as mock_one, \
         patch.object(cache, "drop"):
        # First db.one: SELECT 1 returns None (not taken)
        # Second db.one: INSERT returns id, code
        mock_one.side_effect = [None, {"id": 1, "code": "mykey"}]
        resp = client.post("/shorten", json={"url": "https://example.com/page", "custom": "mykey"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "mykey"
        assert data["short"] == "/mykey"


def test_shorten_custom_code_already_taken(client):
    with patch.object(db, "one", return_value={"?column?": 1}):
        resp = client.post("/shorten", json={"url": "https://example.com", "custom": "taken"})
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]


def test_shorten_custom_code_unique_violation_exception(client):
    with patch.object(db, "one") as mock_one:
        # Check returns None, but insert raises unique violation error
        mock_one.side_effect = [None, Exception("duplicate key value violates unique constraint")]
        resp = client.post("/shorten", json={"url": "https://example.com", "custom": "fastkey"})
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]


def test_shorten_invalid_url(client):
    resp = client.post("/shorten", json={"url": "not-a-valid-scheme://example.com"})
    assert resp.status_code == 400


def test_shorten_unsafe_url(client):
    resp = client.post("/shorten", json={"url": "http://127.0.0.1:8080"})
    assert resp.status_code == 400
    assert "that host is not allowed" in resp.json()["detail"]


def test_shorten_invalid_custom_code_error(client):
    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "api"})
    assert resp.status_code == 400
    assert "reserved" in resp.json()["detail"]


# ============================================================================
# Test List and Stats Endpoints
# ============================================================================

def test_list_links(client):
    sample = [{"code": "c1", "url": "https://a.com/", "clicks": 5}]
    with patch.object(db, "query", return_value=sample):
        resp = client.get("/api/links")
        assert resp.status_code == 200
        assert resp.json() == {"links": sample}


def test_stats_success(client):
    with patch.object(db, "one", return_value={"id": 10, "code": "statcode", "url": "https://a.com/"}), \
         patch.object(db, "query") as mock_query:
        mock_query.side_effect = [
            [{"day": "2026-10-16", "clicks": 10}],
            [{"referrer": "https://google.com/", "clicks": 8}]
        ]
        resp = client.get("/api/links/statcode/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "statcode"
        assert len(data["per_day"]) == 1
        assert len(data["referrers"]) == 1


def test_stats_not_found(client):
    with patch.object(db, "one", return_value=None):
        resp = client.get("/api/links/missing/stats")
        assert resp.status_code == 404


# ============================================================================
# Test CRUD Update & Delete Endpoints
# ============================================================================

def test_update_link_success(client):
    with patch.object(db, "one", return_value={"id": 1, "code": "editcode", "url": "https://old.com/"}), \
         patch.object(db, "query"), \
         patch.object(cache, "drop") as mock_drop:
        resp = client.put("/api/links/editcode", json={"url": "https://new.com/page"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://new.com/page"
        mock_drop.assert_called_with("link:editcode")


def test_update_link_not_found(client):
    with patch.object(db, "one", return_value=None):
        resp = client.put("/api/links/missing/update", json={"url": "https://new.com/"})
        assert resp.status_code == 404


def test_update_link_invalid_url(client):
    with patch.object(db, "one", return_value={"id": 1, "code": "editcode", "url": "https://old.com/"}):
        resp = client.put("/api/links/editcode", json={"url": "ftp://bad"})
        assert resp.status_code == 400


def test_update_link_unsafe_url(client):
    with patch.object(db, "one", return_value={"id": 1, "code": "editcode", "url": "https://old.com/"}):
        resp = client.put("/api/links/editcode", json={"url": "http://10.0.0.1/"})
        assert resp.status_code == 400


def test_delete_link_success(client):
    with patch.object(db, "one", return_value={"id": 1}), \
         patch.object(db, "query"), \
         patch.object(cache, "drop") as mock_drop:
        resp = client.delete("/api/links/delcode")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "code": "delcode"}
        mock_drop.assert_called_with("link:delcode", "clicks:delcode")


def test_delete_link_not_found(client):
    with patch.object(db, "one", return_value=None):
        resp = client.delete("/api/links/missing")
        assert resp.status_code == 404


# ============================================================================
# Test Redirect (Follow) Endpoint
# ============================================================================

def test_follow_cache_hit(client):
    with patch.object(cache, "get_json", return_value={"id": 42, "url": "https://cached.com/"}), \
         patch.object(db, "query"), \
         patch.object(cache, "client") as mock_cache:
        resp = client.get("/cachedcode", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://cached.com/"
        mock_cache.return_value.incr.assert_called_with("clicks:cachedcode")


def test_follow_cache_miss_db_hit(client):
    with patch.object(cache, "get_json", return_value=None), \
         patch.object(db, "one", return_value={"id": 99, "url": "https://from-db.com/"}), \
         patch.object(cache, "set_json") as mock_set_cache, \
         patch.object(db, "query"), \
         patch.object(cache, "client") as mock_cache:
        resp = client.get("/dbcode", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://from-db.com/"
        mock_set_cache.assert_called_once()
        mock_cache.return_value.incr.assert_called_with("clicks:dbcode")


def test_follow_not_found(client):
    with patch.object(cache, "get_json", return_value=None), \
         patch.object(db, "one", return_value=None):
        resp = client.get("/missingcode", follow_redirects=False)
        assert resp.status_code == 404


# ============================================================================
# Test Cache Helpers
# ============================================================================

def test_cache_helpers():
    with patch.object(cache, "client") as mock_client:
        mock_redis = MagicMock()
        mock_client.return_value = mock_redis

        # test set_json
        cache.set_json("test_key", {"foo": "bar"}, ttl=120)
        mock_redis.set.assert_called_once()

        # test get_json
        mock_redis.get.return_value = '{"foo": "bar"}'
        assert cache.get_json("test_key") == {"foo": "bar"}
        mock_redis.get.return_value = None
        assert cache.get_json("test_key") is None

        # test drop
        cache.drop("k1", "k2")
        mock_redis.delete.assert_called_with("k1", "k2")

        # test drop_prefix
        mock_redis.scan_iter.return_value = ["link:1", "link:2"]
        cache.drop_prefix("link:")
        assert mock_redis.delete.call_count >= 2


# ============================================================================
# Test DB Helpers
# ============================================================================

def test_db_helpers():
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"}):
        assert db.url() == "postgresql://test:test@localhost/test"
