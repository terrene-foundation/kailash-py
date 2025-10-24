# Migrating to Control Protocol

**Audience**: Developers with existing Kaizen agents
**Time**: 10 minutes
**Goal**: Add interactive capabilities to your agents

---

## Why Migrate?

**Before Control Protocol** (Fire-and-forget):
- Agent runs autonomously without user input
- No way to ask clarifying questions
- No approval workflow for dangerous operations
- No progress updates during long operations

**After Control Protocol** (Interactive):
- ✅ Agent can ask user questions during execution
- ✅ User can approve/deny dangerous actions
- ✅ Real-time progress updates
- ✅ Human-in-the-loop workflows

---

## Migration Steps

### Step 1: Add Control Protocol Dependency

No package changes needed - Control Protocol is built into Kaizen.

### Step 2: Update Agent Initialization

**Before:**
```python
from kaizen.core.base_agent import BaseAgent

class DataProcessor(BaseAgent):
    def process(self, data):
        # Process without user interaction
        result = self.run(task=f"Process {data}")
        return result
```

**After:**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

class DataProcessor(BaseAgent):
    def __init__(self, config, control_protocol=None):
        super().__init__(config=config, control_protocol=control_protocol)

    async def process(self, data):
        # Can now use interactive methods!
        result = self.run(task=f"Process {data}")
        return result
```

### Step 3: Add Interactive Methods

**Before:**
```python
class DataProcessor(BaseAgent):
    def process(self, file_path):
        # No way to confirm with user
        content = read_file(file_path)
        result = self.run(task=f"Analyze {content}")
        return result
```

**After:**
```python
class DataProcessor(BaseAgent):
    async def process(self, file_path):
        # Ask user for confirmation
        approved = await self.request_approval(
            action=f"Read and analyze {file_path}",
            details={"file": file_path, "size": get_file_size(file_path)}
        )

        if not approved:
            return {"status": "cancelled"}

        # Report progress
        await self.report_progress("Reading file...")
        content = read_file(file_path)

        await self.report_progress("Analyzing content...")
        result = self.run(task=f"Analyze {content}")

        await self.report_progress("Complete!", percentage=100.0)
        return result
```

### Step 4: Update Entry Point

**Before:**
```python
def main():
    agent = DataProcessor(config=config)
    result = agent.process("data.csv")
    print(result)

if __name__ == "__main__":
    main()
```

**After:**
```python
import anyio

async def main():
    # Setup transport and protocol
    transport = CLITransport()
    await transport.connect()
    protocol = ControlProtocol(transport)

    # Create agent with protocol
    agent = DataProcessor(config=config, control_protocol=protocol)

    # Run with protocol started
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        result = await agent.process("data.csv")
        print(result)

        await protocol.stop()

    await transport.close()

if __name__ == "__main__":
    anyio.run(main())
```

---

## Complete Example: Before & After

### Before Migration (Non-Interactive)

```python
# old_agent.py - Fire-and-forget agent
from kaizen.core.base_agent import BaseAgent
from dataclasses import dataclass

@dataclass
class ProcessorConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2:latest"

class FileProcessor(BaseAgent):
    def process_files(self, files):
        results = []
        for file in files:
            result = self.run(task=f"Summarize {file}")
            results.append(result)
        return results

def main():
    agent = FileProcessor(config=ProcessorConfig())
    files = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
    results = agent.process_files(files)

    for file, result in zip(files, results):
        print(f"{file}: {result}")

if __name__ == "__main__":
    main()
```

### After Migration (Interactive)

```python
# new_agent.py - Interactive agent with Control Protocol
import anyio
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from dataclasses import dataclass

@dataclass
class ProcessorConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2:latest"

class FileProcessor(BaseAgent):
    async def process_files(self, files):
        # Ask user which files to process
        selected = await self.ask_user_question(
            question="Which file should I process first?",
            options=files
        )

        # Request approval
        approved = await self.request_approval(
            action=f"Process {len(files)} files",
            details={"files": files, "estimated_time": f"{len(files) * 30}s"}
        )

        if not approved:
            return {"status": "cancelled"}

        # Process with progress updates
        results = []
        for i, file in enumerate(files):
            await self.report_progress(
                f"Processing {file}",
                percentage=(i / len(files)) * 100
            )

            result = self.run(task=f"Summarize {file}")
            results.append(result)

        await self.report_progress("Complete!", percentage=100.0)
        return results

async def main():
    # Setup Control Protocol
    transport = CLITransport()
    await transport.connect()
    protocol = ControlProtocol(transport)

    # Create agent with protocol
    agent = FileProcessor(config=ProcessorConfig(), control_protocol=protocol)

    # Run with protocol
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        files = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
        results = await agent.process_files(files)

        print(f"\nResults: {results}")

        await protocol.stop()

    await transport.close()

if __name__ == "__main__":
    anyio.run(main())
