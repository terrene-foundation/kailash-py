"""DEFINITIVE: full DataFlowMemoryBackend + HierarchicalMemory round-trip with
the tag_list fix applied AND a correct 4-slash absolute sqlite DSN. Real SQLite."""

import asyncio
import json
import tempfile
import traceback
from pathlib import Path

r = {}


def abs_sqlite_dsn(path: Path) -> str:
    # 4-slash absolute form (the only one DataFlow opens, per probe_dsn)
    return "sqlite:////" + str(path.resolve()).lstrip("/")


try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.hierarchical import HierarchicalMemory
    from kaizen.memory.providers.types import MemoryEntry

    tmp = Path(tempfile.mkdtemp(prefix="bert_"))
    dsn = abs_sqlite_dsn(tmp / "kaizen_memory.db")
    r["dsn"] = dsn
    db = DataFlow(database_url=dsn)

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

    # Test 1: direct backend store -> get -> list (sync)
    e = MemoryEntry(
        content="direct content", session_id="s1", importance=0.3, tags=["a", "b"]
    )
    sid = backend.store(e)
    got = backend.get(sid)
    listed = backend.list_entries(session_id="s1", limit=10)
    r["direct_get_content"] = got.content if got else None
    r["direct_get_tags"] = got.tags if got else None
    r["direct_list_count"] = len(listed)
    r["direct_roundtrip"] = bool(
        got and got.content == "direct content" and got.tags == ["a", "b"]
    )

    # Test 2: through HierarchicalMemory, low importance -> warm tier
    mem = HierarchicalMemory(
        hot_size=1000, warm_backend=backend, promotion_threshold=0.7
    )

    async def warm():
        await mem.store(
            MemoryEntry(
                content="warm via hier", session_id="s2", importance=0.2, tags=["w"]
            )
        )
        return backend.list_entries(session_id="s2", limit=10)

    warm_rows = asyncio.run(warm())
    r["hier_warm_rows"] = len(warm_rows)
    r["hier_warm_content"] = warm_rows[0].content if warm_rows else None

    r["VERDICT"] = (
        "PASS"
        if (
            r["direct_roundtrip"]
            and r["hier_warm_rows"] >= 1
            and r["hier_warm_content"] == "warm via hier"
        )
        else "FAIL"
    )
except Exception as ex:
    r["VERDICT"] = "ERROR"
    r["error"] = f"{type(ex).__name__}: {ex}"
    r["trace"] = traceback.format_exc()[-1200:]

open("/tmp/triage/probe_backend_rt_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE", r.get("VERDICT"))
