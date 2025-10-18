---
name: dataflow-deployment
description: "DataFlow production deployment patterns. Use when asking 'deploy dataflow', 'dataflow production', or 'dataflow docker'."
---

# DataFlow Production Deployment

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install DataFlow
RUN pip install kailash-dataflow[postgresql]

COPY . /app

# Run migrations
RUN python -c "from dataflow import DataFlow; db = DataFlow(os.getenv('DATABASE_URL')); db.initialize_schema()"

CMD ["python", "app.py"]
```

## Environment Configuration

```python
import os
from dataflow import DataFlow

# Use environment variable for connection
db = DataFlow(os.getenv("DATABASE_URL"))

# Production settings
db.configure(
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    echo_sql=False  # Disable SQL logging in production
)
```

## Documentation

- **Deployment Guide**: [`sdk-users/apps/dataflow/10-deployment.md`](../../../../sdk-users/apps/dataflow/10-deployment.md)

<!-- Trigger Keywords: deploy dataflow, dataflow production, dataflow docker, dataflow kubernetes -->
