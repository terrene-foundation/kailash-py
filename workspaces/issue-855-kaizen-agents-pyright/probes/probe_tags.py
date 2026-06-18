"""Why do tags read back empty? Dump the RAW record dict the ReadNode returns,
so we see the actual key + value for the tags column."""

import json
import tempfile
import traceback
from pathlib import Path


def dsn(p):
    return "sqlite:////" + str(p.resolve()).lstrip("/")


r = {}
try:
    from dataflow import DataFlow
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.types import MemoryEntry

    tmp = Path(tempfile.mkdtemp(prefix="tags_"))
    db = DataFlow(database_url=dsn(tmp / "m.db"))

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
    e = MemoryEntry(content="c", session_id="s1", importance=0.3, tags=["a", "b"])
    sid = backend.store(e)

    # RAW read node — what keys/values come back?
    wf = WorkflowBuilder()
    wf.add_node("MemoryEntryModelReadNode", "read", {"id": sid})
    with LocalRuntime() as rt:
        res, _ = rt.execute(wf.build())
    raw = res.get("read")
    r["raw_read_repr"] = repr(raw)[:500]
    if isinstance(raw, dict):
        r["raw_read_keys"] = list(raw.keys())
        # what _record_to_entry actually receives may be raw or raw['result'] etc.
        r["raw_tag_list_value"] = raw.get("tag_list", "ABSENT")
        if "result" in raw and isinstance(raw["result"], dict):
            r["result_keys"] = list(raw["result"].keys())
            r["result_tag_list"] = raw["result"].get("tag_list", "ABSENT")

    # And what does backend.get return for tags?
    got = backend.get(sid)
    r["backend_get_tags"] = got.tags if got else None
    r["backend_get_content"] = got.content if got else None
    r["VERDICT"] = "captured"
except Exception as ex:
    r["VERDICT"] = "ERROR"
    r["error"] = f"{type(ex).__name__}: {ex}"
    r["trace"] = traceback.format_exc()[-1000:]

open("/tmp/triage/probe_tags_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE")
