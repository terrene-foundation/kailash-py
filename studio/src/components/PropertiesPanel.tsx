import React, { useState, useEffect } from "react";
import { useWorkflowStore } from "../store/workflowStore";

export function PropertiesPanel() {
  const { nodes, selectedNodeId, updateNode } = useWorkflowStore();
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const [nodeLabel, setNodeLabel] = useState("");
  const [nodeConfig, setNodeConfig] = useState<Record<string, any>>({});

  useEffect(() => {
    if (selectedNode) {
      setNodeLabel(selectedNode.data.label);
      setNodeConfig(selectedNode.data.config || {});
    } else {
      setNodeLabel("");
      setNodeConfig({});
    }
  }, [selectedNode]);

  const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNodeLabel(e.target.value);
  };

  const handleLabelBlur = () => {
    if (selectedNode && nodeLabel.trim()) {
      updateNode(selectedNode.id, {
        data: { ...selectedNode.data, label: nodeLabel.trim() },
      });
    }
  };

  const handleConfigChange = (key: string, value: any) => {
    const newConfig = { ...nodeConfig, [key]: value };
    setNodeConfig(newConfig);

    if (selectedNode) {
      updateNode(selectedNode.id, {
        data: { ...selectedNode.data, config: newConfig },
      });
    }
  };

  const renderConfigField = (key: string, value: any) => {
    if (typeof value === "boolean") {
      return (
        <div className="property-group" key={key}>
          <label className="property-label">
            <input
              type="checkbox"
              checked={value}
              onChange={(e) => handleConfigChange(key, e.target.checked)}
            />
            {key}
          </label>
        </div>
      );
    }

    if (typeof value === "number") {
      return (
        <div className="property-group" key={key}>
          <div className="property-label">{key}</div>
          <input
            type="number"
            className="property-input"
            value={value}
            onChange={(e) => handleConfigChange(key, Number(e.target.value))}
          />
        </div>
      );
    }

    return (
      <div className="property-group" key={key}>
        <div className="property-label">{key}</div>
        <input
          type="text"
          className="property-input"
          value={value || ""}
          onChange={(e) => handleConfigChange(key, e.target.value)}
        />
      </div>
    );
  };

  return (
    <section className="properties-panel">
      <div className="panel-header">
        <h3>Node Properties</h3>
      </div>

      {selectedNode ? (
        <div className="properties-content">
          <div className="property-section">
            <h4>General</h4>

            <div className="property-group">
              <div className="property-label">Label</div>
              <input
                type="text"
                className="property-input"
                value={nodeLabel}
                onChange={handleLabelChange}
                onBlur={handleLabelBlur}
                placeholder="Node label"
              />
            </div>

            <div className="property-group">
              <div className="property-label">Type</div>
              <input
                type="text"
                className="property-input"
                value={selectedNode.data.nodeType}
                readOnly
                style={{ background: "#f5f5f5", cursor: "not-allowed" }}
              />
            </div>

            <div className="property-group">
              <div className="property-label">Category</div>
              <div className="property-value">
                <span style={{ marginRight: 8 }}>{selectedNode.data.icon}</span>
                {selectedNode.data.category}
              </div>
            </div>
          </div>

          <div className="property-section">
            <h4>Configuration</h4>
            {renderNodeSpecificConfig(selectedNode.data.nodeType, nodeConfig, handleConfigChange)}
          </div>

          <div className="property-section">
            <h4>Debug Info</h4>
            <div className="property-group">
              <div className="property-label">Node ID</div>
              <div className="property-value" style={{ fontSize: "11px", color: "#666" }}>
                {selectedNode.id}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <p>Select a node to view its properties</p>
        </div>
      )}
    </section>
  );
}

