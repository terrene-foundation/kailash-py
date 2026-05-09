# Unified Agent API - Implementation Blueprint

Technical specification for implementing the unified Agent class.

---

## File Structure

```
kailash-kaizen/
├── src/kaizen/
│   ├── __init__.py                    # Export Agent, AgentManager
│   ├── core/
│   │   ├── agents.py                  # Unified Agent class
│   │   ├── base_agent.py              # Foundation (used internally)
│   │   ├── config.py                  # BaseAgentConfig
│   │   └── presets.py                 # Agent type and workflow presets
│   ├── agents/specialized/            # Thin wrappers for backward compat
├── tests/unit/test_unified_agent.py   # 100+ unit tests
├── tests/integration/test_unified_agent_integration.py
└── examples/unified_agent/            # 20+ examples
```

---

## Core Implementation (`src/kaizen/core/agents.py`)

```python
from typing import Literal, Optional, List, Dict, Any, Callable, Union
import logging, uuid

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.core.presets import AGENT_TYPE_PRESETS, WORKFLOW_PRESETS
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.memory import (
    BaseMemory, BufferMemory, PersistentBufferMemory,
    SummaryMemory, VectorMemory, KnowledgeGraphMemory, SharedMemoryPool,
)
from kaizen.core.autonomy.hooks import HookManager
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage

logger = logging.getLogger(__name__)

class Agent:
    """
    Universal agent — ONE entry point, configuration-driven behavior.

    Layers:
        1. Zero-config: Agent(model=os.environ["LLM_MODEL"])
        2. Configured: Agent(model=os.environ["LLM_MODEL"], agent_type="react", memory_turns=20)
        3. Expert: Agent(model=os.environ["LLM_MODEL"], memory=CustomMemory())
    """

    def __init__(
        self,
        model: str,
        provider: str = "openai",
        agent_id: Optional[str] = None,
        agent_type: Literal["simple","cot","react","rag","autonomous","reflection"] = "simple",
        workflow: Optional[Literal["supervisor_worker","consensus","debate","sequential","handoff"]] = None,
        multimodal: Optional[List[Literal["vision","audio","document"]]] = None,
        memory_turns: int = 10,
        memory_type: Literal["buffer","persistent","summary","vector","knowledge_graph"] = "buffer",
        memory_backend: Literal["file","sqlite","postgresql"] = "file",
        shared_memory: Optional[SharedMemoryPool] = None,
        tools: Union[Literal["all"], List[str], Literal[False]] = "all",
        auto_approve_safe: bool = True,
        require_approval: bool = False,
        max_cycles: int = 10,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        budget_limit_usd: Optional[float] = 1.0,
        checkpoint_frequency: int = 5,
        checkpointing: bool = True,
        observability: bool = True,
        tracing_only: bool = False,
        rich_output: bool = True,
        verbosity: Literal["quiet","normal","verbose"] = "normal",
        streaming: bool = False,
        progress_reporting: bool = True,
        show_cost: bool = True,
        workers: Optional[List['Agent']] = None,
        workflow_config: Optional[Dict[str, Any]] = None,
        # Expert overrides
        signature: Optional[Signature] = None,
        memory: Optional[BaseMemory] = None,
        hook_manager: Optional[HookManager] = None,
        state_manager: Optional[StateManager] = None,
        control_protocol: Optional['ControlProtocol'] = None,
        mcp_client: Optional['MCPClient'] = None,
        approval_callback: Optional[Callable] = None,
        error_handler: Optional[Callable] = None,
        **kwargs
    ):
        self.model = model
        self.provider = provider
        self.agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        self._agent_type = agent_type
        self._workflow = workflow
        self._multimodal = multimodal or []
        self._config = { ... }  # Store all config params

        self._setup_smart_defaults()
        self._apply_agent_type(agent_type)
        if multimodal: self._apply_multimodal(multimodal)
        if workflow: self._apply_workflow(workflow, workers, workflow_config)
        self._setup_infrastructure(memory=memory, hook_manager=hook_manager,
            state_manager=state_manager, control_protocol=control_protocol,
            mcp_client=mcp_client)
        self._base_agent = self._create_base_agent(
            signature=signature, approval_callback=approval_callback,
            error_handler=error_handler, shared_memory=shared_memory, **kwargs)
        if rich_output and verbosity != "quiet":
            self._show_startup_banner()
```

### Setup Methods

