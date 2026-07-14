"""
Unit tests for credential_provider config propagation (issue #1737).

Verifies the DataFlow(...) constructor threads a caller-supplied
credential_provider into DatabaseConfig.credential_provider across every
DataFlow.__init__ branch:
  1. config= object provided
  2. zero-config mode (no database_url, credential_provider is the only arg)
  3. structured-config mode (database_url + other kwargs provided)
  4. DataFlowConfig(credential_provider=...) constructed directly

No live database connection is required — these are pure config-plumbing
assertions (SQLite-backed DataFlow instances, which never read
credential_provider, so construction stays fast and offline).
"""

from __future__ import annotations

import copy
import threading

from dataflow import DataFlow
from dataflow.core.config import DatabaseConfig, DataFlowConfig


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider — NOT a
    MagicMock."""

    def __init__(self, tokens):
        self._tokens = list(tokens)
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._tokens) - 1)
        return self._tokens[idx]


class StatefulTokenProvider:
    """A credential provider closing over a resource that is NOT
    deepcopy-safe (a threading.Lock) — representative of a real Azure AD /
    AWS IAM token provider, which typically wraps a boto3 client, an HTTP
    session, or an azure-identity credential cache with internal locks."""

    def __init__(self, token: str):
        self._token = token
        self._lock = threading.Lock()
        self.call_count = 0

    def __call__(self) -> str:
        with self._lock:
            self.call_count += 1
        return self._token


class TestDatabaseConfigCredentialProviderField:
    def test_defaults_to_none(self):
        cfg = DatabaseConfig()
        assert cfg.credential_provider is None

    def test_accepts_callable(self):
        provider = RotatingTokenProvider(["t1"])
        cfg = DatabaseConfig(credential_provider=provider)
        assert cfg.credential_provider is provider


class TestDataFlowConfigDirectConstruction:
    def test_credential_provider_kwarg_flows_into_database_config(self):
        provider = RotatingTokenProvider(["t1"])
        config = DataFlowConfig(
            database_url="sqlite:///:memory:", credential_provider=provider
        )
        assert config.database.credential_provider is provider


class TestDataFlowConstructorPropagation:
    """AC: connection config accepts the optional per-connection credential
    callback — verified at every DataFlow.__init__ code path."""

    def test_structured_config_branch_propagates_credential_provider(self):
        provider = RotatingTokenProvider(["t1"])
        db = DataFlow(
            database_url="sqlite:///:memory:",
            credential_provider=provider,
        )
        assert db.config.database.credential_provider is provider

    def test_zero_config_mode_still_propagates_credential_provider(self):
        """When credential_provider is the ONLY constructor arg supplied
        (database_url=None, every other param at its default), DataFlow.__init__
        takes the zero-config (from_env()) branch — credential_provider MUST
        still reach config.database.credential_provider, not be silently
        dropped (mirrors the pre-existing tenant_isolation_strategy pattern).
        """
        provider = RotatingTokenProvider(["t1"])
        db = DataFlow(credential_provider=provider)
        assert db.config.database.credential_provider is provider

    def test_config_object_branch_propagates_credential_provider(self):
        provider = RotatingTokenProvider(["t1"])
        base_config = DataFlowConfig(database_url="sqlite:///:memory:")
        assert base_config.database.credential_provider is None

        db = DataFlow(config=base_config, credential_provider=provider)
        assert db.config.database.credential_provider is provider
        # The caller's original config object is not mutated in place
        # (DataFlow.__init__ deep-copies config= before applying overrides).
        assert base_config.database.credential_provider is None

    def test_absent_credential_provider_defaults_to_none_every_branch(self):
        db_structured = DataFlow(database_url="sqlite:///:memory:")
        assert db_structured.config.database.credential_provider is None

        db_zero_config = DataFlow()
        assert db_zero_config.config.database.credential_provider is None

        db_config_obj = DataFlow(
            config=DataFlowConfig(database_url="sqlite:///:memory:")
        )
        assert db_config_obj.config.database.credential_provider is None


class TestCredentialProviderSurvivesDeepcopy:
    """Regression: DataFlow.__init__'s config= branch deep-copies the
    caller-supplied DataFlowConfig. A real credential_provider (Azure AD /
    AWS IAM token provider) commonly closes over a non-deepcopy-safe
    resource (boto3 client, threading.Lock, azure-identity cache).
    DatabaseConfig.__deepcopy__ MUST carry credential_provider by
    reference — every other field still gets normal deep-copy isolation.
    """

    def test_database_config_deepcopy_preserves_stateful_provider_by_reference(
        self,
    ):
        provider = StatefulTokenProvider(token="tok-1")
        cfg = DatabaseConfig(url="sqlite:///:memory:", credential_provider=provider)

        copied = copy.deepcopy(cfg)

        assert copied.credential_provider is provider
        # Other fields still deep-copy normally — independent dict objects
        # with equal content, not the same object.
        assert copied.connect_args is not cfg.connect_args
        assert copied.connect_args == cfg.connect_args
        assert copied.url == cfg.url

    def test_dataflowconfig_deepcopy_preserves_stateful_provider_by_reference(self):
        provider = StatefulTokenProvider(token="tok-1")
        config = DataFlowConfig(
            database_url="sqlite:///:memory:", credential_provider=provider
        )

        copied = copy.deepcopy(config)

        assert copied.database.credential_provider is provider

    def test_dataflow_config_object_branch_does_not_crash_with_stateful_provider(
        self,
    ):
        """The originating bug: DataFlow(config=<cfg-with-stateful-provider>)
        used to raise TypeError: cannot pickle '_thread.lock' object.
        """
        provider = StatefulTokenProvider(token="tok-1")
        base_config = DataFlowConfig(
            database_url="sqlite:///:memory:", credential_provider=provider
        )

        db = DataFlow(config=base_config)  # MUST NOT raise

        assert db.config.database.credential_provider is provider
        # The live provider still works after surviving the deepcopy.
        assert db.config.database.credential_provider() == "tok-1"
        assert provider.call_count == 1
