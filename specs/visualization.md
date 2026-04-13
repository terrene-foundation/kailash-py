# Visualization

Visualization components for Kailash workflows and execution metrics. Two separate concerns live under this domain:

1. **Workflow structure visualization** — Mermaid and DOT diagram generation from `Workflow` graphs (in `src/kailash/workflow/`).
2. **Execution metrics visualization** — performance reports, real-time dashboards, API servers (in `src/kailash/visualization/`).

Source of truth:

- `src/kailash/workflow/visualization.py` — `WorkflowVisualizer`
- `src/kailash/workflow/mermaid_visualizer.py` — `MermaidVisualizer`
- `src/kailash/visualization/` — `performance.py`, `dashboard.py`, `live_dashboard.py`, `api.py`, `reports.py`

## Workflow structure visualization

### `WorkflowVisualizer` (`src/kailash/workflow/visualization.py`)

Generates Mermaid diagrams and DOT format output for workflow graphs. No external dependencies — outputs render natively in GitHub, VS Code, JetBrains, Jupyter, and any Mermaid-compatible viewer.

```python
class WorkflowVisualizer:
    def __init__(
        self,
        workflow: Workflow | None = None,
        direction: str = "TB",
    ):
        self.workflow = workflow
        self.direction = direction
```

**Constructor parameters** (exactly as in source):

- `workflow: Workflow | None = None` — optional workflow to visualize. Can be set at construction time or passed per-call to `to_mermaid`/`to_dot`. If both are None at call time, those methods raise `ValueError("No workflow provided")`.
- `direction: str = "TB"` — Mermaid graph direction. Supported values are Mermaid's standard: `"TB"` (top-bottom), `"BT"`, `"LR"` (left-right), `"RL"`.

There is NO `title` parameter. Titles are added only when rendering a markdown wrapper via `generate_markdown(title=...)` on the separate `MermaidVisualizer` class.

**Method: `_get_node_shape(node_type: str) -> tuple[str, str]`**

Returns Mermaid node delimiters based on substring matching on the node type. The exact vocabulary from source:

```python
def _get_node_shape(self, node_type: str) -> tuple[str, str]:
    if "Reader" in node_type or "Writer" in node_type:
        return "[(", ")]"    # stadium
    elif (
        "Switch" in node_type or "Merge" in node_type or "Conditional" in node_type
    ):
        return "{", "}"      # diamond
    elif "AI" in node_type or "LLM" in node_type or "Model" in node_type:
        return "[[", "]]"    # subroutine
    elif "Code" in node_type or "Python" in node_type:
        return "[/", "/]"    # parallelogram
    return "[", "]"          # rectangle (default)
```

The recognized substrings are (case-sensitive, exact `in` check):

- `Reader`, `Writer` → stadium `[( ... )]`
- `Switch`, `Merge`, `Conditional` → diamond `{ ... }`
- `AI`, `LLM`, `Model` → subroutine `[[ ... ]]`
- `Code`, `Python` → parallelogram `[/ ... /]`
- anything else → rectangle `[ ... ]`

Note: `WorkflowVisualizer._get_node_shape` does NOT recognize Agent, Chat, Filter, Transform, Processor, Branch, HTTP, API, or Client. The pattern-matching logic in the separate `MermaidVisualizer._get_pattern_style` class uses a broader list, but `WorkflowVisualizer` does not.

**Method: `_sanitize_id(node_id: str) -> str`**

```python
def _sanitize_id(self, node_id: str) -> str:
    return node_id.replace(" ", "_").replace("-", "_").replace(".", "_")
```

Replaces spaces, hyphens, and dots with underscores. Not a regex — just three literal replacements.

**Method: `to_mermaid(workflow: Workflow | None = None) -> str`**

Uses the caller-provided workflow if supplied, otherwise `self.workflow`. Raises `ValueError("No workflow provided")` if both are None.

The generated Mermaid string begins with:

```
graph {direction}
```

