# Cluster B — Agent / AgentTeam / KaizenConfig Class-Model Investigation

**Issue**: #822 — pyright reportAttributeAccessIssue cascade in `packages/kailash-kaizen/src/kaizen/core/framework.py`.
**Scope**: 13+ pyright warnings citing `Agent.role`, `Agent.expertise`, `Agent.capabilities`, `Agent.behavior_traits`, `Agent.authority_level`, `Agent._generate_role_based_prompt`, `AgentTeam.conflict_resolution`, `AgentTeam.performance_optimization`, `KaizenConfig.get`, plus `coordination_workflow`/`parser`/`validator` Optional/None warnings.

All file:line citations verified against the working tree on 2026-05-05.

---

## 1. Agent class — declared attributes

`packages/kailash-kaizen/src/kaizen/core/agents.py:34-83`

- **Kind**: plain Python class (NOT dataclass, NOT Pydantic). No class-body type annotations.
- **`__init__` signature** (line 42-50): `agent_id: str`, `config: Dict[str, Any]`, `signature: Optional[Any] = None`, `kaizen_instance: Optional["Kaizen"] = None`.

| Attribute               | Set in `__init__`?             | Source line      |
| ----------------------- | ------------------------------ | ---------------- |
| `agent_id`              | yes                            | agents.py:60     |
| `config`                | yes (`Dict[str, Any]`)         | agents.py:61     |
| `signature`             | yes (`Optional[Any]`)          | agents.py:62     |
| `kaizen`                | yes (`Optional["Kaizen"]`)     | agents.py:63     |
| `_workflow`             | yes (`Optional[Any]`)          | agents.py:66     |
| `_is_compiled`          | yes (`bool`)                   | agents.py:67     |
| `_execution_history`    | yes (`List[Dict[str, Any]]`)   | agents.py:68     |
| `mcp_connections`       | yes (`List[Any]`)              | agents.py:71     |
| `mcp_connection_errors` | yes (`List[Dict[str, Any]]`)   | agents.py:72     |
| `_mcp_server_config`    | yes (`Optional[Any]`)          | agents.py:73     |
| `enterprise_config`     | yes (None or `kaizen._config`) | agents.py:76, 78 |

**`role`, `expertise`, `capabilities`, `behavior_traits`, `authority_level`, `_generate_role_based_prompt` are NOT assigned in `Agent.__init__`.**

Read-property surface (lines 86-103): `name`, `id`, `has_signature`, `can_execute_structured` — all backward-compat aliases over declared attrs.

### Where the "unknown" attrs are dynamically attached

| Attribute                           | Attached at                                                                        | Caller path                                |
| ----------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------ |
| `agent.role`                        | framework.py:493                                                                   | `Kaizen.create_specialized_agent`          |
| `agent.expertise`                   | framework.py:494                                                                   | `Kaizen.create_specialized_agent`          |
| `agent.capabilities`                | framework.py:495                                                                   | `Kaizen.create_specialized_agent`          |
| `agent._generate_role_based_prompt` | framework.py:498-500                                                               | `Kaizen.create_specialized_agent` (lambda) |
| `agent.authority_level`             | framework.py:807                                                                   | `Kaizen.create_agent_team` only            |
| `agent.behavior_traits`             | **NEVER as agent attr**; only `agent.config["behavior_traits"]` (framework.py:485) | n/a                                        |

**Runtime confirmation** (KAIZEN_DEFAULT_MODEL=gpt-4o-mini, fresh `Agent(agent_id, {...})`):

```
role: False  expertise: False  capabilities: False
behavior_traits: False  authority_level: False  _generate_role_based_prompt: False
```

After `Kaizen().create_specialized_agent(name=..., role=..., config={...})`:

```
role: True 'market analyst'  expertise: True 'finance'  capabilities: True ['analyze']
behavior_traits: False        authority_level: False    _generate_role_based_prompt: True
```

---

## 2. Reachability of `_generate_specialized_agent` / `create_specialized_agent` / `create_agent_team`

The brief asked about `_generate_specialized_agent`. **No method by that exact name exists.** What exists:

- `Kaizen.create_specialized_agent` (public) — framework.py:436
- `Kaizen.create_agent_team` (public) — framework.py:751
- `Kaizen._generate_role_based_prompt` (private helper used at framework.py:530-547)
- `Kaizen._generate_role_based_traits` (private helper at framework.py:505-528)

Both `create_specialized_agent` and `create_agent_team` are **public methods reachable from the `Kaizen` instance API**. Caller evidence:

- `kaizen-kaizen/tests/unit/test_kaizen_multi_agent_coordination.py` exercises both methods (≥10 callsites — lines 303, 311, 329, 362, 389, 418, 436, 466, 472, 478, 525-551, 569, 629).
- `kaizen-kaizen/tests/unit/test_kaizen_core_feature_completion.py` invokes `kaizen.create_specialized_agent` ≥10 times (lines 587-741).
- `kaizen-kaizen/tests/unit/test_integration_test_infrastructure.py` lines 475-478.
- `Kaizen.create_agent_team` at framework.py:800 internally calls `self.create_specialized_agent`.

