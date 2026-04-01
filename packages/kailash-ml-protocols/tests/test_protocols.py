# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Protocol conformance tests for kailash-ml-protocols."""
from __future__ import annotations

from kailash_ml_protocols import AgentInfusionProtocol, MLToolProtocol


class TestMLToolProtocol:
    """MLToolProtocol conformance tests."""

    def test_conformance_passes_with_all_methods(self) -> None:
        """A class implementing all 3 methods passes isinstance check."""

        class FakeTool:
            async def predict(self, model_name, features, *, options=None): ...

            async def get_metrics(self, model_name, version=None, *, options=None): ...

            async def get_model_info(self, model_name, *, options=None): ...

        assert isinstance(FakeTool(), MLToolProtocol)

    def test_conformance_fails_with_missing_method(self) -> None:
        """A class missing a method does NOT pass isinstance check."""

        class IncompleteTool:
            async def predict(self, model_name, features, *, options=None): ...

            async def get_metrics(self, model_name, version=None, *, options=None): ...

            # Missing get_model_info

        assert not isinstance(IncompleteTool(), MLToolProtocol)

    def test_conformance_fails_with_no_methods(self) -> None:
        """An empty class does NOT pass isinstance check."""

        class EmptyClass:
            pass

        assert not isinstance(EmptyClass(), MLToolProtocol)


class TestAgentInfusionProtocol:
    """AgentInfusionProtocol conformance tests."""

    def test_conformance_passes_with_all_methods(self) -> None:
        """A class implementing all 4 methods passes isinstance check."""

        class FakeAgent:
            async def suggest_model(self, data_profile, task_type, *, options=None): ...

            async def suggest_features(
                self, data_profile, existing_features, *, options=None
            ): ...

            async def interpret_results(self, experiment_results, *, options=None): ...

            async def interpret_drift(self, drift_report, *, options=None): ...

        assert isinstance(FakeAgent(), AgentInfusionProtocol)

    def test_conformance_fails_with_missing_method(self) -> None:
        """A class missing a method does NOT pass isinstance check."""

        class IncompleteAgent:
            async def suggest_model(self, data_profile, task_type, *, options=None): ...

            async def suggest_features(
                self, data_profile, existing_features, *, options=None
            ): ...

            # Missing interpret_results and interpret_drift

        assert not isinstance(IncompleteAgent(), AgentInfusionProtocol)

    def test_conformance_fails_with_no_methods(self) -> None:
        """An empty class does NOT pass isinstance check."""

        class EmptyClass:
            pass

        assert not isinstance(EmptyClass(), AgentInfusionProtocol)