— e.g. `graph TB` for the default direction. Note: `WorkflowVisualizer.to_mermaid` uses the keyword `graph`, NOT `flowchart`. (The separate `MermaidVisualizer.generate()` uses `flowchart` — see below.)

For each node, the visualizer:

- sanitizes the id
- fetches the node instance via `wf.nodes.get(node_id)` and reads `node_instance.node_type`
- formats a label as `f"{node_id}\\n({node_type})"`
- looks up the opening/closing delimiters via `_get_node_shape(node_type)`
- emits `    {safe_id}{open}"{label}"{close}`

For nodes with no registered instance, the label is just `node_id` and shape defaults to rectangle.

For each edge:

- `from_output` and `to_input` both present: `    {src} -->|{from_output} -> {to_input}| {dst}`
- non-empty `mapping` dict: `    {src} -->|{"s->d, s->d, ..."}| {dst}`
- neither: `    {src} --> {dst}`

After nodes and edges, style classes are emitted per node with type-dependent fill/stroke:

- `Reader`/`Writer` → `fill:#e1f5fe,stroke:#01579b`
- `AI`/`LLM` → `fill:#e8f5e9,stroke:#1b5e20`
- `Switch`/`Conditional` → `fill:#fce4ec,stroke:#880e4f`
- `Code`/`Python` → `fill:#fffde7,stroke:#f57f17`

**Method: `to_dot(workflow: Workflow | None = None) -> str`**

Generates Graphviz DOT format. Header is:

```
digraph "{workflow.name}" {
    rankdir=TB;
    node [shape=box, style="rounded,filled", fontname="Arial"];
    edge [fontname="Arial", fontsize=10];
```

