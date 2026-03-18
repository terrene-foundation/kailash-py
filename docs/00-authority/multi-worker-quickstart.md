# Multi-Worker Quickstart

Get Kailash running with multiple workers in 5 minutes.

---

## Prerequisites

- Python 3.10+
- Docker and Docker Compose (for PostgreSQL and Redis)
- `pip install kailash`

---

## Step 1: Start Infrastructure

Create a `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: kailash
      POSTGRES_USER: kailash
      POSTGRES_PASSWORD: kailash
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

Start it:

```bash
docker compose up -d
```

---

## Step 2: Set Environment Variables

```bash
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
```

Add these to your `.env` file for persistence:

```
KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
KAILASH_QUEUE_URL=redis://localhost:6379/0
```

---

## Step 3: Write a Workflow

Create `my_workflow.py`:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "step_1", {
    "code": "import time; time.sleep(2); result = {'processed': True}"
})
built = workflow.build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built)
print(f"Run {run_id}: {results['step_1']}")
```

Test it locally first (single-process, no workers needed):

```bash
python my_workflow.py
```

---

## Step 4: Submit to the Queue

Create `submit.py` to submit workflows for worker processing:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.distributed import DistributedRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "step_1", {
    "code": "import time; time.sleep(2); result = {'processed': True}"
})
built = workflow.build()

runtime = DistributedRuntime()

# Submit 10 workflows — workers will process them in parallel
for i in range(10):
    run_id = runtime.submit(built, parameters={"batch_index": i})
    print(f"Submitted: {run_id}")
```

```bash
python submit.py
```

---

## Step 5: Start Workers

Open separate terminal windows (each with the same environment variables):

```bash
# Terminal 2
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
python -m kailash.worker
```

```bash
# Terminal 3
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
python -m kailash.worker
```

Each worker pulls tasks from the queue independently. The 10 submitted workflows are distributed across the available workers automatically.

---

## Step 6: Verify Execution

Check workflow results:

```python
from kailash.runtime.distributed import DistributedRuntime

runtime = DistributedRuntime()
status = runtime.get_status(run_id)
print(f"Status: {status.state}")
print(f"Results: {status.results}")
```

Or query the database directly:

```bash
psql postgresql://kailash:kailash@localhost:5432/kailash \
  -c "SELECT run_id, state, created_at FROM executions ORDER BY created_at DESC LIMIT 10;"
```

---

## Scaling Workers

Add more workers at any time — no restarts, no reconfiguration:

```bash
# Start 4 workers in the background
for i in {1..4}; do
  python -m kailash.worker &
done
```

Workers are stateless. They connect to the shared database for state and to Redis for task dispatch. Start as many as your workload requires. Stop them gracefully with SIGTERM — in-progress workflows will be checkpointed and re-queued.

---

## Using PostgreSQL as the Queue

If you prefer not to run Redis, use PostgreSQL for both storage and queue:

```bash
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
export KAILASH_QUEUE_URL=postgresql://kailash:kailash@localhost:5432/kailash
```

PostgreSQL uses `SELECT ... FOR UPDATE SKIP LOCKED` for task dispatch. This works well for moderate throughput and eliminates Redis as a dependency. Use Redis when you need lower dispatch latency under high concurrency.

---

## Cleanup

```bash
docker compose down -v   # Stop and remove volumes
```

---

## Next Steps

- Read the full [Progressive Infrastructure](progressive-infrastructure.md) guide for all four levels
- See [Store Backends](02-store-backends.md) for detailed store configuration
- See [Architecture](00-architecture.md) for the system design overview
