# Control Protocol Quickstart Tutorial

Build your first interactive AI agent in 10 minutes.

---

## What You'll Build

An interactive file processor that:
1. **Asks the user** which file to process
2. **Requests approval** before taking action
3. **Reports progress** during processing

**Why?** Traditional AI agents are "fire-and-forget"—they run autonomously without user input. The Control Protocol enables **human-in-the-loop** workflows where agents can ask questions, seek approval, and provide real-time feedback.

---

## Prerequisites

- **Kaizen installed:** `pip install kailash-kaizen`
- **Basic Python knowledge:** async/await, dataclasses
- **5 minutes** of your time

---

## Step 1: Import Dependencies

```python
import anyio
from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
```

**What's happening:**
- `BaseAgent`: Your agent base class
- `Signature`: Defines agent's input/output schema
- `ControlProtocol`: Manages bidirectional communication
- `CLITransport`: Enables terminal-based interaction (stdin/stderr)

---

## Step 2: Define Your Agent's Signature

```python
class FileProcessorSignature(Signature):
    """What the agent takes as input and returns as output."""

    file_path: str = InputField(description="Path to file")
    operation: str = InputField(description="Operation to perform")
    result: str = OutputField(description="Processing result")
```

**What's happening:**
- `InputField`: What the agent needs to know
- `OutputField`: What the agent will produce
- This signature tells the agent's LLM what to expect and return

---

## Step 3: Configure Your Agent

```python
@dataclass
class FileProcessorConfig:
    """Agent configuration."""

    llm_provider: str = "ollama"  # or "openai", "anthropic"
    model: str = "llama3.2:latest"  # or "gpt-4", "claude-3"
    temperature: float = 0.7
```

**What's happening:**
- Choose your LLM provider (Ollama is free and local)
- Select a model (larger = smarter but slower)
- Set temperature (0.0 = deterministic, 1.0 = creative)

---

## Step 4: Create Your Interactive Agent

```python
class InteractiveFileProcessor(BaseAgent):
    """An agent that interacts with the user during processing."""

    async def process_interactively(self, available_files: list[str]):
        """Main processing workflow with user interaction."""

        # Step 1: Ask user which file to process
        selected_file = await self.ask_user_question(
            question="Which file would you like me to process?",
            options=available_files,
            timeout=30.0
        )

        # Step 2: Request approval before processing
        approved = await self.request_approval(
            action=f"Analyze and summarize {selected_file}",
            details={
                "file": selected_file,
                "estimated_time": "30 seconds",
                "will_modify": False
            },
            timeout=60.0
        )

        if not approved:
            return {"status": "cancelled", "reason": "User denied approval"}

        # Step 3: Report progress while processing
        await self.report_progress("Starting analysis...")

        # Run the actual LLM processing
        result = self.run(
            file_path=selected_file,
            operation="analyze and summarize"
        )

        await self.report_progress("Analysis complete!", percentage=100.0)

        # Extract the result
        summary = self.extract_str(result, "result", default="No summary generated")

        return {
            "status": "success",
            "file": selected_file,
            "summary": summary
        }
```

**What's happening:**
- `ask_user_question()`: Blocks execution until user answers (30s timeout)
- `request_approval()`: Blocks until user approves/denies (60s timeout)
- `report_progress()`: Fire-and-forget, doesn't block (just informs user)
- `self.run()`: Runs the actual LLM inference
- `self.extract_str()`: Safely extracts output from LLM result

---

## Step 5: Run Your Agent

```python
async def main():
    """Run the interactive file processor."""

    # Setup: Create transport for terminal interaction
    transport = CLITransport()
    await transport.connect()

    # Setup: Create control protocol
    protocol = ControlProtocol(transport)

    # Setup: Create agent with control protocol enabled
    agent = InteractiveFileProcessor(
        config=FileProcessorConfig(),
        control_protocol=protocol  # This enables interactive methods!
    )

    # Run: Start protocol and execute agent
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)  # Start message handling

        # Execute your interactive workflow
        result = await agent.process_interactively(
            available_files=["data.csv", "report.pdf", "notes.txt"]
        )

        print(f"\nFinal Result: {result}")

        await protocol.stop()  # Stop message handling

    # Cleanup
    await transport.close()


if __name__ == "__main__":
    anyio.run(main)
```

