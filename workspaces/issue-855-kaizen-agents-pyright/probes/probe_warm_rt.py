"""SETTLE step 0: after tag_list rename, does the warm tier ACTUALLY round-trip
with proper DataFlow auto-migration + a LOW-importance entry (forces warm path)?
Real SQLite, no mocks. Tests BOTH direct-backend and through-HierarchicalMemory."""

import asyncio
import json
import tempfile
import traceback
from pathlib import Path

r = {}
try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.hierarchical import HierarchicalMemory
    from kaizen.memory.providers.types import MemoryEntry

    tmp = tempfile.mkdtemp(prefix="warmrt_")
    uri = (Path(tmp) / "m.db").as_uri().replace("file://", "sqlite://")
    db = DataFlow(database_url=uri)  # auto_migrate defaults True

    @db.model
    class MemoryEntryModel:
        id: str
        session_id: str
        content: str
        role: str
        timestamp: str
        source: str
        importance: float
        tag_list: str
        metadata: str
        embedding: str = ""

    backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")

    # --- Test 1: DIRECT backend store -> get -> list (pure sync) ---
    e = MemoryEntry(
        content="direct probe content", session_id="s1", importance=0.3, tags=["a", "b"]
    )
    sid = backend.store(e)
    got = backend.get(sid)
    listed = backend.list_entries(session_id="s1", limit=10)
    r["direct_store_id_set"] = bool(sid)
    r["direct_get_content"] = got.content if got else None
    r["direct_get_tags"] = got.tags if got else None
    r["direct_list_count"] = len(listed)
    r["direct_roundtrip"] = bool(
        got and got.content == "direct probe content" and got.tags == ["a", "b"]
    )

    # --- Test 2: through HierarchicalMemory with LOW importance (-> warm tier) ---
    mem = HierarchicalMemory(
        hot_size=1000, warm_backend=backend, promotion_threshold=0.7
    )

    async def warm_path():
        await mem.store(
            MemoryEntry(
                content="warm via hierarchical",
                session_id="s2",
                importance=0.2,
                tags=["w"],
            )
        )
        return backend.list_entries(session_id="s2", limit=10)

    warm_rows = asyncio.run(warm_path())
    r["hier_warm_rows"] = len(warm_rows)
    r["hier_warm_content"] = warm_rows[0].content if warm_rows else None

    r["VERDICT"] = (
        "PASS" if (r["direct_roundtrip"] and r["hier_warm_rows"] >= 1) else "FAIL"
    )
except Exception as ex:
    r["VERDICT"] = "ERROR"
    r["error"] = f"{type(ex).__name__}: {ex}"
    r["trace"] = traceback.format_exc()[-1500:]

open("/tmp/triage/probe_warm_rt_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE", r.get("VERDICT"))