**Reachability conclusion: REACHABLE — production code, NOT orphan.** `create_specialized_agent` and `create_agent_team` form a real public API surface with tested callers. The dynamic-attach pattern is a real design choice, not dead code.

**Caveat — partial dead branch**: framework.py:537-540 reads `agent.behavior_traits` inside a `hasattr(agent, "behavior_traits")` guard. Because the value is stored in `agent.config["behavior_traits"]` (framework.py:485), not as an attribute, that hasattr is always False. The traits-rendering branch is **unreachable in current code**. Either `agent.behavior_traits = specialized_config["behavior_traits"]` is missing at framework.py around line 495, or framework.py:537 should read `agent.config.get("behavior_traits")`. This is a latent bug exposed by the typing audit.

---

## 3. AgentTeam class — declared attributes

`packages/kaizen-agents/src/kaizen_agents/patterns/core/teams.py:22-74` (the `kaizen_agents.coordination.teams` import at framework.py:778 is a re-export shim).

| Attribute                   | Set in `__init__`? | Source line |
| --------------------------- | ------------------ | ----------- |
| `name`                      | yes (`str`)        | teams.py:57 |
| `pattern`                   | yes (`str`)        | teams.py:58 |
| `coordination`              | yes (`str`)        | teams.py:59 |
| `members`                   | yes (`List[Any]`)  | teams.py:60 |
| `kaizen`                    | yes                | teams.py:61 |
| `_state`                    | yes (`dict`)       | teams.py:64 |
| `_state_management_enabled` | yes (`bool`)       | teams.py:70 |

**`conflict_resolution` and `performance_optimization` are NOT declared.** They are dynamically attached at framework.py:824-825 after `AgentTeam.__init__` returns.

Runtime confirmation (`Kaizen().create_agent_team(...)`):

```
team type: kaizen_agents.patterns.core.teams AgentTeam
conflict_resolution: True 'collaborative'
performance_optimization: True True
member.authority_level: True 'leader'
```

Note: `AgentTeam.__init__` raises `DeprecationWarning` recommending `kaizen.orchestration.runtime.OrchestrationRuntime`. The dynamic-attach attributes survive the deprecation banner because the class body is unchanged.

---

## 4. KaizenConfig

`packages/kailash-kaizen/src/kaizen/core/config.py:382-...`

- **Kind**: `@dataclass` (line 382). NOT a dict subclass. NOT Pydantic.
- **`.get()` exists?** No. `hasattr(KaizenConfig(), "get")` → `False`. MRO is `(KaizenConfig, object)`.
- **Where pyright fires**: agents.py:459 — `self.kaizen.config.get("signature_programming_enabled", False)`.

**Why the runtime works anyway**: `Kaizen.config` (framework.py:1283-...) is a property that returns a `ConfigWrapper(dict)` for the default/dict-config path AND returns the raw `KaizenConfig` only when `_config_was_object` is set. The agents.py:455-459 site guards with `hasattr(self.kaizen.config, "get")`, so the call only runs when the runtime form is the dict wrapper.

```
type(k.config): ConfigWrapper   is dict: True   has get: True
```

Pyright sees the property's declared return type `KaizenConfig` (the dataclass), not the `ConfigWrapper(dict)` runtime form, hence the warning.

---

## 5. Per-pyright-warning fix classification

