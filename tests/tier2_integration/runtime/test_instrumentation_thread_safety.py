# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Thread-safety smoke tests for instrumentation components.

Extracted from tests/unit/runtime/test_instrumentation.py because these tests
spawn real OS threads, which violates the Tier 1 contract (fast, isolated,
deterministic). They belong in Tier 2 where real threading is permitted.
"""

from __future__ import annotations

import threading
from typing import Any


class TestThreadSafety:
    """Verify key components are safe under concurrent access."""

    def test_concurrent_tracer_level_changes(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.NONE)
        errors: list[Exception] = []

        def toggle(level: TracingLevel) -> None:
            try:
                for _ in range(50):
                    tracer.level = level
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=toggle, args=(TracingLevel.FULL,)),
            threading.Thread(target=toggle, args=(TracingLevel.NONE,)),
            threading.Thread(target=toggle, args=(TracingLevel.BASIC,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_node_instrumentation(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            inst = NodeInstrumentor()
            results: list[int] = []
            errors: list[Exception] = []

            def run_node(val: int) -> None:
                try:
                    r = inst.execute(
                        node_id=f"n-{val}",
                        node_type="TestNode",
                        func=lambda v: v * 2,
                        args=(val,),
                    )
                    results.append(r)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=run_node, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
            assert errors == []
            assert sorted(results) == [i * 2 for i in range(10)]
        finally:
            mod._global_tracer = old
