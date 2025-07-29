# SDK Development Without Docker

This guide is for developers who cannot or prefer not to use Docker. You'll have reduced functionality but can still run basic examples.

## Limitations

Without Docker, you won't have:
- Multiple PostgreSQL databases
- MongoDB for document storage
- Qdrant for vector operations
- Kafka for streaming
- Mock API endpoints
- MCP server integration

## Alternative Setup

### 1. PostgreSQL (Choose One)

**Option A: Direct Installation**
```bash
# macOS
brew install postgresql@15
brew services start postgresql@15

# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Create user and database
createuser -s kailash
createdb -O kailash transactions
```

**Option B: Use SQLite (Simplest)**
```bash
# No installation needed - SQLite is included with Python
# Examples will automatically use SQLite when PostgreSQL is unavailable
```

### 2. Ollama (For LLM Examples)

Ollama can be installed directly without Docker:

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull a small model
ollama pull llama3.2:1b
```

### 3. Environment Configuration

Create `.env.no-docker` file:

```bash
# Minimal configuration for no-Docker setup
NO_DOCKER=true
SDK_DEV_MODE=false

# Use SQLite instead of PostgreSQL
TRANSACTION_DB=sqlite:///transactions.db
COMPLIANCE_DB=sqlite:///compliance.db
ANALYTICS_DB=sqlite:///analytics.db
CRM_DB=sqlite:///crm.db

# Ollama (if installed)
OLLAMA_HOST=http://localhost:11434

# Disable services that require Docker
KAFKA_BROKERS=
MONGO_URL=
QDRANT_URL=
MCP_SERVER_URL=

# Use placeholder URLs for examples
WEBHOOK_API=http://example.com
FRAUD_ALERT_API=http://example.com
NOTIFICATION_API=http://example.com
```

### 4. Running Examples

#### Minimal Examples (Work without infrastructure)
```bash
export NO_DOCKER=true
source .env.no-docker

# These will work
python financial_processor_minimal.py
python lead_scoring_minimal.py
```

#### Modified Examples
Some examples need modification to work without Docker:

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

# Replace KafkaConsumerNode with file reading
# Instead of:
kafka_consumer = KafkaConsumerNode()

# Use:
csv_reader = CSVReaderNode(file_path="sample_transactions.csv")

# Replace MongoDB operations with file storage
# Instead of:
mongo_writer = MongoDBWriterNode()

# Use:
json_writer = JSONWriterNode(file_path="output.json")

```

### 5. Testing with Limited Infrastructure

Run only tests that don't require full infrastructure:

```bash
# Skip infrastructure tests
pytest -m "not requires_infrastructure"

# Run only unit tests
pytest tests/test_nodes/ -k "not integration"

# Run with SQLite
DATABASE_URL=sqlite:///test.db pytest
```

## Workarounds for Common Patterns

### 1. Streaming Data (No Kafka)
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

# Use file watching instead
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileStreamNode(Node):
    def run(self, **kwargs):
        # Watch directory for new files
        # Process them as they arrive

```

### 2. Vector Search (No Qdrant)
```python
# Use in-memory search with numpy
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class SimpleVectorSearch:
    def __init__(self):
        self.vectors = []
        self.metadata = []

    def add(self, vector, metadata):
        self.vectors.append(vector)
        self.metadata.append(metadata)

    def search(self, query_vector, k=5):
        similarities = cosine_similarity([query_vector], self.vectors)[0]
        top_k = np.argsort(similarities)[-k:][::-1]
        return [(self.metadata[i], similarities[i]) for i in top_k]

```

### 3. Document Storage (No MongoDB)
```python
# Use JSON files as document store
import json
from pathlib import Path

class FileDocumentStore:
    def __init__(self, base_path="./documents"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)

    def insert(self, doc_id, document):
        path = self.base_path / f"{doc_id}.json"
        with open(path, 'w') as f:
            json.dump(document, f)

    def find(self, doc_id):
        path = self.base_path / f"{doc_id}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

```

## Gradual Migration Path

1. **Start Simple**: Use SQLite and file-based storage
2. **Add Ollama**: Install for LLM capabilities
3. **Add PostgreSQL**: When you need real SQL features
4. **Consider Docker**: When you need the full ecosystem

## Getting Help

- Most examples have minimal versions that work without infrastructure
- Check example README files for specific requirements
- Use `NO_DOCKER=true` environment variable for simplified behavior
- See [INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md) for full Docker setup when ready

## Why Docker is Recommended

While this guide helps you get started without Docker, the full SDK experience requires:
- Multiple coordinated services
- Consistent environments across developers
- Easy reset and cleanup
- Realistic testing scenarios

Consider revisiting Docker installation when possible for the complete development experience.