| Pyright warning                                        | File:line                  | Classification               | Fix                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------ | -------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Agent.role`                                           | framework.py:493, 532      | DECLARE                      | Add `role: Optional[str] = None` to `Agent` class body (or to a `RoleSpec` mixin). Type as `Optional[str]` since vanilla `Agent` doesn't have it.                                                                                                                                                                                                                        |
| `Agent.expertise`                                      | framework.py:494, 534, 535 | DECLARE                      | Same — `expertise: Optional[str] = None`.                                                                                                                                                                                                                                                                                                                                |
| `Agent.capabilities`                                   | framework.py:495, 541, 542 | DECLARE                      | `capabilities: List[str] = field(default_factory=list)` (or `Optional[List[str]] = None`).                                                                                                                                                                                                                                                                               |
| `Agent.behavior_traits`                                | framework.py:537, 538      | REFACTOR + DECLARE           | TWO problems: (a) currently stored only in `config["behavior_traits"]`, never as attr — `hasattr(agent, "behavior_traits")` always False, branch is unreachable; (b) declare attr AND assign at framework.py around line 495: `agent.behavior_traits = specialized_config.get("behavior_traits", [])`. Then pyright sees the symbol AND the latent dead branch is fixed. |
| `Agent.authority_level`                                | framework.py:807           | DECLARE                      | `authority_level: Optional[str] = None`. Set only via `create_agent_team` — that's a legitimate optional.                                                                                                                                                                                                                                                                |
| `Agent._generate_role_based_prompt`                    | framework.py:498-500       | REFACTOR                     | Replace dynamic lambda attach with a real method on `Agent` that delegates back to `self.kaizen._generate_role_based_prompt(self, task)` when `self.kaizen` is set. (Or move it to a `SpecializedAgent` subclass — see § 6.)                                                                                                                                             |
| `AgentTeam.conflict_resolution`                        | framework.py:824           | DECLARE                      | Add `conflict_resolution: str = "collaborative"` to `AgentTeam.__init__` parameters in `kaizen-agents/.../teams.py:30-37` (cross-package), threading it through `__init__` body.                                                                                                                                                                                         |
| `AgentTeam.performance_optimization`                   | framework.py:825           | DECLARE                      | Same — `performance_optimization: bool = False` declared in `__init__`.                                                                                                                                                                                                                                                                                                  |
| `KaizenConfig.get` (via `self.kaizen.config.get(...)`) | agents.py:459              | TYPED GUARD / type-narrowing | The hasattr-guard is correct runtime behavior. Fix typing: change `Kaizen.config` property's return annotation to `Union[KaizenConfig, ConfigWrapper]` OR `Mapping[str, Any]` — OR cast inside agents.py:459 with `cast(Mapping[str, Any], self.kaizen.config).get(...)`.                                                                                                |
| `coordination_workflow` reportOptionalCall             | framework.py:882           | TYPED GUARD                  | `pattern_registry.create_coordination_workflow(...)` returns `Optional`; framework.py:886-887 raises if None. Hoist the None-check up so subsequent `workflow.build()` (line 901) sees a narrowed `Workflow`.                                                                                                                                                            |
| `parser` reportOptionalMemberAccess                    | framework.py:1077          | TYPED GUARD (Rule 3a)        | After `_ensure_signatures_loaded()` (line 1074), `self._signature_parser` is `Optional[SignatureParser]` per declaration at line 241 but pyright doesn't track the lazy-load. Add a typed `_require_signature_parser()` per zero-tolerance Rule 3a, OR `assert self._signature_parser is not None` after the ensure call.                                                |
| `validator` reportOptionalMemberAccess                 | framework.py:1097          | TYPED GUARD                  | Same pattern — `assert self._signature_validator is not None` after `_ensure_signatures_loaded()`.                                                                                                                                                                                                                                                                       |
| `coordination_workflow` at 1188, 1258                  | framework.py:1188, 1258    | TYPED GUARD                  | Same hoisted-None-check pattern as 882.                                                                                                                                                                                                                                                                                                                                  |

### Summary by category

- **DECLARE** (8 sites): `Agent.role`, `Agent.expertise`, `Agent.capabilities`, `Agent.authority_level`, `AgentTeam.conflict_resolution`, `AgentTeam.performance_optimization`, plus 2 supporting Optional-type widening for `KaizenConfig.get`.
- **REFACTOR** (2 sites): `Agent.behavior_traits` (latent dead-branch + declaration), `Agent._generate_role_based_prompt` (lambda → method).
- **TYPED GUARD** (5 sites): `coordination_workflow` (3 sites: 882, 1188, 1258), `_signature_parser` (1077), `_signature_validator` (1097).
- **DEAD** (0 sites): nothing is orphan dead code; `create_specialized_agent` and `create_agent_team` are real public API.

---

## 6. Recommended fix scope (single shard)

This is a **DECLARE-dominant cluster**, not a deletion. Edit budget per `autonomous-execution.md` Rule 1:

1. `Agent` class body in `agents.py` — add 5 class-body annotations: `role`, `expertise`, `capabilities`, `behavior_traits`, `authority_level`, plus `_generate_role_based_prompt` as a real method (not lambda). Cross-package: `AgentTeam.__init__` in `kaizen-agents/.../teams.py` — thread two new kwargs through. ~50 LOC across 2 files.
2. `Kaizen.config` property return annotation: widen to `Union[KaizenConfig, ConfigWrapper]` or `Mapping[str, Any]`. ~5 LOC.
3. Typed guards at framework.py:882/886, 1077, 1097, 1188, 1258 — 5 None-narrowings. ~30 LOC.
4. **Latent bug fix**: at framework.py:495 add `agent.behavior_traits = specialized_config.get("behavior_traits", [])` so the rendering branch at line 537-540 actually fires (currently dead). ~1 LOC + 1 Tier-2 regression test that asserts the rendered prompt contains the traits string.

Total: ~85 LOC, 4 invariants (Agent contract, AgentTeam contract, KaizenConfig.get type, lazy-load None-narrowing), 2 call-graph hops. **Single shard, well within budget.**

**Cross-SDK note** (per `cross-sdk-inspection.md`): kailash-rs has no AgentTeam yet (Kaizen is Python-only at present); no parity issue.

---

## Confidence

**HIGH** for class-shape claims (verified by reading both `__init__` bodies AND running `hasattr` against live instances).
**HIGH** for reachability (10+ test callsites of `create_specialized_agent`).
**HIGH** for the latent `behavior_traits` dead-branch finding (runtime hasattr returned False even after `create_specialized_agent`).
**MEDIUM** for the typed-guard fix sketch — pattern is standard but the `Kaizen.config` property's `_config_was_object` branching is fragile and may benefit from a follow-up refactor (out of #822 scope).
