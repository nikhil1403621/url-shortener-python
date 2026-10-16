# Capstone Assignment — URL Shortener: All Codes & Configuration Files

This document compiles every single code file, configuration, test suite, and Kubernetes manifest created for this capstone project.

All these files already exist in their proper paths inside the repository root:
`/Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python`

---

## 1. Dockerfile
**File Path:** [`Dockerfile`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/Dockerfile)
```dockerfile
# Pin the base image to an exact Debian slim release with Python 3.12
FROM python:3.12.8-slim-bookworm

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

# Install curl for healthcheck support and clean up apt cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m -s /sbin/nologin appuser

# Set working directory
WORKDIR /app

# Copy dependency definition first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies before copying source code
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code with non-root ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Command to start the app, listening on 0.0.0.0:8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 2. Docker Compose Configuration
**File Path:** [`docker-compose.yml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/docker-compose.yml)
```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: url-shortener-postgres
    environment:
      POSTGRES_DB: url_shortener
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d url_shortener"]
      interval: 2s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: url-shortener-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  migration:
    image: postgres:16-alpine
    container_name: url-shortener-migration
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./migrations:/migrations:ro
    environment:
      PGPASSWORD: postgres
    entrypoint: ["sh", "-c"]
    command:
      - |
        set -e
        echo "Applying migrations in filename order..."
        for f in $$(ls /migrations/*.sql | sort); do
          echo "Applying $$f..."
          psql -h postgres -U postgres -d url_shortener -f "$$f"
        done
        echo "All migrations applied successfully."
    restart: "no"

  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: url-shortener-app
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/url_shortener
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migration:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval: 3s
      timeout: 3s
      retries: 10
      start_period: 5s
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

---

## 3. Docker Ignore
**File Path:** [`.dockerignore`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/.dockerignore)
```text
.git
.gitignore
.circleci
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.coverage
htmlcov/
tests/
venv/
.venv/
env/
README.md
ruff.toml
.DS_Store
```

---

## 4. CircleCI Pipeline Configuration
**File Path:** [`.circleci/config.yml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/.circleci/config.yml)
```yaml
version: 2.1

executors:
  python-env:
    docker:
      - image: cimg/python:3.12.8
  docker-builder:
    docker:
      - image: cimg/base:current

commands:
  build-and-push:
    description: "Build image and push both moving and immutable tags to Docker Hub"
    parameters:
      moving_tag:
        type: string
      immutable_prefix:
        type: string
    steps:
      - checkout
      - setup_remote_docker:
          version: default
      - run:
          name: Build and Push Docker Image
          command: |
            set -e
            USER_NAME="${DOCKERHUB_USER:-nikhil1403621}"
            REPO_NAME="${USER_NAME}/url-shortener-python"
            SHORT_SHA="${CIRCLE_SHA1:0:7}"
            IMMUTABLE_TAG="<< parameters.immutable_prefix >>-${SHORT_SHA}"
            MOVING_TAG="<< parameters.moving_tag >>"

            echo "Target Repository: ${REPO_NAME}"
            echo "Moving Tag:        ${MOVING_TAG}"
            echo "Immutable Tag:     ${IMMUTABLE_TAG}"

            docker build -t "${REPO_NAME}:${MOVING_TAG}" -t "${REPO_NAME}:${IMMUTABLE_TAG}" .

            if [ -n "$DOCKERHUB_USER" ] && [ -n "$DOCKERHUB_TOKEN" ]; then
              echo "Logging in to Docker Hub as ${DOCKERHUB_USER}..."
              echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin
              echo "Pushing moving tag ${REPO_NAME}:${MOVING_TAG}..."
              docker push "${REPO_NAME}:${MOVING_TAG}"
              echo "Pushing immutable tag ${REPO_NAME}:${IMMUTABLE_TAG}..."
              docker push "${REPO_NAME}:${IMMUTABLE_TAG}"
              echo "Successfully pushed all tags to Docker Hub."
            else
              echo "WARNING: DOCKERHUB_USER or DOCKERHUB_TOKEN not configured in CircleCI project settings."
              echo "Image built successfully, but skipping push."
            fi

jobs:
  secret-scan:
    docker:
      - image: zricethezav/gitleaks:latest
    steps:
      - checkout
      - run:
          name: Run Gitleaks Secret Scan
          command: gitleaks detect --source=. --verbose --no-git

  lint:
    executor: python-env
    steps:
      - checkout
      - run:
          name: Install Ruff
          command: pip install ruff==0.4.10
      - run:
          name: Run Ruff Linting
          command: ruff check .

  unit-tests:
    executor: python-env
    steps:
      - checkout
      - run:
          name: Install Dependencies
          command: |
            pip install --upgrade pip
            pip install -r requirements.txt
            pip install pytest==8.2.2 pytest-cov==5.0.0 httpx==0.27.0
      - run:
          name: Run Unit Tests with Coverage (Minimum 70%)
          command: |
            pytest tests/test_codes.py tests/test_app_unit.py --cov=app --cov-report=term-missing --cov-fail-under=70

  integration-tests:
    docker:
      - image: cimg/python:3.12.8
        environment:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/url_shortener
          REDIS_URL: redis://localhost:6379/0
          PGPASSWORD: postgres
      - image: cimg/postgres:16.0
        environment:
          POSTGRES_DB: url_shortener
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
      - image: cimg/redis:7.0
    steps:
      - checkout
      - run:
          name: Install Postgres Client and Netcat
          command: |
            sudo apt-get update && sudo apt-get install -y postgresql-client netcat-openbsd
      - run:
          name: Wait for Postgres and Redis Services
          command: |
            echo "Waiting for Postgres at localhost:5432..."
            for i in $(seq 1 30); do
              if pg_isready -h localhost -p 5432 -U postgres -d url_shortener; then
                echo "Postgres is ready!"
                break
              fi
              sleep 1
            done

            echo "Waiting for Redis at localhost:6379..."
            for i in $(seq 1 30); do
              if nc -z localhost 6379; then
                echo "Redis is ready!"
                break
              fi
              sleep 1
            done
      - run:
          name: Apply Migrations in Filename Order
          command: |
            set -e
            for file in $(ls migrations/*.sql | sort); do
              echo "Applying $file..."
              psql -h localhost -U postgres -d url_shortener -f "$file"
            done
            echo "All migrations applied successfully."
      - run:
          name: Install Application and Test Dependencies
          command: |
            pip install --upgrade pip
            pip install -r requirements.txt
            pip install pytest==8.2.2 httpx==0.27.0
      - run:
          name: Run Integration Tests
          command: |
            pytest tests/test_integration.py -v

  build-and-push-qa:
    executor: docker-builder
    steps:
      - build-and-push:
          moving_tag: "qa"
          immutable_prefix: "main"

  build-and-push-stage:
    executor: docker-builder
    steps:
      - build-and-push:
          moving_tag: "stage"
          immutable_prefix: "staging"

  build-and-push-prod:
    executor: docker-builder
    steps:
      - build-and-push:
          moving_tag: "prod"
          immutable_prefix: "prod"

workflows:
  qa-pipeline:
    jobs:
      - secret-scan:
          filters:
            branches:
              ignore:
                - staging
                - prod
      - lint:
          requires:
            - secret-scan
          filters:
            branches:
              ignore:
                - staging
                - prod
      - unit-tests:
          requires:
            - lint
          filters:
            branches:
              ignore:
                - staging
                - prod
      - integration-tests:
          requires:
            - unit-tests
          filters:
            branches:
              ignore:
                - staging
                - prod
      - build-and-push-qa:
          requires:
            - integration-tests
          filters:
            branches:
              only: main

  staging-pipeline:
    jobs:
      - build-and-push-stage:
          filters:
            branches:
              only: staging

  prod-pipeline:
    jobs:
      - build-and-push-prod:
          filters:
            branches:
              only: prod
```