**What's happening:**
1. **Transport:** Connects to terminal (stdin/stderr)
2. **Protocol:** Handles message routing between agent and user
3. **Agent:** Created with `control_protocol=protocol` to enable interactive methods
4. **Task Group:** Starts background message handling
5. **Execution:** Runs your workflow
6. **Cleanup:** Stops protocol and closes transport

---

## Step 6: Run It!

```bash
python your_script.py
```

**Expected Output:**
```
Which file would you like me to process?
  1. data.csv
  2. report.pdf
  3. notes.txt
Enter your choice (1-3): 1

Analyze and summarize data.csv?
Details:
  - file: data.csv
  - estimated_time: 30 seconds
  - will_modify: False
Approve? (yes/no): yes

[Progress] Starting analysis...
[Progress] Analysis complete! (100%)

Final Result: {
  'status': 'success',
  'file': 'data.csv',
  'summary': 'This CSV contains sales data with 1,000 rows...'
}
```

---

## Complete Code

```python
import anyio
from dataclasses import dataclass
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport


class FileProcessorSignature(Signature):
    file_path: str = InputField(description="Path to file")
    operation: str = InputField(description="Operation to perform")
    result: str = OutputField(description="Processing result")


@dataclass
class FileProcessorConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2:latest"
    temperature: float = 0.7


class InteractiveFileProcessor(BaseAgent):
    async def process_interactively(self, available_files: list[str]):
        # Ask which file
        selected_file = await self.ask_user_question(
            "Which file would you like me to process?",
            options=available_files,
            timeout=30.0
        )

        # Request approval
        approved = await self.request_approval(
            f"Analyze and summarize {selected_file}",
            details={
                "file": selected_file,
                "estimated_time": "30 seconds",
                "will_modify": False
            }
        )

        if not approved:
            return {"status": "cancelled"}

        # Process with progress
        await self.report_progress("Starting analysis...")

        result = self.run(
            file_path=selected_file,
            operation="analyze and summarize"
        )

        await self.report_progress("Complete!", percentage=100.0)

        return {
            "status": "success",
            "file": selected_file,
            "summary": self.extract_str(result, "result", default="No summary")
        }


async def main():
    transport = CLITransport()
    await transport.connect()

    protocol = ControlProtocol(transport)

    agent = InteractiveFileProcessor(
        config=FileProcessorConfig(),
        control_protocol=protocol
    )

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        result = await agent.process_interactively(
            ["data.csv", "report.pdf", "notes.txt"]
        )

        print(f"\nResult: {result}")

        await protocol.stop()

    await transport.close()


if __name__ == "__main__":
    anyio.run(main)
```

**Lines of code:** ~60 (including imports and whitespace)

**Time to build:** 10 minutes

---

## Understanding the Flow

### Without Control Protocol (Traditional)
```
[Agent starts] → [Agent finishes] → [Result returned]
```
- **User role:** None (fire-and-forget)
- **Control:** Zero
- **Visibility:** Only final result

### With Control Protocol (Interactive)
```
[Agent starts]
    ↓
[Agent asks question] → [User answers] → [Agent continues]
    ↓
[Agent requests approval] → [User approves/denies] → [Agent continues/stops]
    ↓
[Agent reports progress] → [User sees updates]
    ↓
[Agent finishes] → [Result returned]
```
- **User role:** Active participant
- **Control:** Full (can guide and veto)
- **Visibility:** Real-time updates

---

## Next Steps

### Add More Interactivity

```python
# Multiple questions
language = await self.ask_user_question(
    "Output language?",
    options=["English", "Spanish", "French"]
)

format_type = await self.ask_user_question(
    "Output format?",
    options=["JSON", "Markdown", "Plain text"]
)

# Multiple approvals
if await self.request_approval("Download external data?"):
    download_data()

if await self.request_approval("Store results in database?"):
    save_to_db()

# Granular progress
for i, item in enumerate(items):
    await self.report_progress(
        f"Processing {item}",
        percentage=(i / len(items)) * 100,
        details={"current": i+1, "total": len(items)}
    )
```