// Render node-specific configuration based on node type
function renderNodeSpecificConfig(
  nodeType: string,
  config: Record<string, any>,
  onChange: (key: string, value: any) => void
) {
  switch (nodeType) {
    case "SwitchNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">Condition</div>
            <input
              type="text"
              className="property-input"
              value={config.condition || ""}
              onChange={(e) => onChange("condition", e.target.value)}
              placeholder="e.g., data.value > 10"
            />
          </div>
        </>
      );

    case "LoopNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">Condition Type</div>
            <select
              className="property-input"
              value={config.conditionType || "counter"}
              onChange={(e) => onChange("conditionType", e.target.value)}
            >
              <option value="counter">Counter</option>
              <option value="expression">Expression</option>
              <option value="callback">Callback</option>
            </select>
          </div>
          {config.conditionType === "counter" && (
            <div className="property-group">
              <div className="property-label">Max Iterations</div>
              <input
                type="number"
                className="property-input"
                value={config.maxIterations || 100}
                onChange={(e) => onChange("maxIterations", Number(e.target.value))}
              />
            </div>
          )}
          {config.conditionType === "expression" && (
            <div className="property-group">
              <div className="property-label">Expression</div>
              <input
                type="text"
                className="property-input"
                value={config.expression || ""}
                onChange={(e) => onChange("expression", e.target.value)}
                placeholder="e.g., iteration < 10"
              />
            </div>
          )}
        </>
      );

    case "PythonCodeNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">Code</div>
            <textarea
              className="property-input"
              rows={10}
              value={config.code || ""}
              onChange={(e) => onChange("code", e.target.value)}
              placeholder="# Python code here"
              style={{ fontFamily: "monospace", fontSize: "12px" }}
            />
          </div>
        </>
      );

    case "HTTPRequestNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">URL</div>
            <input
              type="text"
              className="property-input"
              value={config.url || ""}
              onChange={(e) => onChange("url", e.target.value)}
              placeholder="https://api.example.com/data"
            />
          </div>
          <div className="property-group">
            <div className="property-label">Method</div>
            <select
              className="property-input"
              value={config.method || "GET"}
              onChange={(e) => onChange("method", e.target.value)}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
            </select>
          </div>
        </>
      );

    case "CSVReaderNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">File Path</div>
            <input
              type="text"
              className="property-input"
              value={config.filePath || ""}
              onChange={(e) => onChange("filePath", e.target.value)}
              placeholder="/path/to/file.csv"
            />
          </div>
          <div className="property-group">
            <label className="property-label">
              <input
                type="checkbox"
                checked={config.hasHeader !== false}
                onChange={(e) => onChange("hasHeader", e.target.checked)}
              />
              Has Header Row
            </label>
          </div>
        </>
      );

    case "LLMAgentNode":
      return (
        <>
          <div className="property-group">
            <div className="property-label">Provider</div>
            <select
              className="property-input"
              value={config.provider || "openai"}
              onChange={(e) => onChange("provider", e.target.value)}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="ollama">Ollama</option>
              <option value="mock">Mock (Testing)</option>
            </select>
          </div>
          <div className="property-group">
            <div className="property-label">Model</div>
            <input
              type="text"
              className="property-input"
              value={config.model || ""}
              onChange={(e) => onChange("model", e.target.value)}
              placeholder="e.g., gpt-4, claude-3"
            />
          </div>
          <div className="property-group">
            <div className="property-label">Temperature</div>
            <input
              type="number"
              className="property-input"
              value={config.temperature || 0.7}
              min="0"
              max="2"
              step="0.1"
              onChange={(e) => onChange("temperature", Number(e.target.value))}
            />
          </div>
          <div className="property-group">
            <div className="property-label">System Prompt</div>
            <textarea
              className="property-input"
              rows={4}
              value={config.systemPrompt || ""}
              onChange={(e) => onChange("systemPrompt", e.target.value)}
              placeholder="You are a helpful assistant..."
            />
          </div>
        </>
      );

    default:
      return (
        <div className="property-group">
          <p style={{ color: "#666", fontSize: "13px" }}>
            No specific configuration for this node type.
          </p>
        </div>
      );
  }
}
