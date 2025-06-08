import { DragEvent } from "react";

const nodeCategories = [
  {
    name: "Core Primitives",
    nodes: [
      { type: "input-node", label: "Input Node", description: "Data entry point", icon: "📥", style: "data-io" },
      { type: "output-node", label: "Output Node", description: "Result endpoint", icon: "📤", style: "data-io" },
      { type: "llm-node", label: "LLM Node", description: "AI decision maker", icon: "🤖", style: "ai-ml" },
      { type: "tool-node", label: "Tool Node", description: "Action executor", icon: "🔧", style: "api" },
      { type: "agent-node", label: "Agent Node", description: "LLM + Tools combo", icon: "🧠", style: "ai-ml" },
    ],
  },
  {
    name: "Agent Patterns",
    nodes: [
      { type: "prompt-chain", label: "Prompt Chain", description: "Sequential processing", icon: "🔗", style: "logic" },
      { type: "parallel-agents", label: "Parallel Agents", description: "Concurrent execution", icon: "⚡", style: "logic" },
      { type: "router-agent", label: "Router Agent", description: "Dynamic branching", icon: "🚦", style: "logic" },
      { type: "evaluator-loop", label: "Evaluator Loop", description: "Generate-evaluate cycle", icon: "🔄", style: "logic" },
    ],
  },
  {
    name: "Data Sources",
    nodes: [
      { type: "csv-reader", label: "CSV Reader", description: "Read CSV files", icon: "📄", style: "data-io" },
      { type: "api-connector", label: "API Connector", description: "External API calls", icon: "🌐", style: "api" },
      { type: "database-query", label: "Database Query", description: "SQL operations", icon: "🗃️", style: "data-io" },
    ],
  },
  {
    name: "Tool Integrations",
    nodes: [
      { type: "composio-tool", label: "Composio Tools", description: "100+ pre-built tools", icon: "🔌", style: "api" },
      { type: "custom-function", label: "Custom Function", description: "Python code execution", icon: "🐍", style: "code" },
    ],
  },
];

export function NodePalette() {
  const onDragStart = (event: DragEvent, nodeType: string) => {
    event.dataTransfer.setData("application/reactflow", nodeType);
    event.dataTransfer.effectAllowed = "move";
  };

  return (
    <aside className="sidebar">
      {nodeCategories.map((category) => (
        <div key={category.name} className="node-category">
          <div className="category-header">{category.name}</div>
          {category.nodes.map((node) => (
            <div
              key={node.type}
              className="node-item"
              draggable
              onDragStart={(e) => onDragStart(e, node.type)}
            >
              <div className={`node-icon ${node.style}`}>{node.icon}</div>
              <div>
                <div style={{ fontSize: "12px", fontWeight: 500 }}>{node.label}</div>
                <div style={{ fontSize: "10px", color: "#888" }}>{node.description}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </aside>
  );
}
