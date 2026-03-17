# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Level 0: Zero-config workflow execution.

Run a workflow with no environment variables, no database, no configuration.
Kailash uses SQLite and in-memory stores by default.

Usage:
    python level0_app.py
"""

from kailash import WorkflowBuilder, LocalRuntime


def main() -> None:
    # Build a two-node workflow: generate text, then transform it
    builder = WorkflowBuilder()

    builder.add_node(
        "PythonCodeNode",
        "generate",
        {
            "code": (
                "import datetime\n"
                "now = datetime.datetime.now(datetime.timezone.utc)\n"
                "output = f'Report generated at {now.isoformat()}'\n"
            ),
            "output_type": "str",
        },
    )

    builder.add_node(
        "PythonCodeNode",
        "transform",
        {
            "code": "output = text.upper().replace(' ', '_')",
            "inputs": {"text": "str"},
            "output_type": "str",
        },
    )

    builder.connect("generate", "transform", mapping={"output": "text"})

    wf = builder.build()

    # Execute with zero configuration
    runtime = LocalRuntime()
    results, run_id = runtime.execute(wf)

    print(f"Run ID: {run_id}")
    print(f"Generate output: {results.get('generate', {})}")
    print(f"Transform output: {results.get('transform', {})}")


if __name__ == "__main__":
    main()
