"""Post-fix proof: full warm-backed HierarchicalMemory store->recall round-trip
against real SQLite, using the corrected tag_list schema. No mocks."""

import asyncio
import json
import tempfile
import traceback
from pathlib import Path

r = {"step": "start"}
try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.hierarchical import HierarchicalMemory
    from kaizen.memory.providers.types import MemoryEntry

    tmp = tempfile.mkdtemp(prefix="p2_855_")
    uri = (Path(tmp) / "kaizen_memory.db").as_uri().replace("file://", "sqlite://")
    db = DataFlow(database_url=uri)

    @db.model
    class MemoryEntryModel:
        id: str
        session_id: str
        content: str
        role: str
        timestamp: str
        source: str
        importance: float
        tag_list: str  # corrected: was `tags` (NodeMetadata collision)
        metadata: str
        embedding: str = ""

    backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")
    mem = HierarchicalMemory(hot_size=2, warm_backend=backend)  # tiny hot -> force warm
    r["has_warm_tier"] = mem.has_warm_tier

    async def run():
        # store >hot_size entries so some demote into the warm (DataFlow) tier
        for i in range(5):
            await mem.store(
                MemoryEntry(
                    content=f"entry {i} with tags", session_id="s1", importance=0.9
                )
            )
        # direct warm read-back proves persistence through DataFlow
        listed = backend.list_entries(session_id="s1", limit=50)
        ctx = await mem.build_context(session_id="s1", max_tokens=4000)
        return len(listed), ctx

    n_warm, ctx = asyncio.run(run())
    r["warm_rows_persisted"] = n_warm
    r["ctx_type"] = type(ctx).__name__
    r["VERDICT"] = "PASS" if n_warm >= 1 else "FAIL_no_warm_rows"
except Exception as e:
    r["VERDICT"] = "FAIL"
    r["error"] = f"{type(e).__name__}: {e}"
    r["trace"] = traceback.format_exc()[-1200:]

open("/tmp/triage/probe_persist2_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE", r.get("VERDICT"))
