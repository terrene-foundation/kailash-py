# Kaizen Advanced Patterns

## Control Protocol — Human-in-the-Loop Agents

The Control Protocol enables bidirectional agent-client communication: agents can ask questions, request approval, and report progress during execution.

### Quick Start

```python
import anyio
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

class FileProcessorSignature(Signature):
    file_path: str = InputField(description="Path to file")
    operation: str = InputField(description="Operation to perform")
    result: str = OutputField(description="Processing result")

class InteractiveFileProcessor(BaseAgent):
    async def process_interactively(self, available_files: list[str]):
        # Ask user which file to process (blocks until answered)
        selected_file = await self.ask_user_question(
            "Which file would you like me to process?",
            options=available_files, timeout=30.0
        )

        # Request approval before acting (blocks until approved/denied)
        approved = await self.request_approval(
            f"Analyze and summarize {selected_file}",
            details={"file": selected_file, "estimated_time": "30 seconds"}
        )
        if not approved:
            return {"status": "cancelled"}

        # Report progress (fire-and-forget, doesn't block)
        await self.report_progress("Starting analysis...")
        result = self.run(file_path=selected_file, operation="analyze and summarize")
        await self.report_progress("Complete!", percentage=100.0)

        return {"status": "success", "summary": self.extract_str(result, "result")}

async def main():
    transport = CLITransport()
    await transport.connect()
    protocol = ControlProtocol(transport)
    config = BaseAgentConfig(agent_id="file-processor", model=os.environ.get("LLM_MODEL", "gpt-4"))
    agent = InteractiveFileProcessor(config=config, control_protocol=protocol)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)
        result = await agent.process_interactively(["data.csv", "report.pdf"])
        await protocol.stop()
    await transport.close()
```

### Transports

| Transport           | Use Case                | Setup                                             |
| ------------------- | ----------------------- | ------------------------------------------------- |
| `CLITransport`      | Terminal/stdin          | `CLITransport()`                                  |
| `HTTPTransport`     | Web apps                | `HTTPTransport(base_url="http://localhost:3000")` |
| `StdioTransport`    | Subprocess coordination | `StdioTransport()`                                |
| `InMemoryTransport` | Testing                 | In-memory, no I/O                                 |

### Common Patterns

- **Sequential workflow**: Chain multiple `ask_user_question()` calls, then `request_approval()` for the whole plan
- **Conditional branches**: Ask mode (safe/aggressive), require extra approval for dangerous modes
- **Long-running ops**: Use `report_progress()` with percentage in loops

---

## Meta-Controller Routing — A2A Capability Matching

Routes requests to the best-fit agent using semantic capability matching via Google's A2A protocol. No hardcoded if/else routing logic.

### Routing Strategies

```python
from kaizen.orchestration.pipeline import Pipeline

# Semantic routing (A2A capability matching) — best for specialized agents
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)
result = pipeline.run(task="Analyze sales data and create visualization")
# Routes to data_agent (score: 0.9)

# Round-robin — best for identical agents (load balancing)
pipeline = Pipeline.router(agents=[worker1, worker2, worker3], routing_strategy="round-robin")

# Random — simple load distribution or A/B testing
pipeline = Pipeline.router(agents=[agent1, agent2], routing_strategy="random")
```

### How A2A Matching Works

Every BaseAgent auto-generates an A2A capability card via `agent.to_a2a_card()`. The router scores each agent's capabilities against the task and selects the highest scorer.

```python
# Debug capability matching
for agent in agents:
    card = agent.to_a2a_card()
    for cap in card.primary_capabilities:
        score = cap.matches_requirement("Your task here")
        print(f"{agent.agent_id}: {cap.name} = {score}")
```

### Error Handling

```python
# Graceful (default) — returns error dict
pipeline = Pipeline.router(agents=agents, error_handling="graceful")
result = pipeline.run(task="Task")
if "error" in result:
    handle_error(result)

# Fail-fast — raises exception
pipeline = Pipeline.router(agents=agents, error_handling="fail-fast")
```

### A2A Integration Across Patterns

- **Router**: Direct semantic routing to best agent
- **Supervisor-Worker**: `selection_mode="semantic"` for semantic worker selection
- **Ensemble**: `discovery_mode="a2a", top_k=3` to discover top-k agents
- **Blackboard**: `selection_mode="semantic"` for dynamic specialist selection

---

## Journey Orchestration (Layer 5)

Declarative multi-step user journeys with intent-driven transitions.

```python
from kaizen.journey import Journey, Pathway, Transition, IntentTrigger, JourneyConfig

class IntakeSignature(Signature):
    __intent__ = "Gather patient symptoms and preferences"
    __guidelines__ = ["Ask symptoms before demographics", "Use empathetic language"]
    message: str = InputField(desc="Patient message")
    symptoms: list = OutputField(desc="Extracted symptoms")

class PatientJourney(Journey):
    __entry_pathway__ = "intake"
    __transitions__ = [
        Transition(trigger=IntentTrigger(intents=["help", "faq"]), to_pathway="faq")
    ]

    class IntakePath(Pathway):
        __signature__ = IntakeSignature
        __agents__ = ["intake_agent"]
        __accumulate__ = ["symptoms", "preferences"]  # Persist across pathways
        __next__ = "booking"

    class FAQPath(Pathway):
        __return_behavior__ = ReturnToPrevious()  # Returns to previous pathway after FAQ

journey = PatientJourney(session_id="patient-123", config=JourneyConfig())
journey.manager.register_agent("intake_agent", intake_agent)
await journey.start()
response = await journey.process_message("I have back pain")
```

### Key Concepts

- **Pathways**: Named stages in a user flow, each with its own signature and agents
- **Transitions**: Intent-driven moves between pathways (LLM-powered intent detection, not keyword/regex)
- **Context accumulation**: Merge strategies: REPLACE, APPEND, UNION, SUM
- **Return behaviors**: `ReturnToPrevious` for detours (FAQ, help), `ReturnToSpecific` for error handling
- **Hooks**: 9 lifecycle events (PRE/POST_PATHWAY_EXECUTE, PRE/POST_TRANSITION, etc.)
- **Nexus deployment**: `deploy_journey_to_nexus()` for API/CLI/MCP
