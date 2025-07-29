# SharePoint Integration

## Basic Setup

```python
import os
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import SharePointGraphReader, SharePointGraphWriter

# Create workflow
workflow = WorkflowBuilder()

# Read from SharePoint
workflow.add_node("sharepoint_read", SharePointGraphReader(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    operation="list_files",
    library_name="Documents"
)

# Process data
workflow.add_node("DataProcessorNode", "processor", {}))

# Write to SharePoint
workflow.add_node("sharepoint_write", SharePointGraphWriter(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    library_name="Reports",
    file_path="output/report.xlsx"
)

# Connect nodes
workflow.add_connection("sharepoint_read", "result", "processor", "input")
workflow.add_connection("processor", "result", "sharepoint_write", "input")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Common Operations

### List Files
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("list_files", SharePointGraphReader(),
    operation="list_files",
    library_name="Documents",
    folder_path="/reports/2024"  # Optional: specific folder
)

```

### Download File
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("download", SharePointGraphReader(),
    operation="download_file",
    library_name="Documents",
    file_path="data/source.csv",
    local_path="downloads/source.csv"
)

```

### Upload File with Metadata
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("upload", SharePointGraphWriter(),
    file_path="reports/analysis.xlsx",
    library_name="Reports",
    metadata={
        "Title": "Q4 Analysis",
        "Department": "Finance",
        "Status": "Final"
    }
)

```

## Multi-Tenant Pattern

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Use parameter override for different tenants
for tenant in ["tenant_a", "tenant_b"]:
    tenant_config = get_tenant_config(tenant)

runtime = LocalRuntime()
# Parameters setup
results, run_id = runtime.execute(workflow, parameter_overrides={
        "sharepoint_read": {
            "tenant_id": tenant_config["tenant_id"],
            "client_id": tenant_config["client_id"],
            "client_secret": tenant_config["client_secret"],
            "site_url": tenant_config["site_url"]
        }
    })

```

## Error Handling

```python
try:
    results, run_id = runtime.execute(workflow.build())
except Exception as e:
    if "401" in str(e):
        print("Authentication failed. Check credentials.")
    elif "404" in str(e):
        print("Site or file not found.")
    else:
        print(f"SharePoint error: {e}")

```

## Environment Variables

```bash
# .env file
SHAREPOINT_TENANT_ID=your-tenant-id
SHAREPOINT_CLIENT_ID=your-client-id
SHAREPOINT_CLIENT_SECRET=your-client-secret
```

## Common Pitfalls

1. **Missing Permissions**: Ensure app registration has Sites.ReadWrite.All
2. **Wrong Site URL**: Use full site URL, not just domain
3. **Path Separators**: Use forward slashes (/) in SharePoint paths
4. **Large Files**: Use chunked upload for files > 4MB

## Next Steps
- [Multi-tenant patterns](014-access-control-multi-tenancy.md)
- [Production example](../workflows/integrations/sharepoint/sharepoint_multi_auth_example.py)
