# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the 2.46.1 `enable_observability()` wiring.

Three defects sat in a row between a caller and working observability, and
fixing only the first would have changed nothing anyone could observe:

1. ``enable_observability()`` raised ``AttributeError: 'NoneType' object has no
   attribute 'register_hook'`` on any agent built without ``hooks_enabled=True``
   -- the default. ``enable_tracing`` defaults ``True``, so the crash landed on
   every caller, including ones asking only for metrics or only for logging.
2. The ``observability`` extra declared ``opentelemetry-api`` and
   ``opentelemetry-sdk`` but NOT ``opentelemetry-exporter-otlp``, which is a
   separate distribution. ``tracing_manager`` imports
   ``opentelemetry.exporter.otlp...`` at module scope, so installing the extra
   and calling the method still raised -- ``ModuleNotFoundError``.
3. ``jaeger_host`` / ``jaeger_port`` / ``insecure`` were documented as
   controlling the OTLP endpoint and forwarded nowhere, so spans always went to
   ``localhost:4317`` no matter what the caller passed.

Why (2) hid, and why the first test below asserts on the MANIFEST rather than
importing anything: the failure requires opentelemetry to be PARTIALLY present.
With the package wholly absent the hook system stays lazy and imports cleanly;
with the exporter present everything works. Only the exact dependency set the
extra declares -- api + sdk, no exporter -- was broken.

That set is never what a developer has. The ROOT ``kailash`` package's own
``[telemetry]`` extra declares ``opentelemetry-exporter-otlp``, so a monorepo
checkout always has the exporter and every existing test passes against it. No
test ever ran against the dependency set ``kailash-kaizen[observability]``
actually produces. This is the editable-install-stays-green shape
``rules/deployment.md`` names, and an import-based test cannot catch it -- in
the environment where the test runs, the import succeeds. So the pin has to be
on the DECLARATION, which is what ``TestObservabilityExtraIsComplete`` does; it
needs no opentelemetry and therefore runs everywhere, unconditionally.
"""

import inspect
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _extra(name: str) -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"][name]


class TestObservabilityExtraIsComplete:
    """Runs everywhere -- needs no opentelemetry, which is the whole point."""

    def test_extra_declares_the_otlp_exporter_distribution(self):
        """`opentelemetry-sdk` does NOT provide `opentelemetry.exporter.otlp`.

        Without this line, `pip install kailash-kaizen[observability]` produced
        precisely the partially-present state in which `enable_observability()`
        raises `ModuleNotFoundError: No module named 'opentelemetry.exporter'`.
        """
        names = [
            d.split(">=")[0].split("[")[0].strip() for d in _extra("observability")
        ]
        assert "opentelemetry-exporter-otlp" in names, (
            "tracing_manager imports opentelemetry.exporter.otlp at module scope; "
            f"the observability extra must declare it. Declared: {names}"
        )

    def test_extra_still_declares_its_other_module_scope_imports(self):
        names = [
            d.split(">=")[0].split("[")[0].strip() for d in _extra("observability")
        ]
        for required in ("opentelemetry-api", "opentelemetry-sdk"):
            assert required in names


class TestEndpointConfigIsForwarded:
    """`jaeger_host` / `jaeger_port` / `insecure` must reach the exporter."""

    def test_observability_manager_accepts_the_endpoint_kwargs(self):
        """Signature pin -- runs without opentelemetry.

        Kept separate from the behavioural test below so that the contract is
        still pinned in an environment where the extra is absent.
        """
        mod = pytest.importorskip(
            "kaizen.core.autonomy.observability.manager",
            reason="requires the observability extra (opentelemetry)",
        )
        params = inspect.signature(mod.ObservabilityManager.__init__).parameters
        for name in ("jaeger_host", "jaeger_port", "insecure"):
            assert name in params

    def test_manager_forwards_endpoint_config_to_the_tracing_manager(self):
        mod = pytest.importorskip(
            "kaizen.core.autonomy.observability.manager",
            reason="requires the observability extra (opentelemetry)",
        )
        obs = mod.ObservabilityManager(
            service_name="svc",
            enable_audit=False,
            jaeger_host="jaeger.internal",
            jaeger_port=14317,
            insecure=False,
        )
        assert obs.tracing.jaeger_host == "jaeger.internal"
        assert obs.tracing.jaeger_port == 14317

    def test_defaults_are_unchanged_for_existing_callers(self):
        mod = pytest.importorskip(
            "kaizen.core.autonomy.observability.manager",
            reason="requires the observability extra (opentelemetry)",
        )
        obs = mod.ObservabilityManager(service_name="svc", enable_audit=False)
        assert obs.tracing.jaeger_host == "localhost"
        assert obs.tracing.jaeger_port == 4317


class TestEnableObservabilityOnDefaultConstructedAgent:
    """The 2.46.1 headline fix, pinned behaviourally."""

    def _agent(self):
        pytest.importorskip(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
            reason="requires the observability extra (opentelemetry-exporter-otlp)",
        )
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        cfg = BaseAgentConfig()
        # The precondition that made this crash: hooks are OFF by default.
        assert cfg.hooks_enabled is False
        agent = BaseAgent(config=cfg)
        assert agent._hook_manager is None
        return agent

    def test_does_not_raise_attributeerror(self):
        agent = self._agent()
        agent.enable_observability()  # pre-2.46.1: AttributeError on NoneType
        assert agent._hook_manager is not None

    def test_holds_the_dual_name_invariant(self):
        """`__init__` keeps both names pointing at ONE object; so must this.

        If they diverge, a later `self.hook_manager` read sees None while hooks
        are registered on the other name -- a silent no-op.
        """
        agent = self._agent()
        agent.enable_observability()
        assert agent.hook_manager is agent._hook_manager

    def test_metrics_only_caller_is_not_broken_by_the_tracing_branch(self):
        """The crash hit metrics-only callers too, because it ran first."""
        agent = self._agent()
        agent.enable_observability(enable_tracing=False, enable_audit=False)

    def test_endpoint_kwargs_reach_the_exporter_through_the_agent(self):
        agent = self._agent()
        obs = agent.enable_observability(
            jaeger_host="collector.example", jaeger_port=4318, enable_audit=False
        )
        assert obs.tracing.jaeger_host == "collector.example"
        assert obs.tracing.jaeger_port == 4318
