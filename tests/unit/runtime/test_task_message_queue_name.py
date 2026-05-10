# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``TaskMessage.queue_name`` (#911 Shard 1).

Pins:

* ``queue_name`` defaults to ``"default"``.
* JSON round-trip preserves ``queue_name`` for non-default queues.
* Older-SDK JSON without ``queue_name`` deserializes as ``"default"``.
* Default-queue JSON OMITS ``queue_name`` so the wire format stays
  byte-identical to pre-#911 messages (older workers parse them
  unchanged).
"""

from __future__ import annotations

import json

from kailash.runtime.distributed import TaskMessage


class TestTaskMessageQueueName:
    def test_default_queue_name(self) -> None:
        task = TaskMessage(task_id="t1")
        assert task.queue_name == "default"

    def test_round_trip_default_queue_omits_field(self) -> None:
        # The default-queue wire format MUST NOT carry queue_name —
        # older workers on a pre-#911 SDK have never seen the field
        # and would otherwise need to ignore it.
        task = TaskMessage(task_id="t1")
        payload = json.loads(task.to_json())
        assert "queue_name" not in payload

    def test_round_trip_non_default_includes_field(self) -> None:
        task = TaskMessage(task_id="t1", queue_name="fast")
        payload = json.loads(task.to_json())
        assert payload["queue_name"] == "fast"

    def test_round_trip_preserves_queue_name(self) -> None:
        original = TaskMessage(task_id="t1", queue_name="slow_queue")
        restored = TaskMessage.from_json(original.to_json())
        assert restored.queue_name == "slow_queue"

    def test_legacy_json_deserializes_to_default_queue(self) -> None:
        # Older-SDK JSON that has never written queue_name MUST
        # deserialize as the default queue.
        legacy = json.dumps(
            {
                "task_id": "t1",
                "workflow_data": {},
                "parameters": {},
                "submitted_at": 1.0,
                "visibility_timeout": 300,
                "attempts": 0,
                "max_attempts": 3,
            }
        )
        restored = TaskMessage.from_json(legacy)
        assert restored.queue_name == "default"

    def test_round_trip_combines_with_execution_limits(self) -> None:
        # #911 Shard 1 + #912 Shard 4 compose orthogonally.
        original = TaskMessage(
            task_id="t1",
            queue_name="fast",
            execution_limits={"soft": 2.0, "hard": 5.0},
        )
        restored = TaskMessage.from_json(original.to_json())
        assert restored.queue_name == "fast"
        assert restored.execution_limits == {"soft": 2.0, "hard": 5.0}
