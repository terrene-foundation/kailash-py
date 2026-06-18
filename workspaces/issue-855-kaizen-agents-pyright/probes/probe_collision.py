"""Isolate the root cause: does a model field named `tags` collide with
DataFlow CreateNode's NodeMetadata.tags (a set)? Test with vs without."""

import json
import tempfile
import traceback
from pathlib import Path

out = {}


def make_db():
    from dataflow import DataFlow

    tmp = tempfile.mkdtemp(prefix="coll855_")
    uri = (Path(tmp) / "m.db").as_uri().replace("file://", "sqlite://")
    return DataFlow(database_url=uri)


# Case 1: model WITH a `tags` field (mirrors MemoryEntryModel)
try:
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    db1 = make_db()

    @db1.model
    class WithTags:
        id: str
        content: str
        tags: str

    wf = WorkflowBuilder()
    wf.add_node(
        "WithTagsCreateNode",
        "create",
        {"id": "1", "content": "x", "tags": json.dumps(["a", "b"])},
    )
    with LocalRuntime() as rt:
        rt.execute(wf.build())
    out["with_tags_field"] = "STORE_OK"
except Exception as e:
    out["with_tags_field"] = f"{type(e).__name__}: {str(e)[:140]}"

# Case 2: same model but field renamed `tag_list` (avoids reserved name)
try:
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    db2 = make_db()

    @db2.model
    class NoTags:
        id: str
        content: str
        tag_list: str

    wf = WorkflowBuilder()
    wf.add_node(
        "NoTagsCreateNode",
        "create",
        {"id": "1", "content": "x", "tag_list": json.dumps(["a", "b"])},
    )
    with LocalRuntime() as rt:
        rt.execute(wf.build())
    out["with_taglist_field"] = "STORE_OK"
except Exception as e:
    out["with_taglist_field"] = f"{type(e).__name__}: {str(e)[:140]}"

# Case 3: confirm NodeMetadata.tags really is a set type
try:
    import inspect

    from kailash.nodes.base import NodeMetadata

    ann = getattr(NodeMetadata, "__annotations__", {})
    out["NodeMetadata_has_tags_field"] = "tags" in ann
    out["NodeMetadata_tags_annotation"] = str(ann.get("tags", "ABSENT"))
except Exception as e:
    out["nodemetadata_check"] = f"{type(e).__name__}: {str(e)[:120]}"

with open("/tmp/triage/probe_collision_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("DONE")
