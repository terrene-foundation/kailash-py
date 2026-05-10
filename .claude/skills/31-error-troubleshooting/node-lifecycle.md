# Node Execution Lifecycle

Debugging contract for Kailash SDK nodes. When a node misbehaves (silent skip, wrong output, exception in unexpected phase), the lifecycle ordering tells you which phase to inspect.

## Lifecycle (in order)

| Phase                     | Trigger                                                    | Common failure mode                                        |
| ------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------- |
| 1. Initialization         | `__init__(node_id, parameters)`                            | Static config invalid; node never enters runtime           |
| 2. Validation             | `add_parameter(NodeParameter(...))` registers schema       | Missing `required=True` param → `ValueError` at build      |
| 3. Input Reception        | Connections deliver upstream outputs into `inputs` dict    | Connection key mismatch → input absent; node sees `{}`     |
| 4. Execution              | `execute(inputs)` runs business logic                      | Most user bugs land here; raise to surface, do NOT swallow |
| 5. Output Generation      | Return dict from `execute()`                               | Output keys MUST match downstream connection target keys   |
| 6. Connection Propagation | Runtime forwards return dict to connected downstream nodes | Mismatched output key → downstream sees `None` / KeyError  |

## Reference Implementation

```python
class CustomNode(Node):
    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)        # Phase 1
        self.add_parameter(NodeParameter(            # Phase 2
            name="input",
            param_type="string",
            required=True,
        ))

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        input_value = self.get_parameter("input", inputs)  # Phase 3 (read)
        result = process(input_value)                       # Phase 4
        return {                                            # Phase 5
            "result": result,
            "status": "success",
        }
        # Phase 6 happens automatically; runtime forwards `result` and `status`
        # to whatever downstream node has a connection on these keys.
```

## Debugging Pattern (which phase failed?)

```python
import logging
logger = logging.getLogger(__name__)

class DebugNode(Node):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Node {self.node_id} starting execution")  # Phase 4 entry
        logger.debug(f"Inputs: {inputs}")                       # Phase 3 result

        try:
            result = self.process_data(inputs)
            logger.info(f"Node {self.node_id} completed successfully")  # Phase 5
            return result
        except Exception as e:
            logger.error(f"Node {self.node_id} failed: {e}", exc_info=True)
            raise  # NEVER swallow — masks Phase 4 root causes
```

**Diagnostic mapping:**

- Logs show "starting execution" but no "completed" → exception in Phase 4 logic.
- Logs show empty `inputs` → Phase 3 connection mismatch (check the source node's output key against this node's connection input key).
- `ValueError` at workflow.build() → Phase 2 missing required parameter.
- Downstream node sees `None` for an expected key → Phase 5 output key doesn't match the connection target.

## See Also

- `error-runtime-execution.md` — runtime-level execution failures (this skill)
- `error-parameter-validation.md` — Phase 2 failure modes (this skill)
- `01-core-sdk/custom-node-guide.md` — full custom-node authoring guide