```python
    def _setup_smart_defaults(self):
        self._memory_config = {"type": ..., "turns": ..., "backend": ..., "enabled": True}
        self._tools_config = {"enabled": True, "tools": "all", "auto_approve_safe": True}
        self._observability_config = {"enabled": True, "tracing": True, "metrics": True, "logging": True}
        self._checkpoint_config = {"enabled": True, "frequency": 5, "storage": "filesystem", "compress": True}
        self._budget_config = {"limit_usd": 1.0, "warn_at": 0.75, "error_at": 1.0}

    def _apply_agent_type(self, agent_type: str):
        preset = AGENT_TYPE_PRESETS[agent_type]  # raises if unknown
        self._strategy = preset["strategy"]
        self._max_cycles = preset.get("max_cycles", self._config["max_cycles"])
        if not preset.get("tools_enabled", True): self._tools_config["enabled"] = False
        if preset.get("reasoning_steps"): self._reasoning_enabled = True
        if preset.get("convergence"): self._convergence_strategy = preset["convergence"]
        if preset.get("required_tools"): self._required_tools = preset["required_tools"]
        if preset.get("checkpointing_required"): self._checkpoint_config["enabled"] = True
        if preset.get("reflection_enabled"): self._reflection_enabled = True

    def _apply_multimodal(self, modalities: List[str]):
        self._vision_enabled = "vision" in modalities
        self._audio_enabled = "audio" in modalities
        self._document_enabled = "document" in modalities

    def _apply_workflow(self, workflow, workers, config):
        preset = WORKFLOW_PRESETS[workflow]
        if "workers" in preset["required_params"] and not workers:
            raise ValueError(f"Workflow '{workflow}' requires 'workers'")
        self._workflow_preset = preset
        self._workers = workers or []
        self._workflow_config = config or {}
```

### Infrastructure Setup

```python
    def _setup_infrastructure(self, memory=None, hook_manager=None,
                               state_manager=None, control_protocol=None, mcp_client=None):
        # Each: use expert override if provided, else create smart default, else None
        self._memory = memory or (self._create_default_memory() if self._memory_config["enabled"] else None)
        self._hook_manager = hook_manager or (self._create_default_hook_manager() if self._observability_config["enabled"] else None)
        self._state_manager = state_manager or (self._create_default_state_manager() if self._checkpoint_config["enabled"] else None)
        self._control_protocol = control_protocol
        self._mcp_client = mcp_client

    def _create_default_memory(self) -> BaseMemory:
        t, turns, backend = self._memory_config["type"], self._memory_config["turns"], self._memory_config["backend"]
        return {
            "buffer": lambda: BufferMemory(max_turns=turns),
            "persistent": lambda: PersistentBufferMemory(
                db_path=f".kaizen/memory/{self.agent_id}.db" if backend == "sqlite"
                else f".kaizen/memory/{self.agent_id}.jsonl", max_turns=turns),
            "summary": lambda: SummaryMemory(llm_provider=self.provider, model=self.model, max_turns=turns),
            "vector": lambda: VectorMemory(embedding_provider=self.provider, max_turns=turns),
            "knowledge_graph": lambda: KnowledgeGraphMemory(llm_provider=self.provider, model=self.model, max_turns=turns),
        }[t]()

    def _create_default_hook_manager(self) -> HookManager:
        hm = HookManager()
        if self._observability_config["tracing"]:
            from kaizen.core.autonomy.observability import register_tracing_hooks; register_tracing_hooks(hm)
        if self._observability_config["metrics"]:
            from kaizen.core.autonomy.observability import register_metrics_hooks; register_metrics_hooks(hm)
        if self._observability_config["logging"]:
            from kaizen.core.autonomy.observability import register_logging_hooks; register_logging_hooks(hm)
        return hm

    def _create_default_state_manager(self) -> StateManager:
        storage = FilesystemStorage(base_dir=f".kaizen/checkpoints/{self.agent_id}", compress=True)
        return StateManager(storage=storage, checkpoint_frequency=self._checkpoint_config["frequency"], retention_count=10)
```

### Public API

```python
    def run(self, *args, **kwargs) -> Dict[str, Any]:
        if self._config["progress_reporting"]: self._show_progress_start()
        try:
            result = self._base_agent.run(*args, **kwargs)
            if self._budget_config["limit_usd"]: self._check_budget(result)
            if self._config["rich_output"]: self._show_completion(result)
            return result
        except Exception as e:
            return self._handle_execution_error(e, *args, **kwargs)

    async def run_async(self, *args, **kwargs) -> Dict[str, Any]:
        # Async equivalent of run()

    def _check_budget(self, result):
        cost, limit = result.get("cost_usd", 0), self._budget_config["limit_usd"]
        if cost >= limit: raise RuntimeError(f"Budget exceeded: ${cost:.3f} >= ${limit:.2f}")
        if cost >= limit * 0.75: logger.warning(f"Approaching budget: ${cost:.3f}/{limit:.2f}")

    # Helpers delegated to BaseAgent
    def extract_list(self, result, key, default=None): return self._base_agent.extract_list(result, key, default)
    def extract_dict(self, result, key, default=None): return self._base_agent.extract_dict(result, key, default)
    def extract_float(self, result, key, default=0.0): return self._base_agent.extract_float(result, key, default)
    def extract_str(self, result, key, default=""): return self._base_agent.extract_str(result, key, default)
    def write_to_memory(self, content, tags=None, importance=0.5): return self._base_agent.write_to_memory(content, tags, importance)
    def to_a2a_card(self): return self._base_agent.to_a2a_card()
    def get_config(self) -> Dict[str, Any]: ...
    def get_features(self) -> Dict[str, bool]: ...
```

