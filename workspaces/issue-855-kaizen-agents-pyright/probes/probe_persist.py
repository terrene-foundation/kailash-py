"""Prove the real warm-backed HierarchicalMemory construction works end-to-end
against real SQLite, BEFORE designing the shortcuts factory. No mocks."""

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

result = {"step": "start"}
try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.hierarchical import HierarchicalMemory
    from kaizen.memory.providers.types import MemoryEntry

    result["step"] = "imports_ok"

    tmpdir = tempfile.mkdtemp(prefix="probe855_")
    db_path = Path(tmpdir) / "kaizen_memory.db"
    db_uri = (
        (Path(tmpdir) / "kaizen_memory.db").as_uri().replace("file://", "sqlite://")
    )
    result["db_uri"] = db_uri

    db = DataFlow(database_url=db_uri)
    result["step"] = "dataflow_created"

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
        embedding: str = ""  # JSON array; "" sentinel (Optional caused issues?)

    result["step"] = "model_registered"

    backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")
    result["step"] = "backend_created"

    mem = HierarchicalMemory(hot_size=1000, warm_backend=backend)
    result["step"] = "hierarchical_created"
    result["has_warm_tier"] = mem.has_warm_tier

    # store + recall round trip
    async def roundtrip():
        e = MemoryEntry(content="round-trip probe entry", session_id="probe-s1")
        await mem.store(e)
        ctx = await mem.build_context(session_id="probe-s1", max_tokens=4000)
        return ctx

    ctx = asyncio.run(roundtrip())
    result["step"] = "roundtrip_ok"
    result["ctx_type"] = type(ctx).__name__
    result["ctx_repr"] = repr(ctx)[:200]
    result["VERDICT"] = "PASS"
except Exception as e:
    result["VERDICT"] = "FAIL"
    result["error"] = f"{type(e).__name__}: {e}"
    result["trace"] = traceback.format_exc()[-1500:]

with open("/tmp/triage/probe_persist_result.json", "w") as f:
    json.dump(result, f, indent=2, default=str)
print("WROTE", result.get("VERDICT"), "at step", result.get("step"))
