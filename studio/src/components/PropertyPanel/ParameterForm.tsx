import React, { useState, useEffect } from "react";
import { Node } from "reactflow";
import { NodeDefinition } from "@/store/workflowStore";
import { useWorkflowStore } from "@/store/workflowStore";

interface ParameterFormProps {
  node: Node;
  nodeDefinition: NodeDefinition;
}

export function ParameterForm({ node, nodeDefinition }: ParameterFormProps) {
  const { updateNode } = useWorkflowStore();
  const [config, setConfig] = useState(node.data.config || {});

  useEffect(() => {
    setConfig(node.data.config || {});
  }, [node]);

  const handleChange = (paramName: string, value: any) => {
    const newConfig = { ...config, [paramName]: value };
    setConfig(newConfig);

    // Update node in store
    updateNode(node.id, {
      data: {
        ...node.data,
        config: newConfig,
      },
    });
  };

  const renderInput = (param: any) => {
    const value = config[param.name] ?? param.default ?? "";

    switch (param.type) {
      case "bool":
      case "boolean":
        return (
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => handleChange(param.name, e.target.checked)}
            className="h-4 w-4 rounded border-input"
          />
        );

      case "int":
      case "float":
      case "number":
        return (
          <input
            type="number"
            value={value}
            onChange={(e) => handleChange(param.name, e.target.value)}
            className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={String(param.default || "")}
          />
        );

      case "list":
      case "array":
        return (
          <textarea
            value={Array.isArray(value) ? value.join("\n") : value}
            onChange={(e) =>
              handleChange(param.name, e.target.value.split("\n").filter(Boolean))
            }
            className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="One item per line"
            rows={3}
          />
        );

      case "dict":
      case "object":
        return (
          <textarea
            value={
              typeof value === "object" ? JSON.stringify(value, null, 2) : value
            }
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                handleChange(param.name, parsed);
              } catch {
                // Invalid JSON, just store as string for now
                handleChange(param.name, e.target.value);
              }
            }}
            className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring font-mono"
            placeholder='{"key": "value"}'
            rows={4}
          />
        );

      default:
        return (
          <input
            type="text"
            value={value}
            onChange={(e) => handleChange(param.name, e.target.value)}
            className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={String(param.default || "")}
          />
        );
    }
  };

  if (!nodeDefinition.parameters || nodeDefinition.parameters.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No parameters to configure
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {nodeDefinition.parameters.map((param) => (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1">
            {param.name}
            {param.required && <span className="text-destructive ml-1">*</span>}
          </label>
          {param.description && (
            <p className="text-xs text-muted-foreground mb-2">
              {param.description}
            </p>
          )}
          {renderInput(param)}
          {param.type && (
            <p className="text-xs text-muted-foreground mt-1">
              Type: {param.type}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
