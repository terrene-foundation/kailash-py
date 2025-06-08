import React, { memo } from "react";
import { Handle, Position, NodeProps } from "reactflow";
import { useWorkflowStore } from "../../store/workflowStore";

interface KailashNodeData {
  nodeType: string;
  label: string;
  config: Record<string, any>;
  inputs: number;
  outputs: Record<string, string>;
  category?: string;
  icon?: string;
  color?: string;
}

const KailashNode = memo(({ id, data, selected }: NodeProps<KailashNodeData>) => {
  const { setSelectedNode, executionResults } = useWorkflowStore();
  const executionResult = executionResults.get(id);

  const handleClick = () => {
    setSelectedNode(id);
  };

  // Get output handles based on node type
  const outputHandles = Object.entries(data.outputs || { output: "Output" });
  const handleSpacing = 100 / (outputHandles.length + 1);

  return (
    <div
      className={`kailash-node ${selected ? "selected" : ""} ${
        executionResult ? "executed" : ""
      }`}
      style={{
        borderColor: data.color || "#ddd",
        minWidth: "180px",
      }}
      onClick={handleClick}
    >
      {/* Input handle(s) - always on the left */}
      {data.inputs > 0 && (
        <>
          {data.inputs === 1 ? (
            <Handle
              type="target"
              position={Position.Left}
              id="input"
              className="kailash-handle"
              style={{
                background: "#555",
                width: 10,
                height: 10,
                border: "2px solid #fff",
              }}
            />
          ) : (
            // Multiple inputs (e.g., MergeNode)
            Array.from({ length: data.inputs }, (_, i) => (
              <Handle
                key={`input-${i}`}
                type="target"
                position={Position.Left}
                id={`input-${i + 1}`}
                className="kailash-handle"
                style={{
                  background: "#555",
                  width: 10,
                  height: 10,
                  border: "2px solid #fff",
                  top: `${(100 / (data.inputs + 1)) * (i + 1)}%`,
                }}
              />
            ))
          )}
        </>
      )}

      {/* Node content */}
      <div className="node-header">
        <span className="node-icon">{data.icon || "📦"}</span>
        <span className="node-label">{data.label}</span>
      </div>

      {/* Execution status indicator */}
      {executionResult && (
        <div className="execution-status">
          {executionResult.error ? (
            <span className="status-error">❌ Error</span>
          ) : (
            <span className="status-success">✅ Complete</span>
          )}
        </div>
      )}

      {/* Node type indicator */}
      <div className="node-type">{data.nodeType}</div>

      {/* Output handle(s) - always on the right */}
      {outputHandles.map(([handleId, label], index) => (
        <Handle
          key={handleId}
          type="source"
          position={Position.Right}
          id={handleId}
          className="kailash-handle"
          style={{
            background: getHandleColor(handleId, data.nodeType),
            width: 10,
            height: 10,
            border: "2px solid #fff",
            top: `${handleSpacing * (index + 1)}%`,
          }}
          title={label}
        />
      ))}
    </div>
  );
});

KailashNode.displayName = "KailashNode";

// Get handle color based on type
function getHandleColor(handleId: string, nodeType: string): string {
  if (nodeType === "SwitchNode") {
    return handleId === "true" ? "#4caf50" : "#f44336";
  }
  if (nodeType === "LoopNode") {
    return handleId === "continue" ? "#9b59b6" : "#3498db";
  }
  return "#555";
}

export default KailashNode;