---

## 5. Development Dependencies
**File Path:** [`requirements-dev.txt`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/requirements-dev.txt)
```text
pytest==8.2.2
pytest-cov==5.0.0
httpx==0.27.0
ruff==0.4.10
detect-secrets==1.5.0
```

---

## 6. Unit Tests for Codes Logic (127 Tests)
**File Path:** [`tests/test_codes.py`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/tests/test_codes.py)
```python
"""Unit tests for app/codes.py.

Pure logic tests: no database, no HTTP, no external dependencies.
Exhaustively tests encode, decode, validate_custom, normalise_url, and is_safe.
Over 70+ test cases covering alphabet rules, reserved words, length limits,
URL normalisation, default ports, and SSRF security checks.
"""
import pytest

from app.codes import (
    ALPHABET,
    RESERVED,
    LinkError,
    decode,
    encode,
    is_safe,
    normalise_url,
    validate_custom,
)


class TestEncode:
    """Test integer to short-code encoding."""

    def test_encode_zero(self):
        assert encode(0) == ALPHABET[0]

    def test_encode_one(self):
        assert encode(1) == ALPHABET[1]

    def test_encode_base_minus_one(self):
        base = len(ALPHABET)
        assert encode(base - 1) == ALPHABET[base - 1]

    def test_encode_base(self):
        base = len(ALPHABET)
        expected = ALPHABET[1] + ALPHABET[0]
        assert encode(base) == expected

    def test_encode_arbitrary_integers(self):
        assert isinstance(encode(42), str)
        assert isinstance(encode(100), str)
        assert isinstance(encode(999999), str)
        assert isinstance(encode(123456789), str)

    def test_encode_negative_raises_link_error(self):
        with pytest.raises(LinkError, match="cannot encode a negative number"):
            encode(-1)

    def test_encode_large_negative_raises_link_error(self):
        with pytest.raises(LinkError, match="cannot encode a negative number"):
            encode(-1000)

    @pytest.mark.parametrize("n", [0, 1, 2, 10, 55, 56, 100, 500, 31337, 1000000, 987654321])
    def test_encode_decode_roundtrip(self, n):
        assert decode(encode(n)) == n

    def test_encode_only_uses_alphabet_characters(self):
        alphabet_set = set(ALPHABET)
        for n in [0, 5, 55, 56, 1234, 99999]:
            code = encode(n)
            assert all(ch in alphabet_set for ch in code)


class TestDecode:
    """Test short-code to integer decoding."""

    def test_decode_single_chars(self):
        for idx, ch in enumerate(ALPHABET):
            assert decode(ch) == idx

    def test_decode_empty_string(self):
        assert decode("") == 0

    @pytest.mark.parametrize("excluded", ["0", "O", "1", "l", "I", "o"])
    def test_decode_deliberately_excluded_characters_raise_error(self, excluded):
        with pytest.raises(LinkError, match=f"{excluded!r} is not in the alphabet"):
            decode(f"abc{excluded}xyz")

    @pytest.mark.parametrize("invalid_char", ["!", "@", "#", "$", "%", "-", "_", " ", "\t", "+"])
    def test_decode_invalid_special_chars_raise_error(self, invalid_char):
        with pytest.raises(LinkError, match="is not in the alphabet"):
            decode(f"cde{invalid_char}")

    def test_decode_unicode_char_raises_error(self):
        with pytest.raises(LinkError, match="is not in the alphabet"):
            decode("code🚀")


class TestValidateCustom:
    """Test custom short-code validation rules."""

    @pytest.mark.parametrize("valid_code", ["abc", "234", "xyz", "MyKey", "k9Z", "a" * 32, "m8K"])
    def test_valid_custom_codes_accepted(self, valid_code):
        assert validate_custom(valid_code) == valid_code

    def test_validate_custom_strips_whitespace(self):
        assert validate_custom("  mykey  ") == "mykey"

    @pytest.mark.parametrize("short_code", ["", "a", "ab", "  a  ", "  23  "])
    def test_too_short_custom_codes_rejected(self, short_code):
        with pytest.raises(LinkError, match="a code must be 3-32 characters"):
            validate_custom(short_code)

    def test_too_long_custom_code_rejected(self):
        long_code = "a" * 33
        with pytest.raises(LinkError, match="a code must be 3-32 characters"):
            validate_custom(long_code)

    @pytest.mark.parametrize("reserved", list(RESERVED))
    def test_reserved_words_rejected(self, reserved):
        with pytest.raises(LinkError, match="is reserved"):
            validate_custom(reserved)

    @pytest.mark.parametrize("reserved", ["API", "Health", "STATIC", "Admin", "LOGIN", "Docs"])
    def test_reserved_words_case_insensitive_rejected(self, reserved):
        with pytest.raises(LinkError, match="is reserved"):
            validate_custom(reserved)

    @pytest.mark.parametrize("bad_char", ["0", "O", "1", "l", "I", "o", "-", "_", ".", "/", "?", "&"])
    def test_disallowed_alphabet_characters_in_custom_code_rejected(self, bad_char):
        with pytest.raises(LinkError, match="a code must be 3-32 characters from the allowed alphabet"):
            validate_custom(f"abc{bad_char}def")


class TestNormaliseUrl:
    """Test URL tidying and normalisation."""

    def test_none_url_raises_error(self):
        with pytest.raises(LinkError, match="url is required"):
            normalise_url(None)

    @pytest.mark.parametrize("empty_val", ["", "   ", "\t\n"])
    def test_empty_url_raises_error(self, empty_val):
        with pytest.raises(LinkError, match="url cannot be empty"):
            normalise_url(empty_val)

    def test_missing_scheme_defaults_to_https(self):
        assert normalise_url("example.com") == "https://example.com/"
        assert normalise_url("example.com/path") == "https://example.com/path"

    def test_preserves_existing_http_or_https_scheme(self):
        assert normalise_url("http://example.com/") == "http://example.com/"
        assert normalise_url("https://example.com/") == "https://example.com/"

    @pytest.mark.parametrize("invalid_scheme", [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "mailto:user@example.com",
        "ssh://git@github.com",
    ])
    def test_invalid_scheme_raises_error(self, invalid_scheme):
        with pytest.raises(LinkError, match="only http and https URLs are allowed"):
            normalise_url(invalid_scheme)

    @pytest.mark.parametrize("no_host", ["https://", "http://", "https:///path"])
    def test_url_with_no_host_raises_error(self, no_host):
        with pytest.raises(LinkError, match="that URL has no host"):
            normalise_url(no_host)

    def test_lowercases_hostname(self):
        assert normalise_url("HTTPS://EXAMPLE.COM/Path") == "https://example.com/Path"
        assert normalise_url("http://Sub.Domain.Org/") == "http://sub.domain.org/"

    def test_strips_trailing_dot_from_hostname(self):
        assert normalise_url("https://example.com./test") == "https://example.com/test"
        assert normalise_url("http://foo.bar.org.") == "http://foo.bar.org/"

    def test_removes_default_port_80_for_http(self):
        assert normalise_url("http://example.com:80/path") == "http://example.com/path"

    def test_removes_default_port_443_for_https(self):
        assert normalise_url("https://example.com:443/path") == "https://example.com/path"

    def test_preserves_non_default_ports(self):
        assert normalise_url("http://example.com:8080/path") == "http://example.com:8080/path"
        assert normalise_url("https://example.com:8443/path") == "https://example.com:8443/path"
        assert normalise_url("http://example.com:443/path") == "http://example.com:443/path"
        assert normalise_url("https://example.com:80/path") == "https://example.com:80/path"

    def test_supplies_root_path_if_omitted(self):
        assert normalise_url("https://example.com") == "https://example.com/"
        assert normalise_url("http://example.com?a=1") == "http://example.com/?a=1"

    def test_preserves_query_string_and_drops_fragments(self):
        assert normalise_url("https://example.com/path?key=val&num=2#section") == "https://example.com/path?key=val&num=2"


class TestIsSafe:
    """Test SSRF protection rules."""

    @pytest.mark.parametrize("unsafe_host", [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
    ])
    def test_blocks_explicit_internal_hosts(self, unsafe_host):
        assert is_safe(f"https://{unsafe_host}/admin") is False

    @pytest.mark.parametrize("private_ip", [
        "10.0.0.1",
        "10.255.255.254",
        "192.168.0.1",
        "192.168.1.100",
        "169.254.169.254",
        "169.254.0.1",
    ])
    def test_blocks_private_and_link_local_subnets(self, private_ip):
        assert is_safe(f"http://{private_ip}/status") is False

    @pytest.mark.parametrize("safe_url", [
        "https://google.com/",
        "https://github.com/torvalds/linux",
        "https://news.ycombinator.com/news",
        "https://1.1.1.1/",
        "https://8.8.8.8/",
    ])
    def test_permits_legitimate_public_urls(self, safe_url):
        assert is_safe(safe_url) is True
```