```

---

## Common Patterns

### Pattern 1: Conditional Interaction

Only use Control Protocol when available:

```python
class FlexibleAgent(BaseAgent):
    async def process(self, data):
        # Check if Control Protocol enabled
        if self.control_protocol is not None:
            # Interactive mode
            approved = await self.request_approval(f"Process {data}")
            if not approved:
                return None
        else:
            # Non-interactive mode (backward compatible)
            pass

        return self.run(task=f"Process {data}")
```

### Pattern 2: Batch Approval

Ask once for batch operations:

```python
async def process_batch(self, items):
    # Single approval for entire batch
    approved = await self.request_approval(
        action=f"Process {len(items)} items",
        details={"count": len(items), "estimated_time": f"{len(items) * 5}s"}
    )

    if not approved:
        return []

    results = []
    for i, item in enumerate(items):
        await self.report_progress(f"Item {i+1}/{len(items)}", percentage=(i / len(items)) * 100)
        result = self.run(task=f"Process {item}")
        results.append(result)

    return results
```

### Pattern 3: Error Recovery

Use questions for error recovery:

```python
async def process_with_recovery(self, data):
    try:
        return self.run(task=f"Process {data}")
    except ProcessingError as e:
        # Ask user how to proceed
        action = await self.ask_user_question(
            question=f"Processing failed: {e}. What should I do?",
            options=["retry", "skip", "abort"]
        )

        if action == "retry":
            return await self.process_with_recovery(data)  # Recursive retry
        elif action == "skip":
            return None
        else:
            raise
```

---

## Backward Compatibility

**Good news**: Control Protocol is fully backward compatible!

### Agents Work Without Protocol

```python
# This still works - no Control Protocol needed
agent = MyAgent(config=config)  # control_protocol=None (default)
result = agent.run(task="...")

# But these will raise RuntimeError if control_protocol is None:
# await agent.ask_user_question(...)  # RuntimeError
# await agent.request_approval(...)   # RuntimeError
# await agent.report_progress(...)    # RuntimeError
```

### Graceful Degradation

```python
class SmartAgent(BaseAgent):
    async def process(self, data):
        # Only ask if protocol available
        if self.control_protocol:
            approved = await self.request_approval(f"Process {data}")
            if not approved:
                return None

        return self.run(task=f"Process {data}")
```

---

## Migration Checklist

- [ ] Update agent `__init__` to accept `control_protocol` parameter
- [ ] Pass `control_protocol` to `super().__init__()`
- [ ] Change synchronous methods to `async def`
- [ ] Add interactive method calls where appropriate
- [ ] Update entry point to use `anyio.run()` and `async def main()`
- [ ] Create transport and protocol in main
- [ ] Use `async with anyio.create_task_group()` for protocol lifecycle
- [ ] Test interactive workflow manually
- [ ] Add error handling for user cancellation
- [ ] Update documentation/examples

---

## Testing Interactive Agents

### Manual Testing

```bash
# Run your interactive agent
python new_agent.py

# You'll see prompts:
# "Which file should I process first?"
# "Process 3 files? [Approve/Deny]"
# "[Progress] Processing doc1.pdf (33%)"
```

### Automated Testing

```python
import pytest
from tests.utils.mock_transport import MockTransport

@pytest.mark.asyncio
async def test_interactive_agent():
    transport = MockTransport()
    protocol = ControlProtocol(transport)

    agent = MyAgent(config=config, control_protocol=protocol)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        # Queue responses for testing
        async def auto_respond():
            await anyio.sleep(0.1)
            transport.queue_response("approval", {"approved": True})

        tg.start_soon(auto_respond)

        result = await agent.process("test data")
        assert result is not None

        await protocol.stop()
```

---

## Troubleshooting

### "RuntimeError: Control protocol not configured"

**Problem**: Calling interactive methods without control_protocol

**Solution**: Pass control_protocol when creating agent:
```python
agent = MyAgent(config=config, control_protocol=protocol)
```

### "Methods hang indefinitely"

**Problem**: Forgot to call `protocol.start(tg)`

**Solution**: Start protocol in task group:
```python
async with anyio.create_task_group() as tg:
    await protocol.start(tg)  # Required!
    await agent.process(...)
```

### "Transport not ready"

**Problem**: Forgot to call `transport.connect()`

**Solution**: Connect transport before creating protocol:
```python
await transport.connect()  # Required!
protocol = ControlProtocol(transport)
```

---

## Next Steps

1. **Migrate one agent** as a pilot
2. **Test thoroughly** with real workflows
3. **Gather feedback** from team
4. **Migrate remaining agents** gradually
5. **Consider advanced features** (HTTP transport, custom transports)

---

## See Also

- **Tutorial**: [Control Protocol Quickstart](control-protocol-tutorial.md)
- **API Reference**: [Control Protocol API](../reference/control-protocol-api.md)
- **Examples**: `examples/autonomy/`

---

**Last Updated**: 2025-10-20
