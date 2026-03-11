# Claude Code Parity Tools Developer Guide

## Overview

The Claude Code Parity Tools (TODO-207) implement full tool parity with Claude Code's autonomous capabilities. These tools enable bidirectional user communication, plan management, notebook editing, and process control - all essential for autonomous agent workflows.

## Architecture

```
kaizen/tools/native/
├── todo_tool.py         # TodoWriteTool - task list management
├── notebook_tool.py     # NotebookEditTool - Jupyter notebook editing
├── interaction_tool.py  # AskUserQuestionTool - user communication
├── planning_tool.py     # EnterPlanMode/ExitPlanMode - plan workflow
└── process_tool.py      # KillShell/TaskOutput - process management
```

## Tool Categories

| Category | Tools | Count |
|----------|-------|-------|
| `interaction` | TodoWriteTool, NotebookEditTool, AskUserQuestionTool | 3 |
| `planning` | EnterPlanModeTool, ExitPlanModeTool | 2 |
| `process` | KillShellTool, TaskOutputTool | 2 |

## Quick Start

```python
from kaizen.tools.native import KaizenToolRegistry

# Register all Claude Code parity tools
registry = KaizenToolRegistry()
registry.register_defaults(categories=["interaction", "planning", "process"])

# Now 7 additional tools are available:
# - todo_write, notebook_edit, ask_user_question
# - enter_plan_mode, exit_plan_mode
# - kill_shell, task_output
```

## Interaction Tools

### TodoWriteTool

Manages structured task lists for tracking progress during autonomous execution.

```python
from kaizen.tools.native import TodoWriteTool

tool = TodoWriteTool()

# Create a todo list
result = await tool.execute(todos=[
    {
        "content": "Implement feature X",
        "status": "in_progress",
        "activeForm": "Implementing feature X"
    },
    {
        "content": "Write tests",
        "status": "pending",
        "activeForm": "Writing tests"
    }
])

print(result.output)  # Summary of todo list
print(tool.get_display())  # Formatted display
```

**Key Features:**
- Three statuses: `pending`, `in_progress`, `completed`
- `activeForm` field for present-continuous display
- Warns when multiple items are `in_progress`
- Change callbacks for UI integration

### NotebookEditTool

Edits Jupyter notebook (.ipynb) cells with replace, insert, and delete operations.

```python
from kaizen.tools.native import NotebookEditTool

tool = NotebookEditTool()

# Replace cell content
result = await tool.execute(
    notebook_path="/path/to/notebook.ipynb",
    new_source="print('Updated!')",
    cell_id="cell-001",
    cell_type="code",
    edit_mode="replace"
)

# Insert new cell after cell-001
result = await tool.execute(
    notebook_path="/path/to/notebook.ipynb",
    new_source="# New Section",
    cell_id="cell-001",  # Insert after this cell
    cell_type="markdown",
    edit_mode="insert"
)

# Delete a cell
result = await tool.execute(
    notebook_path="/path/to/notebook.ipynb",
    new_source="",  # Ignored for delete
    cell_id="cell-002",
    edit_mode="delete"
)
```

**Key Features:**
- Three edit modes: `replace`, `insert`, `delete`
- Two cell types: `code`, `markdown`
- Creates new notebook if inserting into non-existent file
- Validates notebook structure

### AskUserQuestionTool

Enables bidirectional communication with users during autonomous execution.

```python
from kaizen.tools.native import AskUserQuestionTool, Question, QuestionAnswer

# Define a callback to handle questions
async def user_callback(questions: list) -> list:
    # In a real app, this would prompt the user
    return [QuestionAnswer(
        question_index=0,
        selected_labels=["React"]
    )]

tool = AskUserQuestionTool(user_callback=user_callback)

result = await tool.execute(questions=[
    {
        "question": "Which framework should we use?",
        "header": "Framework",  # Max 12 chars
        "options": [
            {"label": "React", "description": "Popular UI library"},
            {"label": "Vue", "description": "Progressive framework"},
            {"label": "Angular", "description": "Full framework"},
        ],
        "multiSelect": False  # Single selection
    }
])

print(result.output)  # "Q0: React"
```

**Key Features:**
- 1-4 questions per call
- 2-4 options per question
- Multi-select support
- Timeout handling (default 5 minutes)
- Supports sync and async callbacks

## Planning Tools

### EnterPlanModeTool & ExitPlanModeTool

Manage plan mode workflow for implementation planning before code changes.

```python
from kaizen.tools.native import PlanModeManager

# Create manager (tools share state)
manager = PlanModeManager()
enter_tool = manager.create_enter_tool()
exit_tool = manager.create_exit_tool()

# Enter plan mode
result = await enter_tool.execute()
print(manager.is_active)  # True

# Exit with permissions
result = await exit_tool.execute(
    allowedPrompts=[
        {"tool": "Bash", "prompt": "run tests"},
        {"tool": "Bash", "prompt": "install dependencies"}
    ]
)
print(manager.is_ready_for_approval)  # True

# Approve and implement
manager.approve()
print(manager.state.mode)  # "approved"
```

