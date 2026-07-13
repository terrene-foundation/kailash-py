"""Regression: OTLP endpoint credential masking in the config log line (#1708 final redteam LOW-2).

Auth normally travels via OTEL_EXPORTER_OTLP_HEADERS (never logged), but a
pathological config can embed basic-auth in the endpoint URL. The config INFO
log must redact embedded userinfo — while leaving a normal credential-free
endpoint verbatim (no spurious ``***@``).
"""

import pytest

from kailash.observability.otlp import _mask_otlp_endpoint


@pytest.mark.regression
def test_credential_free_endpoint_logged_verbatim():
    assert _mask_otlp_endpoint("http://collector:4317") == "http://collector:4317"
    assert _mask_otlp_endpoint("https://otel.example.com:4318/v1/metrics") == (
        "https://otel.example.com:4318/v1/metrics"
    )


@pytest.mark.regression
def test_embedded_userinfo_is_masked():
    masked = _mask_otlp_endpoint("http://user:s3cret@collector:4317")
    assert "s3cret" not in masked
    assert "user" not in masked
    assert masked == "http://***@collector:4317"


@pytest.mark.regression
def test_none_and_empty_render_none_sentinel():
    assert _mask_otlp_endpoint(None) == "(none)"
    assert _mask_otlp_endpoint("") == "(none)"
