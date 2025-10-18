---
name: dataflow-installation
description: "DataFlow installation and setup guide. Use when asking 'install dataflow', 'dataflow setup', or 'dataflow requirements'."
---

# DataFlow Installation Guide

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> SDK Version: `0.9.25+`
> Related Skills: [`dataflow-specialist`](dataflow-specialist.md), [`dataflow-quickstart`](dataflow-quickstart.md)

## Installation

```bash
# Install DataFlow
pip install kailash-dataflow

# With PostgreSQL support
pip install kailash-dataflow[postgresql]

# With all database drivers
pip install kailash-dataflow[all]
```

## Requirements

- Python 3.9+
- kailash SDK 0.9.25+
- SQLite (included) or PostgreSQL 12+

## Quick Setup

```python
from dataflow import DataFlow

# SQLite (default)
db = DataFlow("sqlite:///my_app.db")

# PostgreSQL
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Initialize schema
db.initialize_schema()
```

## Verification

```python
# Test connection
print(db.connection_string)

# Verify models are loaded
print(db.list_models())
```

## Documentation

- **Installation Guide**: [`sdk-users/apps/dataflow/01-installation.md`](../../../../sdk-users/apps/dataflow/01-installation.md)

<!-- Trigger Keywords: install dataflow, dataflow setup, dataflow requirements, dataflow installation -->
