"""Settle the warm round-trip with CORRECT DataFlow DSN forms. The prior probe
used Path.as_uri().replace -> sqlite:///tmp/... (3-slash = RELATIVE -> unable to
open). Test the DSN forms DataFlow actually documents. No tag_list fix applied
yet here -> test a NON-colliding model first to isolate DSN from the tags bug."""

import json
import os
import tempfile
import traceback
from pathlib import Path

r = {"cases": {}}


def try_dsn(label, dsn, workdir=None):
    try:
        from dataflow import DataFlow
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        cwd0 = os.getcwd()
        if workdir:
            os.chdir(workdir)
        try:
            db = DataFlow(database_url=dsn)

            @db.model
            class Thing:
                id: str
                content: str
                tag_list: str

            wf = WorkflowBuilder()
            wf.add_node(
                "ThingCreateNode",
                "create",
                {"id": "1", "content": "hello", "tag_list": "[]"},
            )
            with LocalRuntime() as rt:
                res, _ = rt.execute(wf.build())
            cres = res.get("create")
            if isinstance(cres, dict) and cres.get("error"):
                return f"CREATE_ERROR: {str(cres['error'])[:120]}"
            # read back
            wf2 = WorkflowBuilder()
            wf2.add_node("ThingListNode", "list", {})
            with LocalRuntime() as rt:
                res2, _ = rt.execute(wf2.build())
            lres = res2.get("list")
            if isinstance(lres, dict) and lres.get("error"):
                return f"LIST_ERROR: {str(lres['error'])[:120]}"
            return f"OK list={repr(lres)[:160]}"
        finally:
            os.chdir(cwd0)
    except Exception as e:
        return f"EXC {type(e).__name__}: {str(e)[:120]}"


tmp = tempfile.mkdtemp(prefix="dsn_")
abs_db = str(Path(tmp) / "m.db")

# 4-slash absolute (SQLAlchemy canonical absolute sqlite)
r["cases"]["4slash_abs"] = try_dsn("4slash", f"sqlite:////{abs_db.lstrip('/')}")
# DataFlow-doc form with absolute path appended after 3 slashes
r["cases"]["3slash_abs"] = try_dsn("3slash_abs", f"sqlite:///{abs_db}")
# relative, but cwd set to tmp (so 'm.db' resolves)
r["cases"]["relative_in_cwd"] = try_dsn("relcwd", "sqlite:///m.db", workdir=tmp)
# bare path (no scheme variations) — what DataFlow("sqlite:///memory.db") uses
r["cases"]["doc_form_relcwd"] = try_dsn("docform", "sqlite:///memory.db", workdir=tmp)

open("/tmp/triage/probe_dsn_result.json", "w").write(
    json.dumps(r, indent=2, default=str)
)
print("WROTE")
