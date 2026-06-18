import json
import tempfile
import traceback
from pathlib import Path

r = {}
try:
    from dataflow import DataFlow
    from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    from kaizen.memory.providers.types import MemoryEntry

    tmp = tempfile.mkdtemp(prefix="why_")
    uri = (Path(tmp) / "m.db").as_uri().replace("file://", "sqlite://")
    r["uri"] = uri
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
    e = MemoryEntry(content="hello", session_id="s1", importance=0.3, tags=["a"])
    # capture the RAW result of store's workflow, not just the swallowed return
    import json as _j

    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    wf = WorkflowBuilder()
    wf.add_node(
        "MemoryEntryModelCreateNode",
        "create",
        {
            "id": e.id,
            "session_id": e.session_id,
            "content": e.content,
            "role": e.role,
            "timestamp": e.timestamp.isoformat(),
            "source": e.source.value,
            "importance": e.importance,
            "tag_list": _j.dumps(e.tags),
            "metadata": _j.dumps(e.metadata),
            "embedding": None,
        },
    )
    with LocalRuntime() as rt:
        results, _ = rt.execute(wf.build())
    r["create_results_keys"] = list(results.keys())
    r["create_result"] = repr(results.get("create"))[:300]
    # now a raw Read/List on the same db
    wf2 = WorkflowBuilder()
    wf2.add_node("MemoryEntryModelListNode", "list", {})
    with LocalRuntime() as rt:
        res2, _ = rt.execute(wf2.build())
    r["list_result"] = repr(res2.get("list"))[:400]
    r["VERDICT"] = "captured"
except Exception as ex:
    r["VERDICT"] = "ERROR"
    r["error"] = f"{type(ex).__name__}: {ex}"
    r["trace"] = traceback.format_exc()[-1200:]
open("/tmp/triage/probe_why_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE")
