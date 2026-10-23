"""Liveness/readiness endpoints (Foundation Core observability requirement).

/health: is the process alive — no auth, no dependency checks.
/readiness: can this instance actually serve traffic — currently just
PostgreSQL. Both must never leak secrets/tracebacks/connection strings.
"""
from unittest.mock import patch

import main as main_module
from app.tests.conftest import client


def test_health_requires_no_auth_and_reports_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Module 10: Metadata & System Information — version is always present
    # (sourced from the FastAPI app's own version=); build_timestamp/git_sha
    # are optional deploy-time metadata and null unless the environment
    # sets them.
    assert body["version"] == main_module.app.version
    assert "build_timestamp" in body
    assert "git_sha" in body


def test_readiness_reports_ready_when_database_is_up():
    response = client.get("/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_readiness_reports_not_ready_when_database_is_down():
    secret_marker = "super-secret-connection-detail-should-never-leak"

    def _boom(*args, **kwargs):
        raise RuntimeError(secret_marker)

    with patch.object(main_module.engine, "connect", side_effect=_boom):
        response = client.get("/readiness")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "unavailable"
    # The real exception text (which could carry sensitive detail) must
    # never reach the client.
    assert secret_marker not in response.text


def test_readiness_response_has_no_secrets_or_stack_trace():
    response = client.get("/readiness")
    body_text = response.text.lower()
    for forbidden in ("password", "traceback", "secret", "postgresql://"):
        assert forbidden not in body_text