**Plan Mode States:**
1. `inactive` - Not in plan mode
2. `active` - Planning phase (exploring, designing)
3. `ready_for_approval` - Plan complete, awaiting approval
4. `approved` - Ready to implement

## Process Management Tools

### KillShellTool & TaskOutputTool

Manage background processes and retrieve their output.

```python
from kaizen.tools.native import ProcessManager, KillShellTool, TaskOutputTool

# Create shared process manager
pm = ProcessManager()
kill_tool = KillShellTool(process_manager=pm)
output_tool = TaskOutputTool(process_manager=pm)

# Register a background task (usually done by BashTool)
from kaizen.tools.native.process_tool import TaskType
task = pm.register_task("shell-001", TaskType.SHELL)
pm.start_task("shell-001")
pm.update_output("shell-001", "Running npm install...")

# Get task output (non-blocking)
result = await output_tool.execute(
    task_id="shell-001",
    block=False  # Don't wait for completion
)
print(result.output)  # "Running npm install..."

# Wait for completion (blocking)
result = await output_tool.execute(
    task_id="shell-001",
    block=True,
    timeout=30000  # Max 30 seconds
)

# Kill a background shell
result = await kill_tool.execute(shell_id="shell-001")
print(result.output)  # "Shell shell-001 killed successfully"
```

**TaskOutputTool Parameters:**
- `task_id` (required): Task identifier
- `block` (default True): Wait for completion
- `timeout` (default 30000): Max wait time in ms (max 600000)

## Full Registration Example

```python
from kaizen.tools.native import KaizenToolRegistry

# Register all 19 native tools
registry = KaizenToolRegistry()
registry.register_defaults(categories=[
    "file",        # 7 tools
    "bash",        # 1 tool
    "search",      # 2 tools
    "agent",       # 2 tools
    "interaction", # 3 tools (TODO-207)
    "planning",    # 2 tools (TODO-207)
    "process"      # 2 tools (TODO-207)
])

print(f"Total tools: {len(registry)}")  # 19

# Get all tool schemas for LLM
schemas = registry.get_tool_schemas()
```

## Creating Custom Callbacks

### User Question Callback

```python
from kaizen.tools.native import (
    AskUserQuestionTool,
    Question,
    QuestionAnswer
)

async def interactive_callback(questions: list[Question]) -> list[QuestionAnswer]:
    """Interactive callback that prompts user."""
    answers = []
    for i, q in enumerate(questions):
        print(f"\n{q.question}")
        for j, opt in enumerate(q.options):
            print(f"  {j+1}. {opt.label}: {opt.description}")

        choice = input("Enter number: ")
        selected = q.options[int(choice) - 1].label

        answers.append(QuestionAnswer(
            question_index=i,
            selected_labels=[selected]
        ))
    return answers

tool = AskUserQuestionTool(user_callback=interactive_callback)
```

### Plan Mode Callbacks

```python
from kaizen.tools.native import PlanModeManager, PlanState

def on_enter_plan(state: PlanState):
    """Called when entering plan mode."""
    print(f"Entered plan mode at {state.entered_at}")
    # Enable planning UI mode

def on_exit_plan(state: PlanState):
    """Called when exiting plan mode."""
    print(f"Plan ready with {len(state.allowed_prompts)} permissions")
    # Show approval dialog

manager = PlanModeManager(
    on_enter=on_enter_plan,
    on_exit=on_exit_plan
)
```

## Integration with LocalKaizenAdapter

The tools integrate seamlessly with LocalKaizenAdapter's TAOD loop:

```python
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.tools.native import KaizenToolRegistry

# Create registry with Claude Code parity tools
registry = KaizenToolRegistry()
registry.register_defaults(categories=[
    "file", "bash", "search",
    "interaction", "planning", "process"
])

# Create adapter with registry
adapter = LocalKaizenAdapter(tool_registry=registry)

# Run autonomous task
result = await adapter.run(
    task="Build a REST API with tests",
    max_cycles=100
)
```

## Testing

All tools have comprehensive test coverage:

| Module | Tests |
|--------|-------|
| test_todo_tool.py | 47 |
| test_notebook_tool.py | 29 |
| test_interaction_tool.py | 42 |
| test_planning_tool.py | 40 |
| test_process_tool.py | 56 |
| **Total TODO-207** | **214** |
| **Full native tools** | **451** |

Run tests:

```bash
# TODO-207 tools only
pytest tests/unit/tools/native/test_todo_tool.py \
       tests/unit/tools/native/test_notebook_tool.py \
       tests/unit/tools/native/test_interaction_tool.py \
       tests/unit/tools/native/test_planning_tool.py \
       tests/unit/tools/native/test_process_tool.py -v

# All native tools
pytest tests/unit/tools/native/ -v
```

## Best Practices

1. **Use PlanModeManager** for coordinated planning tools
2. **Share ProcessManager** between KillShellTool and TaskOutputTool
3. **Set callbacks early** for AskUserQuestionTool
4. **Validate notebook paths** are absolute before calling NotebookEditTool
5. **Handle timeouts** for AskUserQuestionTool (default 5 min)
6. **Use non-blocking mode** for TaskOutputTool when checking status
