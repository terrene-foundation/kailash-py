# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for fabric config types — construction, validation, env var checking.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from dataflow.fabric.config import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    CircuitBreakerConfig,
    CloudSourceConfig,
    DatabaseSourceConfig,
    FileSourceConfig,
    OAuth2Auth,
    RateLimit,
    RestSourceConfig,
    StalenessPolicy,
    StreamSourceConfig,
    WebhookConfig,
)


# ---------- Auth types ----------


class TestBearerAuth:
    def test_valid_construction(self):
        auth = BearerAuth(token_env="MY_TOKEN")
        assert auth.token_env == "MY_TOKEN"

    def test_empty_token_env_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            BearerAuth(token_env="")

    def test_get_token_reads_env(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        auth = BearerAuth(token_env="MY_TOKEN")
        assert auth.get_token() == "secret123"

    def test_get_token_raises_when_missing(self):
        auth = BearerAuth(token_env="NONEXISTENT_TOKEN_VAR_12345")
        with pytest.raises(ValueError, match="not set or empty"):
            auth.get_token()

    def test_frozen(self):
        auth = BearerAuth(token_env="TOK")
        with pytest.raises(AttributeError):
            auth.token_env = "OTHER"  # type: ignore[misc]


class TestApiKeyAuth:
    def test_valid_construction(self):
        auth = ApiKeyAuth(key_env="MY_KEY")
        assert auth.header == "X-API-Key"

    def test_custom_header(self):
        auth = ApiKeyAuth(key_env="MY_KEY", header="Authorization")
        assert auth.header == "Authorization"

    def test_empty_key_env_raises(self):
        with pytest.raises(ValueError):
            ApiKeyAuth(key_env="")

    def test_get_key(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "abc")
        auth = ApiKeyAuth(key_env="MY_KEY")
        assert auth.get_key() == "abc"


class TestOAuth2Auth:
    def test_valid_construction(self):
        auth = OAuth2Auth(
            client_id_env="CID",
            client_secret_env="CSEC",
            token_url="https://auth.example.com/token",
        )
        assert auth.token_url == "https://auth.example.com/token"

    def test_empty_fields_raise(self):
        with pytest.raises(ValueError):
            OAuth2Auth(client_id_env="", client_secret_env="S", token_url="http://x")
        with pytest.raises(ValueError):
            OAuth2Auth(client_id_env="C", client_secret_env="", token_url="http://x")
        with pytest.raises(ValueError):
            OAuth2Auth(client_id_env="C", client_secret_env="S", token_url="")


class TestBasicAuth:
    def test_valid_construction(self):
        auth = BasicAuth(username_env="USER", password_env="PASS")
        assert auth.username_env == "USER"

    def test_get_credentials(self, monkeypatch):
        monkeypatch.setenv("USER", "admin")
        monkeypatch.setenv("PASS", "secret")
        auth = BasicAuth(username_env="USER", password_env="PASS")
        u, p = auth.get_credentials()
        assert u == "admin"
        assert p == "secret"


# ---------- Shared config types ----------


class TestStalenessPolicy:
    def test_defaults(self):
        sp = StalenessPolicy()
        assert sp.max_age == timedelta(minutes=5)
        assert sp.on_stale == "serve"
        assert sp.on_source_error == "serve_stale"


class TestRateLimit:
    def test_defaults(self):
        rl = RateLimit()
        assert rl.max_requests == 100
        assert rl.max_unique_params == 50


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cb = CircuitBreakerConfig()
        assert cb.failure_threshold == 3
        assert cb.probe_interval == 30.0


class TestWebhookConfig:
    def test_valid(self):
        wh = WebhookConfig(path="/hooks/crm", secret_env="HOOK_SECRET")
        assert wh.path == "/hooks/crm"

    def test_empty_path_raises(self):
        with pytest.raises(ValueError):
            WebhookConfig(path="", secret_env="SEC")

    def test_empty_secret_raises(self):
        with pytest.raises(ValueError):
            WebhookConfig(path="/hooks", secret_env="")


# ---------- Source config types ----------


class TestRestSourceConfig:
    def test_valid_config(self):
        cfg = RestSourceConfig(url="https://api.example.com")
        cfg.validate()

    def test_missing_url_raises(self):
        cfg = RestSourceConfig()
        with pytest.raises(ValueError, match="url must not be empty"):
            cfg.validate()

    def test_invalid_url_raises(self):
        cfg = RestSourceConfig(url="ftp://wrong.com")
        with pytest.raises(ValueError, match="http:// or https://"):
            cfg.validate()

    def test_negative_poll_interval_raises(self):
        cfg = RestSourceConfig(url="https://x.com", poll_interval=-1)
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            cfg.validate()

    def test_negative_timeout_raises(self):
        cfg = RestSourceConfig(url="https://x.com", timeout=-5)
        with pytest.raises(ValueError, match="timeout must be positive"):
            cfg.validate()


class TestFileSourceConfig:
    def test_valid_config(self):
        cfg = FileSourceConfig(path="/tmp/data.json")
        cfg.validate()

    def test_empty_path_raises(self):
        cfg = FileSourceConfig()
        with pytest.raises(ValueError, match="path.*or.*directory.*must be set"):
            cfg.validate()


class TestCloudSourceConfig:
    def test_valid_config(self):
        cfg = CloudSourceConfig(bucket="my-bucket", provider="s3")
        cfg.validate()

    def test_empty_bucket_raises(self):
        cfg = CloudSourceConfig()
        with pytest.raises(ValueError, match="bucket must not be empty"):
            cfg.validate()

    def test_invalid_provider_raises(self):
        cfg = CloudSourceConfig(bucket="b", provider="dropbox")
        with pytest.raises(ValueError, match="'s3', 'gcs', or 'azure'"):
            cfg.validate()


class TestDatabaseSourceConfig:
    def test_valid_config(self):
        cfg = DatabaseSourceConfig(url="sqlite:///test.db")
        cfg.validate()

    def test_empty_url_raises(self):
        cfg = DatabaseSourceConfig()
        with pytest.raises(ValueError, match="url must not be empty"):
            cfg.validate()


class TestStreamSourceConfig:
    def test_valid_config(self):
        cfg = StreamSourceConfig(broker="localhost:9092", topic="events")
        cfg.validate()

    def test_empty_broker_raises(self):
        cfg = StreamSourceConfig(topic="t")
        with pytest.raises(ValueError, match="broker must not be empty"):
            cfg.validate()

    def test_empty_topic_raises(self):
        cfg = StreamSourceConfig(broker="localhost:9092")
        with pytest.raises(ValueError, match="topic must not be empty"):
            cfg.validate()