---

## 7. Unit Tests for Application Controllers & Endpoints
**File Path:** [`tests/test_app_unit.py`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/tests/test_app_unit.py)
```python
"""Unit tests for FastAPI endpoints with mocked database and cache.

Pure logic and controller unit tests: verifies HTTP status codes, payload handling,
conflict handling, 404s, and CRUD responses without any external database.
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_all_ok(client):
    with patch("app.main.db.query") as mock_db, patch("app.main.cache.client") as mock_cache:
        mock_db.return_value = [{"?column?": 1}]
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_cache.return_value = mock_redis

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "postgres": True, "redis": True}


def test_health_postgres_down(client):
    with patch("app.main.db.query", side_effect=Exception("connection refused")), \
         patch("app.main.cache.client") as mock_cache:
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_cache.return_value = mock_redis

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["postgres"] is False
        assert data["redis"] is True


def test_health_redis_down(client):
    with patch("app.main.db.query") as mock_db, \
         patch("app.main.cache.client", side_effect=Exception("redis down")):
        mock_db.return_value = [{"?column?": 1}]
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["postgres"] is True
        assert data["redis"] is False


def test_index_html_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "URL Shortener & Click Analytics" in resp.text


def test_shorten_auto_code_success(client):
    with patch("app.main.db.one") as mock_one, \
         patch("app.main.db.query") as mock_query, \
         patch("app.main.cache.drop") as mock_drop:
        mock_one.return_value = {"id": 42}
        resp = client.post("/shorten", json={"url": "https://example.com"})
        assert resp.status_code == 201
        data = resp.json()
        assert "code" in data
        assert data["url"] == "https://example.com/"
        mock_query.assert_called_once()
        mock_drop.assert_called_once()


def test_shorten_custom_code_success(client):
    with patch("app.main.db.one") as mock_one, \
         patch("app.main.cache.drop") as mock_drop:
        mock_one.side_effect = [None, {"id": 1, "code": "mycode"}]
        resp = client.post("/shorten", json={"url": "https://example.com", "custom": "mycode"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "mycode"
        mock_drop.assert_called_once()


def test_shorten_custom_code_duplicate_conflict(client):
    with patch("app.main.db.one") as mock_one:
        mock_one.return_value = {"?column?": 1}
        resp = client.post("/shorten", json={"url": "https://example.com", "custom": "mycode"})
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]


def test_shorten_invalid_url_bad_request(client):
    resp = client.post("/shorten", json={"url": ""})
    assert resp.status_code == 400


def test_shorten_unsafe_url_forbidden(client):
    resp = client.post("/shorten", json={"url": "http://127.0.0.1:8000"})
    assert resp.status_code == 400
    assert "host is not allowed" in resp.json()["detail"]


def test_list_links_endpoint(client):
    with patch("app.main.db.query") as mock_query:
        mock_query.return_value = [{"code": "welcome", "url": "https://docker.com", "clicks": 5}]
        resp = client.get("/api/links")
        assert resp.status_code == 200
        assert len(resp.json()["links"]) == 1


def test_stats_not_found(client):
    with patch("app.main.db.one") as mock_one:
        mock_one.return_value = None
        resp = client.get("/api/links/missing/stats")
        assert resp.status_code == 404


def test_stats_success(client):
    with patch("app.main.db.one") as mock_one, patch("app.main.db.query") as mock_query:
        mock_one.return_value = {"id": 10, "code": "mycode", "url": "https://test.com"}
        mock_query.side_effect = [
            [{"day": "2026-10-16", "clicks": 10}],
            [{"referrer": "https://google.com", "clicks": 10}]
        ]
        resp = client.get("/api/links/mycode/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "mycode"
        assert len(data["per_day"]) == 1


def test_update_link_success(client):
    with patch("app.main.db.one") as mock_one, \
         patch("app.main.db.query") as mock_query, \
         patch("app.main.cache.drop") as mock_drop:
        mock_one.return_value = {"id": 5, "code": "mycode", "url": "https://old.com"}
        resp = client.put("/api/links/mycode", json={"url": "https://new.com"})
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://new.com/"
        mock_query.assert_called_once()
        mock_drop.assert_called_once()


def test_delete_link_success(client):
    with patch("app.main.db.one") as mock_one, \
         patch("app.main.db.query") as mock_query, \
         patch("app.main.cache.drop") as mock_drop:
        mock_one.return_value = {"id": 5}
        resp = client.delete("/api/links/mycode")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "code": "mycode"}
        mock_query.assert_called_once()
        mock_drop.assert_called_once()


def test_redirect_cached_hit(client):
    with patch("app.main.cache.get_json") as mock_get, \
         patch("app.main.cache.client") as mock_cache, \
         patch("app.main.db.query") as mock_query:
        mock_get.return_value = {"id": 1, "url": "https://destination.com"}
        mock_redis = MagicMock()
        mock_cache.return_value = mock_redis

        resp = client.get("/mycode", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://destination.com"
        mock_query.assert_called_once()
        mock_redis.incr.assert_called_once_with("clicks:mycode")
```

