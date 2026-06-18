"""Does backend.store()/list round-trip work in PURE SYNC context (its
documented usage) after the tag_list fix? Isolates the tags-fix from the
separate async-nesting bug. No mocks, real SQLite."""

import json
import tempfile
import traceback
from pathlib import Path

r = {}
try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.types import MemoryEntry

    tmp = tempfile.mkdtemp(prefix="sync855_")
    uri = (Path(tmp) / "m.db").as_uri().replace("file://", "sqlite://")
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
        tag_list: str
        metadata: str
        embedding: str = ""

    backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")
    e = MemoryEntry(
        content="sync probe", session_id="s1", importance=0.9, tags=["x", "y"]
    )
    stored_id = backend.store(e)  # pure sync
    listed = backend.list_entries(session_id="s1", limit=10)
    got = backend.get(stored_id)
    r["stored_id"] = stored_id
    r["list_count"] = len(listed)
    r["got_content"] = got.content if got else None
    r["got_tags_roundtrip"] = got.tags if got else None
    r["VERDICT"] = (
        "PASS"
        if (got and got.content == "sync probe" and got.tags == ["x", "y"])
        else "PARTIAL"
    )
except Exception as ex:
    r["VERDICT"] = "FAIL"
    r["error"] = f"{type(ex).__name__}: {ex}"
    r["trace"] = traceback.format_exc()[-1000:]

open("/tmp/triage/probe_sync_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE", r.get("VERDICT"))
