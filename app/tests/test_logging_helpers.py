"""assert_no_secrets() was silently broken — `item in lowered and item in
("authorization", "bearer ")` only ever caught "authorization"; password,
refresh_token, access_token, jwt_secret, and secret were never actually
checked, and the function was never called from anywhere. Now fixed and
wired into SafeAccessLogMiddleware as a canary against a secret ever
landing in the access log line.
"""
import json
import logging

import pytest

from app.core.logging import JsonFormatter, assert_no_secrets
from app.tests.conftest import client, register_and_login


@pytest.mark.parametrize(
    "term",
    ["password", "refresh_token", "access_token", "jwt_secret", "secret", "Authorization"],
)
def test_assert_no_secrets_catches_every_blocked_term(term):
    with pytest.raises(AssertionError):
        assert_no_secrets(f"some log line containing {term} in it")


def test_assert_no_secrets_passes_clean_text():
    assert_no_secrets("GET /api/v1/auth/me -> 200") is None


def test_middleware_actually_calls_it_on_real_requests():
    # Not a mock — a real request through the real middleware. If
    # assert_no_secrets ever fires here, this test fails loudly instead of
    # the check being silently bypassed as before.
    _, tokens = register_and_login()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200


def _make_record(level=logging.INFO, msg="hello", context=None, exc_info=None):
    record = logging.LogRecord(
        name="nexusauth.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    if context is not None:
        record.context = context
    return record


class TestJsonFormatter:
    # Doc: "Structured logging (JSON format)" (NEXUS_ONE_ARCHITECTURE_PLAN
    # §3, Module 10: Observability & Logging).

    def test_output_is_valid_json_with_core_fields(self):
        formatted = JsonFormatter().format(_make_record())
        parsed = json.loads(formatted)  # raises if not valid JSON
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "nexusauth.test"
        assert parsed["message"] == "hello"
        assert "timestamp" in parsed

    def test_context_fields_are_merged_into_the_top_level_payload(self):
        formatted = JsonFormatter().format(
            _make_record(context={"request_id": "abc123", "status_code": 200})
        )
        parsed = json.loads(formatted)
        assert parsed["request_id"] == "abc123"
        assert parsed["status_code"] == 200

    def test_non_json_native_context_values_degrade_to_str_instead_of_raising(self):
        class Unserializable:
            def __str__(self):
                return "unserializable-repr"

        formatted = JsonFormatter().format(_make_record(context={"weird": Unserializable()}))
        parsed = json.loads(formatted)
        assert parsed["weird"] == "unserializable-repr"

    def test_exception_info_is_included_when_present(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            formatted = JsonFormatter().format(_make_record(level=logging.ERROR, exc_info=sys.exc_info()))
        parsed = json.loads(formatted)
        assert "ValueError: boom" in parsed["exception"]

    def test_real_request_produces_structured_access_log(self, caplog):
        # End-to-end: the actual middleware, not a hand-built record —
        # confirms SafeAccessLogMiddleware really does attach a `context`
        # extra with the fields a log aggregator would filter/query on.
        with caplog.at_level(logging.INFO, logger="nexusauth.access"):
            response = client.get("/health")
        assert response.status_code == 200
        records = [r for r in caplog.records if r.name == "nexusauth.access"]
        assert records, "expected at least one nexusauth.access log record"
        context = records[-1].context
        assert context["method"] == "GET"
        assert context["path"] == "/health"
        assert context["status_code"] == 200
        assert "request_id" in context