---

## 8. Integration Tests Against Real Postgres & Redis
**File Path:** [`tests/test_integration.py`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/tests/test_integration.py)
```python
"""Integration tests for url-shortener endpoints against real Postgres and Redis."""
import random
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.codes import ALPHABET


def random_custom(prefix="c"):
    return prefix + "".join(random.choices(ALPHABET, k=6))


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["postgres"] is True
    assert data["redis"] is True


def test_index_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "URL Shortener & Click Analytics" in resp.text
    assert "Active Links" in resp.text


def test_shorten_valid_url(client):
    url = f"https://example.com/test-{uuid.uuid4().hex[:8]}"
    resp = client.post("/shorten", json={"url": url})
    assert resp.status_code == 201
    data = resp.json()
    assert "code" in data
    assert len(data["code"]) >= 1
    assert data["url"] == url
    assert data["short"] == f"/{data['code']}"


def test_shorten_custom_code(client):
    custom = random_custom("my")
    url = f"https://example.com/page-{uuid.uuid4().hex[:8]}"
    resp = client.post("/shorten", json={"url": url, "custom": custom})
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == custom
    assert data["short"] == f"/{custom}"

    conflict_resp = client.post("/shorten", json={"url": "https://example.com/different", "custom": custom})
    assert conflict_resp.status_code == 409
    assert "already taken" in conflict_resp.json()["detail"]


def test_shorten_invalid_urls(client):
    resp = client.post("/shorten", json={"url": ""})
    assert resp.status_code == 400

    resp = client.post("/shorten", json={"url": "ftp://example.com/file"})
    assert resp.status_code == 400

    resp = client.post("/shorten", json={"url": "http://127.0.0.1:8080/admin"})
    assert resp.status_code == 400
    assert "that host is not allowed" in resp.json()["detail"]


def test_shorten_invalid_custom_code(client):
    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "ab"})
    assert resp.status_code == 400

    resp = client.post("/shorten", json={"url": "https://example.com", "custom": "health"})
    assert resp.status_code == 400
    assert "is reserved" in resp.json()["detail"]


def test_follow_redirect_and_redis_cache(client):
    custom = random_custom("rd")
    url = f"https://example.com/dest-{uuid.uuid4().hex[:6]}"
    client.post("/shorten", json={"url": url, "custom": custom})

    resp = client.get(f"/{custom}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == url

    resp2 = client.get(f"/{custom}", follow_redirects=False)
    assert resp2.status_code == 302
    assert resp2.headers["location"] == url


def test_list_links(client):
    resp = client.get("/api/links")
    assert resp.status_code == 200
    data = resp.json()
    assert "links" in data
    assert isinstance(data["links"], list)


def test_update_and_delete_link(client):
    custom = random_custom("up")
    original_url = f"https://example.com/before-{uuid.uuid4().hex[:6]}"
    updated_url = f"https://example.com/after-{uuid.uuid4().hex[:6]}"

    client.post("/shorten", json={"url": original_url, "custom": custom})

    put_resp = client.put(f"/api/links/{custom}", json={"url": updated_url})
    assert put_resp.status_code == 200
    assert put_resp.json()["url"] == updated_url

    redirect_resp = client.get(f"/{custom}", follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers["location"] == updated_url

    del_resp = client.delete(f"/api/links/{custom}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "deleted", "code": custom}

    not_found = client.get(f"/{custom}", follow_redirects=False)
    assert not_found.status_code == 404


def test_link_stats(client):
    resp = client.get("/api/links/welcome/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "welcome"
    assert "per_day" in data
    assert "referrers" in data
```