### Use Different Transports

**HTTP (for web apps):**
```python
from kaizen.core.autonomy.control.transports import HTTPTransport

transport = HTTPTransport(base_url="http://localhost:3000")
# Agent questions will POST to http://localhost:3000/control
# Agent progress will stream via SSE from http://localhost:3000/control/events
```

**Stdio (for subprocess coordination):**
```python
from kaizen.core.autonomy.control.transports import StdioTransport

transport = StdioTransport()
# Agent uses stdout/stdin for parent process communication
```

### Handle Errors Gracefully

```python
try:
    answer = await self.ask_user_question(
        "Critical decision?",
        timeout=10.0
    )
except TimeoutError:
    # User didn't respond in time
    answer = "default_safe_option"
    await self.report_progress("No response - using safe default")
```

---

## Common Patterns

### Pattern 1: Sequential Workflow

```python
# Step-by-step guided workflow
step1 = await agent.ask_user_question("Choose step 1 option:", options=[...])
step2 = await agent.ask_user_question("Choose step 2 option:", options=[...])
step3 = await agent.ask_user_question("Choose step 3 option:", options=[...])

if await agent.request_approval(f"Execute workflow with {step1}, {step2}, {step3}?"):
    execute_workflow(step1, step2, step3)
```

### Pattern 2: Conditional Branches

```python
mode = await agent.ask_user_question(
    "Processing mode?",
    options=["safe", "aggressive"]
)

if mode == "aggressive":
    # Aggressive mode requires extra approval
    if not await agent.request_approval("Aggressive mode may cause data loss"):
        mode = "safe"

process(mode=mode)
```

### Pattern 3: Long-Running Operations

```python
await agent.report_progress("Downloading dataset...")
download()

await agent.report_progress("Training model...", percentage=0.0)
for epoch in range(10):
    train_epoch()
    await agent.report_progress(
        f"Epoch {epoch+1}/10",
        percentage=((epoch+1) / 10) * 100
    )

await agent.report_progress("Complete!", percentage=100.0)
```

---

## Troubleshooting

### "Control protocol not configured"

**Problem:** You created the agent without `control_protocol` parameter

**Solution:**
```python
# ❌ Wrong
agent = BaseAgent(config=config, signature=signature)

# ✅ Correct
agent = BaseAgent(config=config, signature=signature, control_protocol=protocol)
```

### "Transport not ready"

**Problem:** You forgot to call `transport.connect()`

**Solution:**
```python
transport = CLITransport()
await transport.connect()  # Don't forget this!
```

### Methods hang/timeout immediately

**Problem:** Protocol not started in task group

**Solution:**
```python
async with anyio.create_task_group() as tg:
    await protocol.start(tg)  # Must be inside task group!
    # ... your code ...
```

---

## What's Next?

- **API Reference:** Full documentation of all methods ([`docs/reference/control-protocol-api.md`](../reference/control-protocol-api.md))
- **Examples:** Working code in `examples/autonomy/`
- **Architecture:** Design decisions in [ADR-011](../architecture/adr/ADR-011-bidirectional-agent-communication.md)
- **Advanced:** Multi-agent coordination with Control Protocol

---

## Summary

**You've learned:**
1. ✅ How to create an interactive AI agent
2. ✅ How to ask questions with `ask_user_question()`
3. ✅ How to request approval with `request_approval()`
4. ✅ How to report progress with `report_progress()`
5. ✅ How to choose and use different transports
6. ✅ How to handle errors gracefully

**Key takeaway:** The Control Protocol transforms AI agents from fire-and-forget scripts into collaborative assistants that work **with** users, not just **for** them.

---

**Happy building!** 🚀

If you run into issues, check the [API Reference](../reference/control-protocol-api.md) or open an issue on GitHub.

---

**Last Updated:** 2025-10-19
