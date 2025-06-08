# SharePoint Integration

```python
import os
from kailash.nodes.data import SharePointGraphReader, SharePointGraphWriter

# Read from SharePoint
workflow.add_node("sharepoint_read", SharePointGraphReader(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    operation="list_files",
    library_name="Documents"
)

# Write to SharePoint
workflow.add_node("sharepoint_write", SharePointGraphWriter(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    library_name="Reports",
    file_path="output/report.xlsx"
)
```
