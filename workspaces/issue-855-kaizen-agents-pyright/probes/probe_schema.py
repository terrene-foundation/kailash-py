"""Which field in the documented 10-field MemoryEntryModel schema breaks
CreateNode? Add fields incrementally to find the offender. No mocks."""

import json
import tempfile
import traceback
from pathlib import Path

out = {}


def fresh_db():
    from dataflow import DataFlow

    tmp = tempfile.mkdtemp(prefix="sch855_")
    uri = (Path(tmp) / "m.db").as_uri().replace("file://", "sqlite://")
    return DataFlow(database_url=uri)


from kailash.runtime.local import LocalRuntime  # noqa: E402
from kailash.workflow.builder import WorkflowBuilder  # noqa: E402


# Full documented schema (per dataflow_backend.py docstring lines 39-49)
def try_full():
    db = fresh_db()

    @db.model
    class MemoryEntryModel:
        id: str
        session_id: str
        content: str
        role: str
        timestamp: str
        source: str
        importance: float
        tags: str
        metadata: str
        embedding: str = ""

    wf = WorkflowBuilder()
    wf.add_node(
        "MemoryEntryModelCreateNode",
        "create",
        {
            "id": "1",
            "session_id": "s",
            "content": "c",
            "role": "user",
            "timestamp": "2026-01-01T00:00:00",
            "source": "user",
            "importance": 0.5,
            "tags": json.dumps([]),
            "metadata": json.dumps({}),
            "embedding": json.dumps([]),
        },
    )
    with LocalRuntime() as rt:
        rt.execute(wf.build())
    return "STORE_OK"


try:
    out["full_schema"] = try_full()
except Exception as e:
    out["full_schema"] = f"{type(e).__name__}: {str(e)[:200]}"


# Isolate `metadata` field specifically
def try_metadata_only():
    db = fresh_db()

    @db.model
    class MdOnly:
        id: str
        metadata: str

    wf = WorkflowBuilder()
    wf.add_node("MdOnlyCreateNode", "create", {"id": "1", "metadata": json.dumps({})})
    with LocalRuntime() as rt:
        rt.execute(wf.build())
    return "STORE_OK"


try:
    out["metadata_field_only"] = try_metadata_only()
except Exception as e:
    out["metadata_field_only"] = f"{type(e).__name__}: {str(e)[:200]}"


# Isolate `source` field (another reserved-sounding name)
def try_source_only():
    db = fresh_db()

    @db.model
    class SrcOnly:
        id: str
        source: str

    wf = WorkflowBuilder()
    wf.add_node("SrcOnlyCreateNode", "create", {"id": "1", "source": "user"})
    with LocalRuntime() as rt:
        rt.execute(wf.build())
    return "STORE_OK"


try:
    out["source_field_only"] = try_source_only()
except Exception as e:
    out["source_field_only"] = f"{type(e).__name__}: {str(e)[:200]}"

with open("/tmp/triage/probe_schema_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("DONE")