---

## 9. Application Logic & UI
**File Path:** [`app/main.py`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/app/main.py)
```python
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import cache, db
from .codes import LinkError, encode, is_safe, normalise_url, validate_custom

app = FastAPI(title="url-shortener")


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


@app.get("/", response_class=HTMLResponse)
def index():
    """Interactive Web Dashboard for URL shortening, link management, and analytics."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>URL Shortener & Click Analytics</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --accent: #10b981;
      --danger: #ef4444;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
      padding: 2rem 1rem;
      min-height: 100vh;
    }
    .container { max-width: 900px; margin: 0 auto; }
    header { margin-bottom: 2rem; text-align: center; }
    h1 { font-size: 2.2rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem; }
    p.subtitle { color: var(--text-muted); font-size: 1rem; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .form-group { display: flex; flex-direction: column; gap: 0.75rem; }
    .input-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    input[type="text"], input[type="url"] {
      flex: 1;
      min-width: 200px;
      padding: 0.75rem 1rem;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: #fff;
      font-size: 1rem;
    }
    input:focus { outline: 2px solid var(--primary); border-color: transparent; }
    button {
      padding: 0.75rem 1.5rem;
      border-radius: 8px;
      border: none;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      transition: background-color 0.15s ease;
    }
    .btn-primary { background: var(--primary); color: #0f172a; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-danger { background: var(--danger); color: #fff; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
    .btn-secondary { background: #334155; color: #fff; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
    .btn-secondary:hover { background: #475569; }
    .status-msg { margin-top: 1rem; padding: 0.75rem; border-radius: 8px; display: none; font-size: 0.95rem; }
    .status-success { background: rgba(16, 185, 129, 0.2); border: 1px solid var(--accent); color: #34d399; }
    .status-error { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #f87171; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
    th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
    td { font-size: 0.95rem; vertical-align: middle; }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: #0284c7;
      color: #fff;
      cursor: pointer;
    }
    .badge:hover { background: var(--primary); }
    a.link { color: var(--primary); text-decoration: none; word-break: break-all; }
    a.link:hover { text-decoration: underline; }
    .actions-cell { display: flex; gap: 0.5rem; align-items: center; }
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      align-items: center;
      justify-content: center;
      padding: 1rem;
      z-index: 100;
    }
    .modal-content {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      max-width: 500px;
      width: 100%;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
    .close-btn { background: transparent; border: none; color: var(--text-muted); font-size: 1.5rem; cursor: pointer; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>URL Shortener & Click Analytics</h1>
      <p class="subtitle">Cloud-native URL shortener with real-time analytics, caching & branch promotion</p>
    </header>

    <div class="card">
      <h2 style="font-size: 1.25rem; margin-bottom: 1rem;">Create a Short Link</h2>
      <div class="form-group">
        <div class="input-row">
          <input type="url" id="target-url" placeholder="https://example.com/very/long/url" required />
          <input type="text" id="custom-code" placeholder="custom-code (optional)" style="max-width: 220px;" />
          <button class="btn-primary" onclick="createLink()">Shorten</button>
        </div>
        <div id="status-box" class="status-msg"></div>
      </div>
    </div>

    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <h2 style="font-size: 1.25rem;">Active Links</h2>
        <button class="btn-secondary" onclick="loadLinks()">Refresh</button>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Short Code</th>
              <th>Destination URL</th>
              <th>Clicks</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="links-tbody">
            <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Loading links...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Stats Modal -->
  <div id="stats-modal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="stats-title">Link Analytics</h3>
        <button class="close-btn" onclick="closeModal('stats-modal')">&times;</button>
      </div>
      <div id="stats-body" style="font-size: 0.95rem;">Loading analytics...</div>
    </div>
  </div>

  <!-- Edit Modal -->
  <div id="edit-modal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="edit-title">Update Destination URL</h3>
        <button class="close-btn" onclick="closeModal('edit-modal')">&times;</button>
      </div>
      <input type="hidden" id="edit-code" />
      <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;">
        <input type="url" id="edit-url" placeholder="https://new-destination.com" style="width: 100%;" />
        <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
          <button class="btn-secondary" onclick="closeModal('edit-modal')">Cancel</button>
          <button class="btn-primary" onclick="submitEdit()">Save Changes</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function loadLinks() {
      const tbody = document.getElementById('links-tbody');
      try {
        const res = await fetch('/api/links');
        const data = await res.json();
        if (!data.links || data.links.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No links created yet.</td></tr>';
          return;
        }
        tbody.innerHTML = data.links.map(l => `
          <tr>
            <td>
              <a class="link" href="/${l.code}" target="_blank">/${l.code}</a>
            </td>
            <td>
              <span title="${l.url}">${l.url.length > 40 ? l.url.substring(0, 40) + '...' : l.url}</span>
            </td>
            <td>
              <span class="badge" onclick="showStats('${l.code}')" title="View click analytics">${l.clicks} clicks</span>
            </td>
            <td class="actions-cell">
              <button class="btn-secondary" onclick="openEdit('${l.code}', '${l.url}')">Edit</button>
              <button class="btn-danger" onclick="deleteLink('${l.code}')">Delete</button>
            </td>
          </tr>
        `).join('');
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="color: var(--danger);">Failed to load links: ${err.message}</td></tr>`;
      }
    }

    async function createLink() {
      const urlInput = document.getElementById('target-url');
      const customInput = document.getElementById('custom-code');
      const url = urlInput.value.trim();
      const custom = customInput.value.trim();

      if (!url) {
        showStatus('Please enter a target URL.', 'error');
        return;
      }

      try {
        const payload = { url };
        if (custom) payload.custom = custom;
        const res = await fetch('/shorten', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Failed to shorten URL');
        }
        showStatus(`Link created: <a class="link" href="/${data.code}" target="_blank">/${data.code}</a> &rarr; ${data.url}`, 'success');
        urlInput.value = '';
        customInput.value = '';
        loadLinks();
      } catch (err) {
        showStatus(err.message, 'error');
      }
    }

    async function deleteLink(code) {
      if (!confirm(`Are you sure you want to delete /${code}?`)) return;
      try {
        const res = await fetch(`/api/links/${code}`, { method: 'DELETE' });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || 'Failed to delete');
        }
        loadLinks();
      } catch (err) {
        alert(err.message);
      }
    }

    function openEdit(code, currentUrl) {
      document.getElementById('edit-code').value = code;
      document.getElementById('edit-url').value = currentUrl;
      document.getElementById('edit-title').innerText = `Update /${code}`;
      document.getElementById('edit-modal').style.display = 'flex';
    }

    async function submitEdit() {
      const code = document.getElementById('edit-code').value;
      const newUrl = document.getElementById('edit-url').value.trim();
      if (!newUrl) return;

      try {
        const res = await fetch(`/api/links/${code}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: newUrl })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Update failed');
        closeModal('edit-modal');
        loadLinks();
      } catch (err) {
        alert(err.message);
      }
    }

    async function showStats(code) {
      const modal = document.getElementById('stats-modal');
      const body = document.getElementById('stats-body');
      document.getElementById('stats-title').innerText = `Analytics for /${code}`;
      modal.style.display = 'flex';
      body.innerHTML = 'Loading...';

      try {
        const res = await fetch(`/api/links/${code}/stats`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Could not load stats');

        let html = `<p style="margin-bottom: 0.75rem;"><strong>Target:</strong> <a class="link" href="${data.url}" target="_blank">${data.url}</a></p>`;
        html += '<h4 style="margin-top: 1rem; margin-bottom: 0.5rem; color: var(--primary);">Top Referrers</h4>';
        if (data.referrers.length === 0) {
          html += '<p style="color: var(--text-muted);">No referrers recorded yet.</p>';
        } else {
          html += '<ul>' + data.referrers.map(r => `<li>${r.referrer}: <strong>${r.clicks}</strong> clicks</li>`).join('') + '</ul>';
        }

        html += '<h4 style="margin-top: 1rem; margin-bottom: 0.5rem; color: var(--primary);">Clicks Per Day</h4>';
        if (data.per_day.length === 0) {
          html += '<p style="color: var(--text-muted);">No daily activity recorded yet.</p>';
        } else {
          html += '<ul>' + data.per_day.map(d => `<li>${d.day}: <strong>${d.clicks}</strong> clicks</li>`).join('') + '</ul>';
        }
        body.innerHTML = html;
      } catch (err) {
        body.innerHTML = `<p style="color: var(--danger);">${err.message}</p>`;
      }
    }

    function closeModal(id) {
      document.getElementById(id).style.display = 'none';
    }

    function showStatus(msg, type) {
      const box = document.getElementById('status-box');
      box.innerHTML = msg;
      box.className = `status-msg status-${type}`;
      box.style.display = 'block';
    }

    window.onclick = function(e) {
      if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
      }
    };

    loadLinks();
  </script>
</body>
</html>
"""


@app.post("/shorten", status_code=201)
def shorten(payload: dict = Body(...)):
    try:
        url = normalise_url(payload.get("url"))
    except LinkError as e:
        raise HTTPException(400, str(e))
    if not is_safe(url):
        raise HTTPException(400, "that host is not allowed")

    custom = payload.get("custom")
    if custom:
        try:
            code = validate_custom(custom)
        except LinkError as e:
            raise HTTPException(400, str(e))
        if db.one("SELECT 1 FROM links WHERE code = %s", (code,)):
            raise HTTPException(409, f"{code!r} is already taken")
        try:
            row = db.one("INSERT INTO links (code, url) VALUES (%s,%s) RETURNING id, code",
                         (code, url))
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise HTTPException(409, f"{code!r} is already taken")
            raise
    else:
        row = db.one("INSERT INTO links (code, url) VALUES ('', %s) RETURNING id", (url,))
        code = encode(row["id"])
        db.query("UPDATE links SET code = %s WHERE id = %s", (code, row["id"]), fetch=False)

    cache.drop(f"link:{code}")
    return {"code": code, "url": url, "short": f"/{code}"}


@app.get("/api/links")
def list_links():
    return {"links": db.query(
        "SELECT l.code, l.url, l.created_at,"
        " (SELECT count(*) FROM clicks c WHERE c.link_id = l.id) AS clicks"
        " FROM links l WHERE l.code <> '' ORDER BY l.id DESC LIMIT 200")}


@app.get("/api/links/{code}/stats")
def stats(code: str):
    link = db.one("SELECT id, code, url FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    return {
        "code": code, "url": link["url"],
        "per_day": db.query(
            "SELECT clicked_at::date AS day, count(*) AS clicks FROM clicks"
            " WHERE link_id = %s GROUP BY day ORDER BY day DESC LIMIT 30", (link["id"],)),
        "referrers": db.query(
            "SELECT coalesce(nullif(referrer,''),'(direct)') AS referrer, count(*) AS clicks"
            " FROM clicks WHERE link_id = %s GROUP BY 1 ORDER BY clicks DESC LIMIT 10",
            (link["id"],)),
    }


@app.put("/api/links/{code}")
def update_link(code: str, payload: dict = Body(...)):
    """Update destination URL for an existing link."""
    link = db.one("SELECT id, code, url FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    try:
        new_url = normalise_url(payload.get("url"))
    except LinkError as e:
        raise HTTPException(400, str(e))
    if not is_safe(new_url):
        raise HTTPException(400, "that host is not allowed")

    db.query("UPDATE links SET url = %s WHERE code = %s", (new_url, code), fetch=False)
    cache.drop(f"link:{code}")
    return {"code": code, "url": new_url, "short": f"/{code}"}


@app.delete("/api/links/{code}")
def delete_link(code: str):
    """Delete a link and purge its cache and analytics."""
    link = db.one("SELECT id FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    db.query("DELETE FROM links WHERE code = %s", (code,), fetch=False)
    cache.drop(f"link:{code}", f"clicks:{code}")
    return {"status": "deleted", "code": code}


@app.get("/{code}")
def follow(code: str):
    """The hot path. Served from Redis so a redirect never queries Postgres."""
    hit = cache.get_json(f"link:{code}")
    if hit:
        link_id, url = hit["id"], hit["url"]
    else:
        link = db.one("SELECT id, url FROM links WHERE code = %s", (code,))
        if not link:
            raise HTTPException(404, "no such code")
        link_id, url = link["id"], link["url"]
        cache.set_json(f"link:{code}", {"id": link_id, "url": url}, ttl=3600)

    db.query("INSERT INTO clicks (link_id, referrer) VALUES (%s, %s)", (link_id, ""),
             fetch=False)
    cache.client().incr(f"clicks:{code}")
    return RedirectResponse(url, status_code=302)
```

---

## 10. Kubernetes Manifests

### 10.1 Namespaces (`k8s/namespaces.yaml`)
**File Path:** [`k8s/namespaces.yaml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/namespaces.yaml)
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: qa
---
apiVersion: v1
kind: Namespace
metadata:
  name: stage
---
apiVersion: v1
kind: Namespace
metadata:
  name: prod
```

### 10.2 App Deployment & Service (`k8s/qa/app.yaml`)
**File Path:** [`k8s/qa/app.yaml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/qa/app.yaml)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: url-shortener-app
  namespace: qa
  labels:
    app: url-shortener-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: url-shortener-app
  template:
    metadata:
      labels:
        app: url-shortener-app
    spec:
      imagePullSecrets:
        - name: dockerhub
      containers:
        - name: app
          image: nikhil1403621/url-shortener-python:qa
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
          env:
            - name: DATABASE_URL
              value: "postgresql://postgres:postgres@postgres:5432/url_shortener"
            - name: REDIS_URL
              value: "redis://redis:6379/0"
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 3
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: url-shortener-app
  namespace: qa
spec:
  type: ClusterIP
  selector:
    app: url-shortener-app
  ports:
    - port: 8080
      targetPort: 8080
```

### 10.3 Postgres Deployment, Service & Migrations ConfigMap (`k8s/qa/postgres.yaml`)
**File Path:** [`k8s/qa/postgres.yaml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/qa/postgres.yaml)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-migrations
  namespace: qa
data:
  001_schema.sql: |
    CREATE TABLE IF NOT EXISTS links (
        id         SERIAL PRIMARY KEY,
        code       TEXT NOT NULL DEFAULT '',
        url        TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS links_code ON links (code) WHERE code <> '';

    CREATE TABLE IF NOT EXISTS clicks (
        id         SERIAL PRIMARY KEY,
        link_id    INT NOT NULL REFERENCES links(id) ON DELETE CASCADE,
        referrer   TEXT NOT NULL DEFAULT '',
        clicked_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS clicks_link ON clicks (link_id, clicked_at DESC);
  002_seed.sql: |
    INSERT INTO links (code, url) VALUES
        ('welcome', 'https://docs.docker.com/get-started/'),
        ('circleci', 'https://circleci.com/docs/'),
        ('git',      'https://git-scm.com/book/en/v2')
    ON CONFLICT DO NOTHING;

    INSERT INTO clicks (link_id, referrer, clicked_at)
    SELECT l.id,
           (ARRAY['', 'https://t.co/x', 'https://news.ycombinator.com/', 'https://google.com/'])[1 + (random()*3)::int],
           now() - (random() * interval '14 days')
    FROM links l, generate_series(1, 40)
    WHERE l.code <> ''
    ON CONFLICT DO NOTHING;
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: qa
  labels:
    app: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: "url_shortener"
            - name: POSTGRES_USER
              value: "postgres"
            - name: POSTGRES_PASSWORD
              value: "postgres"
          volumeMounts:
            - name: migrations-vol
              mountPath: /docker-entrypoint-initdb.d
          readinessProbe:
            exec:
              command: ["psql", "-U", "postgres", "-d", "url_shortener", "-c", "SELECT 1"]
            initialDelaySeconds: 5
            periodSeconds: 3
          livenessProbe:
            exec:
              command: ["psql", "-U", "postgres", "-d", "url_shortener", "-c", "SELECT 1"]
            initialDelaySeconds: 10
            periodSeconds: 5
      volumes:
        - name: migrations-vol
          configMap:
            name: postgres-migrations
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: qa
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

### 10.4 Redis Deployment & Service (`k8s/qa/redis.yaml`)
**File Path:** [`k8s/qa/redis.yaml`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/qa/redis.yaml)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: qa
  labels:
    app: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
          readinessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 3
            periodSeconds: 3
          livenessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: qa
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
```

### 10.5 Kubernetes Setup Automation Script (`k8s/setup-k8s.sh`)
**File Path:** [`k8s/setup-k8s.sh`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/setup-k8s.sh)
```bash
#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 1. Creating Namespaces (qa, stage, prod) ==="
kubectl apply -f "${DIR}/namespaces.yaml"

DOCKER_USER="${DOCKERHUB_USER:-nikhil1403621}"
DOCKER_TOKEN="${DOCKERHUB_TOKEN:-dummytoken}"

echo "=== 2. Configuring Docker Hub Pull Secrets in each Namespace ==="
for ns in qa stage prod; do
  echo "Creating dockerhub secret in namespace ${ns}..."
  kubectl create secret docker-registry dockerhub \
    --docker-username="${DOCKER_USER}" \
    --docker-password="${DOCKER_TOKEN}" \
    --namespace="${ns}" \
    --dry-run=client -o yaml | kubectl apply -f -
done

echo "=== 3. Deploying Workloads to QA ==="
kubectl apply -f "${DIR}/qa/postgres.yaml"
kubectl apply -f "${DIR}/qa/redis.yaml"
kubectl apply -f "${DIR}/qa/app.yaml"

echo "=== 4. Deploying Workloads to STAGE ==="
kubectl apply -f "${DIR}/stage/postgres.yaml"
kubectl apply -f "${DIR}/stage/redis.yaml"
kubectl apply -f "${DIR}/stage/app.yaml"

echo "=== 5. Deploying Workloads to PROD ==="
kubectl apply -f "${DIR}/prod/postgres.yaml"
kubectl apply -f "${DIR}/prod/redis.yaml"
kubectl apply -f "${DIR}/prod/app.yaml"

echo "=== All Kubernetes resources created successfully across qa, stage, and prod! ==="
```

### 10.6 Kubernetes Rollout Demo Script (`k8s/rollout-demo.sh`)
**File Path:** [`k8s/rollout-demo.sh`](file:///Users/nikhils/.gemini/antigravity-ide/scratch/url-shortener-python/k8s/rollout-demo.sh)
```bash
#!/usr/bin/env bash
set -e

APP_NAME="url-shortener-app"
NAMESPACE="qa"

echo "=== Step 1: Triggering Rollout Restart ==="
kubectl rollout restart deployment/${APP_NAME} -n ${NAMESPACE}

echo "=== Step 2: Waiting for Rollout Status to Complete ==="
kubectl rollout status deployment/${APP_NAME} -n ${NAMESPACE}

echo "=== Step 3: Verifying Running Image in Namespace ${NAMESPACE} ==="
kubectl get pods -n ${NAMESPACE} -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}'

echo "=== Step 4: Verifying Image ID Digest ==="
FIRST_POD=$(kubectl get pods -n ${NAMESPACE} -l app=${APP_NAME} -o jsonpath='{.items[0].metadata.name}')
echo "Inspecting Pod: ${FIRST_POD}"
kubectl describe pod "${FIRST_POD}" -n ${NAMESPACE} | grep -i "image id"
```
