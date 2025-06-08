# Workflow as REST API

```python
from kailash.api.workflow_api import WorkflowAPI

# Expose any workflow as REST API in 3 lines
api = WorkflowAPI(workflow)
api.run(port=8000)

# Endpoints created:
# POST /execute - Execute workflow
# GET /workflow/info - Get workflow metadata
# GET /health - Health check
# GET /docs - OpenAPI documentation
```