### AgentManager

```python
class AgentManager:
    """Manage multiple agents with shared memory coordination."""

    def __init__(self, shared_memory: Optional[SharedMemoryPool] = None):
        self.agents: Dict[str, Agent] = {}
        self.shared_memory = shared_memory or SharedMemoryPool()

    def create_agent(self, agent_id: str, **kwargs) -> Agent:
        agent = Agent(agent_id=agent_id, shared_memory=self.shared_memory, **kwargs)
        self.agents[agent_id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]: return self.agents.get(agent_id)
    def list_agents(self) -> List[str]: return list(self.agents.keys())
```

---

## Presets (`src/kaizen/core/presets.py`)

```python
AGENT_TYPE_PRESETS = {
    "simple":     {"strategy": "single_shot", "max_cycles": 1,   "tools_enabled": False, "memory_type": "buffer"},
    "cot":        {"strategy": "single_shot", "max_cycles": 1,   "tools_enabled": False, "memory_type": "buffer",
                   "reasoning_steps": True, "prompt_modifier": "Think step by step:"},
    "react":      {"strategy": "multi_cycle", "max_cycles": 10,  "tools_enabled": True,  "memory_type": "persistent",
                   "convergence": "satisfaction"},
    "rag":        {"strategy": "single_shot", "max_cycles": 1,   "tools_enabled": True,  "memory_type": "vector",
                   "required_tools": ["vector_search"]},
    "autonomous": {"strategy": "multi_cycle", "max_cycles": 100, "tools_enabled": True,  "memory_type": "persistent",
                   "checkpointing_required": True, "convergence": "goal_achieved"},
    "reflection": {"strategy": "multi_cycle", "max_cycles": 5,   "tools_enabled": False, "memory_type": "persistent",
                   "reflection_enabled": True},
}

WORKFLOW_PRESETS = {
    "supervisor_worker": {"required_params": ["workers"], "pattern_class": "SupervisorWorkerPattern"},
    "consensus":         {"required_params": ["agents"],  "pattern_class": "ConsensusPattern"},
    "debate":            {"required_params": ["agents"],  "pattern_class": "DebatePattern"},
    "sequential":        {"required_params": ["agents"],  "pattern_class": "SequentialPattern"},
    "handoff":           {"required_params": ["agents"],  "pattern_class": "HandoffPattern"},
}
```

---

## Package Export (`src/kaizen/__init__.py`)

```python
from kaizen.core.agents import Agent, AgentManager
__all__ = [..., "Agent", "AgentManager"]
```

---

## Testing Strategy

```python
class TestLayer1ZeroConfig:
    def test_agent_creation_minimal(self):
        agent = Agent(model=os.environ["LLM_MODEL"])
        assert agent.model == "gpt-4"
        assert agent.agent_id is not None

    def test_default_features_enabled(self):
        agent = Agent(model=os.environ["LLM_MODEL"])
        features = agent.get_features()
        assert all(features[k] for k in ["memory", "tools", "observability", "checkpointing"])

class TestLayer2Configuration:
    def test_agent_type_react(self):
        agent = Agent(model=os.environ["LLM_MODEL"], agent_type="react")
        assert agent._agent_type == "react"
        assert agent._tools_config["enabled"] is True
        assert agent._max_cycles == 10

    def test_disable_features(self):
        agent = Agent(model=os.environ["LLM_MODEL"], memory=False, tools=False, observability=False, checkpointing=False)
        features = agent.get_features()
        assert not any(features[k] for k in ["memory", "tools", "observability", "checkpointing"])

class TestLayer3ExpertOverride:
    def test_custom_memory(self):
        custom_memory = BufferMemory(max_turns=50)
        agent = Agent(model=os.environ["LLM_MODEL"], memory=custom_memory)
        assert agent._memory is custom_memory
```

**Coverage target**: 100+ unit tests across all 3 layers, 20+ integration tests.
