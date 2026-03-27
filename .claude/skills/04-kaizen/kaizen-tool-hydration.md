# Tool Search & Hydration

For agents with 30+ tools, kaizen-agents provides automatic tool hydration — only a base set of tools is sent to the LLM initially. The LLM calls `search_tools` to discover and activate additional tools on demand.

## How It Works

1. Tools split into **base set** (~15 always-available) and **deferred set**
2. LLM receives base tools + `search_tools` meta-tool
3. LLM calls `search_tools("database query")` → gets matching tool schemas
4. Matching tools are **hydrated** (added to active set) for the current request

## Usage

```python
from kaizen_agents import Delegate

# Automatic: activates when tool count > 30
delegate = Delegate(model="gpt-4o", tools=my_50_tools)
# search_tools auto-injected, hydration transparent to LLM

# Manual threshold override
from kaizen_agents.delegate.tools.hydrator import ToolHydrator
hydrator = ToolHydrator(threshold=20)
hydrator.load_tools(tool_defs, tool_executors)
```

## BM25 Search

```python
from kaizen_agents.delegate.tools.search import create_search_tools_executor

executor = create_search_tools_executor(hydrator)
results = await executor(query="database operations", top_n=5)
# Returns top-5 matching tool schemas ranked by BM25 score
```

The search uses stdlib-only BM25 scoring (no external deps) over tool names + descriptions.

## Key Design

- **LLM-first**: The LLM decides WHEN to search (not code). `search_tools` is a dumb data endpoint.
- **Below threshold**: Complete passthrough, zero overhead.
- **Force-lookup**: Tools hydrated via `search_tools` in the same tool-call batch execute immediately.

## Source Files

- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/search.py`