Note `rankdir` is hardcoded to `TB` (the constructor's `direction` parameter is NOT threaded into DOT output). Color categories use a local mapping:

```python
color_map = {
    "data":      "#e1f5fe",
    "transform": "#fff3e0",
    "logic":     "#fce4ec",
    "ai":        "#e8f5e9",
    "code":      "#fffde7",
    "default":   "#f5f5f5",
}
```

Categorization (lowercase substring match on `node_type.lower()`):

- `reader`/`writer` → `data`
- `ai`/`llm` → `ai`
- `switch`/`conditional` → `logic`
- `python`/`code` → `code`
- anything else → `default`

Each node is emitted as `"node_id" [label="node_id\\n(node_type)", fillcolor="#..."];`. Each edge is emitted as `"src" -> "dst" [label="..."];` or without a label if there is no mapping.

**Method: `visualize(output_path: str | None = None, format: str = "mermaid", **kwargs) -> str`\*\*

- If `format == "dot"`, calls `to_dot()` — otherwise calls `to_mermaid()`.
- If `output_path` is provided:
  - For `format == "mermaid"` with no file extension: appends `.md` and wraps the content in ` ```mermaid ... ``` ` fences.
  - For `format == "dot"` with no file extension: appends `.dot`.
  - Ensures parent directories exist.
- Returns the raw diagram string in every case.

**Method: `save(output_path: str, format: str = "mermaid", **kwargs) -> None`\*\*

Thin wrapper around `visualize(output_path=..., format=...)`.

**Method: `create_execution_graph(run_id: str, task_manager: Any, output_path: str | None = None) -> str`**

Generates a Markdown document with an embedded Mermaid diagram annotated with per-node execution status. Internally:

1. Calls `task_manager.list_tasks(run_id)` to get `TaskSummary` records.
2. Builds a `{node_id: TaskStatus}` mapping from the results.
3. Constructs a `MermaidVisualizer(self.workflow)` (the separate class from `mermaid_visualizer.py`) and calls `generate()` to produce the base diagram.
4. Appends status emojis to matching node lines in the generated Mermaid:
   - `TaskStatus.PENDING` → `⏳`
   - `TaskStatus.RUNNING` → `🔄`
   - `TaskStatus.COMPLETED` → `✅`
   - `TaskStatus.FAILED` → `❌`
   - `TaskStatus.SKIPPED` → `⏭️`
5. Writes the result as markdown containing run metadata, the Mermaid block, a status legend, and a task detail table with duration.
6. Writes to `output_path` if supplied, otherwise to a default path under `data/outputs/visualizations/workflow_executions/execution_{run_id}.md` relative to the project root.

Returns the output file path as a string.

### Module-level: `add_visualization_to_workflow()`

Called on import, attaches a `visualize(self, output_path=None, format="mermaid", **kwargs) -> str` method to the `Workflow` class. Thus every `Workflow` instance gets a `.visualize()` method that delegates to a freshly constructed `WorkflowVisualizer(self)`.

### `MermaidVisualizer` (`src/kailash/workflow/mermaid_visualizer.py`)

Separate class that generates richer Mermaid diagrams using a pattern-oriented style vocabulary. Used internally by `WorkflowVisualizer.create_execution_graph` and by module-level helpers that monkey-patch `Workflow`.

```python
class MermaidVisualizer:
    def __init__(
        self,
        workflow: Workflow,
        direction: str = "TB",
        node_styles: dict[str, str] | None = None,
    ):
        self.workflow = workflow
        self.direction = direction
        self.node_styles = node_styles or self._default_node_styles()
```

**Constructor parameters** (exactly as in source):

- `workflow: Workflow` — required, not optional (unlike `WorkflowVisualizer`).
- `direction: str = "TB"`
- `node_styles: dict[str, str] | None = None` — optional override dict mapping node type patterns (`"reader"`, `"writer"`, etc.) to Mermaid style strings. When None, `_default_node_styles()` returns a hardcoded mapping.

There are NO `theme`, `show_node_types`, `show_edge_labels`, `detect_patterns`, or `custom_styles` parameters. The class has no theme system — styles are either the defaults or a caller-provided `node_styles` override.

**Default node styles** (from `_default_node_styles()`):

```python
{
    "reader":    "fill:#e1f5fe,stroke:#01579b,stroke-width:2px",
    "writer":    "fill:#f3e5f5,stroke:#4a148c,stroke-width:2px",
    "transform": "fill:#fff3e0,stroke:#e65100,stroke-width:2px",
    "logic":     "fill:#fce4ec,stroke:#880e4f,stroke-width:2px",
    "ai":        "fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px",
    "api":       "fill:#f3e5f5,stroke:#4527a0,stroke-width:2px",
    "code":      "fill:#fffde7,stroke:#f57f17,stroke-width:2px",
    "default":   "fill:#f5f5f5,stroke:#424242,stroke-width:2px",
}
```

**Method: `generate() -> str`**

Returns the full Mermaid diagram string. The first line is:

```
flowchart {direction}
```

— NOT `graph {direction}`. This is a distinction from `WorkflowVisualizer.to_mermaid`.

The generator:

1. Partitions graph nodes into `source_nodes` (in-degree 0), `sink_nodes` (out-degree 0), and `intermediate_nodes` based on `workflow.graph.in_degree` / `out_degree`.
2. If there are source nodes, emits an `input_data([Input Data])` stadium node plus the section header `%% Input Data`.
3. Categorizes every workflow node into six buckets based on lowercase substring match on `node_type`: `readers`, `writers`, `routers` (`switch`/`router`/`conditional`), `mergers` (`merge`), `validators` (`valid`/`check`/`verify`), and everything else as `processors`.
4. Emits each category in its own `%% <category>` commented section. Validators and routers use `{...}` diamond shape, mergers use `((...))` circle shape, readers/writers/processors use `[...]` rectangle shape.
5. Emits flow section:
   - Connects `input_data` to each source node
   - Emits every edge with `_get_pattern_edge_label`-generated labels
   - Connects each sink node to `output_data([Output Data])`
6. Emits `%% Styling` section: styles the input/output pseudo-nodes with dashed-stroke, then styles every workflow node via `_get_pattern_style(node_type)`.

**Method: `_get_pattern_style(node_type: str) -> str`**

Returns a Mermaid fill/stroke style string based on node type (lowercased). Recognises a broader vocabulary than `WorkflowVisualizer._get_node_shape`:

- `reader` → `fill:#e1f5fe,stroke:#01579b,stroke-width:2px`
- `writer` → `fill:#f3e5f5,stroke:#4a148c,stroke-width:2px`
- `valid`/`check`/`verify` → `fill:#fff3e0,stroke:#ff6f00,stroke-width:2px`
- `error`/`fail`/`exception` → `fill:#ffebee,stroke:#c62828,stroke-width:2px`
- `switch`/`router`/`conditional` → `fill:#fce4ec,stroke:#880e4f,stroke-width:2px`
- `merge` → `fill:#f3e5f5,stroke:#4a148c,stroke-width:2px`
- `transform`/`filter`/`process`/`aggregate` → `fill:#fff3e0,stroke:#e65100,stroke-width:2px`
- `python`/`code` → `fill:#fffde7,stroke:#f57f17,stroke-width:2px`
- `ai`/`ml`/`model`/`embedding` → `fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px`
- `api`/`http`/`rest`/`graphql` → `fill:#e8eaf6,stroke:#283593,stroke-width:2px`
- everything else → `fill:#f5f5f5,stroke:#616161,stroke-width:2px`

**Method: `_get_node_style(node_type: str) -> str`**

Similar lookup, but returns entries from the constructor-supplied `self.node_styles` dict rather than the pattern-specific hardcoded strings. Covers: `reader`, `writer`, `transform/filter/processor/aggregator`, `switch/merge/conditional/logic`, `ai/llm/model/embedding`, `api/http/rest/graphql/oauth`, `python/code`, else `default`.

**Method: `_get_node_shape(node_type: str) -> tuple[str, str]`**

Returns shape brackets for a node type (lowercased):

- `reader` → `"(["`, `"])"` (stadium for inputs)
- `writer` → `"(["`, `"])"` (stadium for outputs)
- `switch`/`conditional` → `"{"`, `"}"` (rhombus for decisions)
- `merge` → `"(("`, `"))"` (circle for merge)
- everything else → `"["`, `"]"` (rectangle for processing)

**Method: `_sanitize_node_id(node_id: str) -> str`**

Regex-based: replaces every character not matching `[a-zA-Z0-9_]` with `_`, then prepends `node_` if the result starts with a digit.

**Method: `_get_node_label(node_id: str) -> str`**

Returns the node's `name` attribute if defined, else `f"{node_id}<br/>({node_type})"`. Note the `<br/>` line break (not `\n`).

**Method: `_get_pattern_label(node_id: str, node_instance) -> str`**

Returns the node's `name` attribute when present, else `f"{clean_type}<br/>{node_id}"` where `clean_type` is `node_type` with a trailing `Node` suffix stripped.

**Method: `_get_pattern_edge_label(source: str, target: str, data: dict) -> str`**

Specialized labels for validation and router patterns:

- Source node name contains `valid` or `check` AND target contains `error`/`fail` → label is `"Invalid"`.
- Source node name contains `valid` or `check` AND basic label present → `"Valid|{basic_label}"`.
- Source node name contains `valid` or `check` → `"Valid"`.
- Source node name contains `switch` or `router` and basic label starts with `"case_"` → case name titlecased.
- Otherwise, returns `_get_edge_label(source, target, data)`.

**Method: `_get_edge_label(source: str, target: str, data: dict) -> str`**

Returns:

- `f"{from_output}→{to_input}"` if both are set
- `f"{src}→{dst}"` for a single-entry mapping
- `f"{len(mapping)} mappings"` for multi-entry mapping
- `""` otherwise

**Method: `_get_node_type_label(node_type: str) -> str`**

Strips a trailing `Node` suffix (e.g. `CSVReaderNode` → `CSVReader`).

**Method: `generate_markdown(title: str | None = None) -> str`**

Returns a full markdown section:

````
## Workflow: {workflow.name}           (or "## {title}" if supplied)

_{workflow.description}_               (if present)

```mermaid
{generate()}
````

### Nodes

| Node ID | Type | Description |
| ------- | ---- | ----------- |

...

### Connections

| From | To  | Mapping |
| ---- | --- | ------- |

...

````

Description is first line of the node's docstring if available.

**Method: `save_markdown(filepath: str, title: str | None = None) -> None`**

Calls `generate_markdown(title)` and writes to `filepath`.

**Method: `save_mermaid(filepath: str) -> None`**

Calls `generate()` and writes the raw Mermaid to `filepath`.

### Module-level: `add_mermaid_to_workflow()`

Called on import, attaches three methods to `Workflow`:

- `to_mermaid(self, direction: str = "TB") -> str`
- `to_mermaid_markdown(self, title: str | None = None) -> str`
- `save_mermaid_markdown(self, filepath: str, title: str | None = None) -> None`

Each constructs a `MermaidVisualizer(self)` internally.

## Execution metrics visualization (`src/kailash/visualization/`)

### Public exports (`__init__.py`)

```python
from kailash.visualization.api import SimpleDashboardAPI
from kailash.visualization.dashboard import (
    DashboardConfig, DashboardExporter, LiveMetrics, RealTimeDashboard,
)
from kailash.visualization.performance import PerformanceVisualizer
from kailash.visualization.reports import (
    PerformanceInsight, ReportConfig, ReportFormat,
    WorkflowPerformanceReporter, WorkflowSummary,
)

# Optional — only when FastAPI is installed:
from kailash.visualization.api import DashboardAPIServer
````

### `PerformanceVisualizer` (`visualization/performance.py`)

```python
class PerformanceVisualizer:
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
```

**Constructor parameters** (exactly as in source):

- `task_manager: TaskManager` — required. Stores it as `self.task_manager`. No other parameters.

**Purpose:** Creates Markdown performance reports with embedded Mermaid bar charts. No matplotlib or seaborn dependency — pure text output that renders in any Markdown viewer that supports Mermaid.

**Method: `create_run_performance_summary(run_id: str, output_dir: Path | None = None) -> dict[str, Path]`**

1. If `output_dir` is None, defaults to `{project_root}/data/outputs/visualizations/performance`.
2. Fetches the run via `task_manager.get_run(run_id)`; raises `ValueError(f"Run {run_id} not found")` if missing.
3. Fetches tasks via `task_manager.get_run_tasks(run_id)`; logs a warning and returns `{}` if there are no tasks.
4. Calls `_create_performance_report(run, tasks, report_path)`.
5. Returns `{"report": report_path}`.

**Method: `_create_performance_report(run, tasks, output_path) -> Path`**

Writes a Markdown file containing:

- Header with run id, workflow name, start time, status, total tasks.
- Total duration, average CPU/memory/etc. computed over completed tasks with metrics.
- Mermaid bar charts (using the text-based approach of `xychart-beta bar` or similar) for per-node duration.
- Task detail table.

### `DashboardConfig` (`visualization/dashboard.py`)

```python
@dataclass
class DashboardConfig:
    update_interval: float = 1.0
    max_history_points: int = 100
    auto_refresh: bool = True
    show_completed: bool = True
    show_failed: bool = True
    theme: str = "light"    # "light" or "dark"
```

### `LiveMetrics`

```python
@dataclass
class LiveMetrics:
    timestamp: datetime = field(default_factory=datetime.now)
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_cpu_usage: float = 0.0
    total_memory_usage: float = 0.0  # MB
    throughput: float = 0.0          # tasks per minute
    avg_task_duration: float = 0.0   # seconds
```

### `RealTimeDashboard`

```python
class RealTimeDashboard:
    def __init__(
        self,
        task_manager: TaskManager,
        config: DashboardConfig | None = None,
    ):
        self.task_manager = task_manager
        self.config = config or DashboardConfig()
        self.performance_viz = PerformanceVisualizer(task_manager)
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._metrics_history: list[LiveMetrics] = []
        self._current_run_id: str | None = None
        self._status_callbacks: list[Any] = []
        self._metrics_callbacks: list[Any] = []
        self.logger = logger
```

**Constructor parameters:**

- `task_manager: TaskManager` — required
- `config: DashboardConfig | None = None` — uses `DashboardConfig()` defaults if None

**Methods:**

- `start_monitoring(run_id: str | None = None)` — begins background monitoring thread. Warns if already monitoring. Starts a daemon `threading.Thread` running `_monitor_loop`.
- `stop_monitoring()` — sets `_monitoring = False` and joins the thread with a 5-second timeout.
- `_monitor_loop()` — sleep-and-sample loop that collects `_collect_live_metrics()`, appends to `_metrics_history` (truncated to `config.max_history_points`), invokes metrics callbacks, checks for status changes, sleeps `config.update_interval` seconds.
- `_collect_live_metrics() -> LiveMetrics` — aggregates stats from `task_manager.get_run_tasks(_current_run_id)` or the most recent run if not specified.
- Additional methods for callback registration, live-report generation, and snapshot export.

### `DashboardExporter`

```python
class DashboardExporter:
    def __init__(self, dashboard: RealTimeDashboard):
        ...
```

Exports dashboard snapshots to various formats.

### `LiveDashboard` (`visualization/live_dashboard.py`)

Renders an HTML dashboard page with WebSocket-driven live updates (separate from `RealTimeDashboard`).

```python
class LiveDashboard:
    def __init__(
        self,
        ws_url: Optional[str] = None,
        title: str = "Kailash Live Dashboard",
        theme: str = "light",
        reconnect_interval_ms: int = 3000,
    ) -> None:
```

**Constructor parameters** (exactly as in source):

- `ws_url: Optional[str] = None` — WebSocket endpoint URL. If None, the generated HTML derives the URL at runtime from `window.location` (auto-detecting the host and scheme).
- `title: str = "Kailash Live Dashboard"` — HTML page title.
- `theme: str = "light"` — `"light"` or `"dark"`. Used to look up `_THEME_COLORS[self.theme]`.
- `reconnect_interval_ms: int = 3000` — milliseconds between WebSocket reconnect attempts if the connection drops.

**Methods:**

- `render() -> str` — returns the full HTML page as a string, with WebSocket URL, colors, and reconnect interval substituted into the template.
- `write(path: str | Path) -> Path` — writes the rendered HTML to the given path (creating parent directories) and returns the resolved path.

Internal: `_THEME_COLORS` is a module-level dict keyed by theme name with sub-dicts for `bg`, `card_bg`, `text`, `border`, `primary`, `success`, `danger`, `warning`.

### `ReportFormat` (Enum, `visualization/reports.py`)

```python
class ReportFormat(Enum):
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    PDF = "pdf"  # Future enhancement
```

### `ReportConfig`

```python
@dataclass
class ReportConfig:
    include_charts: bool = True
    include_recommendations: bool = True
    chart_format: str = "png"          # "png" or "svg"
    detail_level: str = "detailed"     # "summary" | "detailed" | "comprehensive"
    compare_historical: bool = True
    theme: str = "corporate"           # "light" | "dark" | "corporate"
```

### `PerformanceInsight`

```python
@dataclass
class PerformanceInsight:
    category: str       # "bottleneck" | "optimization" | "warning"
    severity: str       # "low" | "medium" | "high" | "critical"
    title: str
    description: str
    recommendation: str
    metrics: dict[str, Any] = field(default_factory=dict)
```

### `WorkflowSummary`

```python
@dataclass
class WorkflowSummary:
    run_id: str
    workflow_name: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_duration: float = 0.0
    avg_cpu_usage: float = 0.0
    peak_memory_usage: float = 0.0
    total_io_read: int = 0
    total_io_write: int = 0
    throughput: float = 0.0
    efficiency_score: float = 0.0    # 0-100
```

### `WorkflowPerformanceReporter`

```python
class WorkflowPerformanceReporter:
    def __init__(self, task_manager: TaskManager, config: ReportConfig | None = None):
        self.task_manager = task_manager
        self.config = config or ReportConfig()
        self.performance_viz = PerformanceVisualizer(task_manager)
        self.logger = logger
```

**Constructor parameters:**

- `task_manager: TaskManager` — required
- `config: ReportConfig | None = None` — uses `ReportConfig()` defaults if None

**Method: `generate_report(run_id, output_path=None, format=ReportFormat.HTML, compare_runs=None) -> Path`**

Generates a comprehensive performance report in the chosen format, optionally comparing multiple runs.

### `DashboardAPIServer` (`visualization/api.py`)

FastAPI server for dashboard REST endpoints. Only available when FastAPI is installed — otherwise the import fails and `visualization/__init__.py` omits it from `__all__`.

```python
class DashboardAPIServer:
    def __init__(
        self,
        task_manager: TaskManager,
        dashboard_config: DashboardConfig | None = None,
    ):
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI is required for API server functionality. "
                              "Install with: pip install fastapi uvicorn")
        self.task_manager = task_manager
        self.dashboard_config = dashboard_config or DashboardConfig()
        self.dashboard = RealTimeDashboard(task_manager, self.dashboard_config)
        self.reporter = WorkflowPerformanceReporter(task_manager)
        self._websocket_connections: list[Any] = []
        self._broadcast_task: asyncio.Task | None = None
        self.app = FastAPI(
            title="Kailash Dashboard API",
            description="Real-time workflow performance monitoring API",
            version="1.0.0",
        )
        # CORS middleware, routes registered via _register_routes()
```

**Constructor parameters:**

- `task_manager: TaskManager` — required
- `dashboard_config: DashboardConfig | None = None`

**Routes registered via `_register_routes()`:**

- `GET /health` — health check returning `{"status": "healthy", "timestamp": datetime.now()}`
- `GET /api/v1/runs` — paginated list of runs (`limit`, `offset` query params), returning `RunResponse[]`
- Additional endpoints for run detail, metrics snapshots, performance reports, WebSocket updates (exact list is in `_register_routes()`).

### `SimpleDashboardAPI` (`visualization/api.py`)

FastAPI-free variant.

```python
class SimpleDashboardAPI:
    def __init__(
        self,
        task_manager: TaskManager,
        dashboard_config: DashboardConfig | None = None,
    ):
        self.task_manager = task_manager
        self.dashboard_config = dashboard_config or DashboardConfig()
        self.dashboard = RealTimeDashboard(task_manager, self.dashboard_config)
        self.reporter = WorkflowPerformanceReporter(task_manager)
        self.logger = logger
```

**Methods (plain Python, no HTTP):**

- `get_runs(limit: int = 10, offset: int = 0) -> list[dict[str, Any]]` — returns paginated list of runs as plain dicts with `run_id`, `workflow_name`, `status`, `started_at`, `ended_at`, `total_tasks`, `completed_tasks`, `failed_tasks`.
- `get_run_details(run_id: str) -> dict[str, Any] | None` — returns full run details or None.

## Design Notes

- `WorkflowVisualizer` (in `workflow/visualization.py`) and `MermaidVisualizer` (in `workflow/mermaid_visualizer.py`) are two separate classes with different APIs and output formats. `WorkflowVisualizer.to_mermaid` emits `graph TB` with a narrow shape vocabulary; `MermaidVisualizer.generate` emits `flowchart TB` with a broader pattern-style vocabulary.
- Both modules attach methods to the `Workflow` class at import time via `add_visualization_to_workflow()` and `add_mermaid_to_workflow()`. As a result, importing either module has the side effect of adding `.visualize()` / `.to_mermaid()` / `.to_mermaid_markdown()` / `.save_mermaid_markdown()` to every `Workflow` instance.
- Performance visualization (`visualization/performance.py`) emits Markdown with Mermaid charts rather than matplotlib/seaborn images, so reports work in any Markdown-rendering environment without graphics dependencies.
- `LiveDashboard` (HTML page + WebSocket) is separate from `RealTimeDashboard` (background-thread monitor). The former is a standalone HTML artifact; the latter is a programmatic monitoring loop.
- `DashboardAPIServer` raises `ImportError` at construction time if FastAPI is not installed. `SimpleDashboardAPI` is the no-FastAPI alternative and returns plain dicts/lists.
