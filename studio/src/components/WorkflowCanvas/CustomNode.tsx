import React, { memo } from "react";
import { Handle, Position, NodeProps } from "reactflow";
import { NodeDefinition } from "@/store/workflowStore";
import { clsx } from "clsx";

interface CustomNodeData {
  nodeDefinition: NodeDefinition;
  label: string;
  config: Record<string, any>;
}

export const CustomNode = memo(({ data, selected }: NodeProps<CustomNodeData>) => {
  const { nodeDefinition, label, config } = data;

  // Get category color
  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      ai: "border-purple-500 bg-purple-50 dark:bg-purple-950",
      data: "border-blue-500 bg-blue-50 dark:bg-blue-950",
      logic: "border-green-500 bg-green-50 dark:bg-green-950",
      transform: "border-orange-500 bg-orange-50 dark:bg-orange-950",
      api: "border-red-500 bg-red-50 dark:bg-red-950",
      code: "border-yellow-500 bg-yellow-50 dark:bg-yellow-950",
      mcp: "border-pink-500 bg-pink-50 dark:bg-pink-950",
    };
    return colors[nodeDefinition.category] || "border-gray-500 bg-gray-50 dark:bg-gray-950";
  };

  return (
    <div
      className={clsx(
        "px-4 py-3 rounded-md border-2 min-w-[200px] transition-all",
        getCategoryColor(nodeDefinition.category),
        selected && "ring-2 ring-primary ring-offset-2"
      )}
    >
      {/* Input handles */}
      {nodeDefinition.inputs?.map((input, index) => (
        <Handle
          key={`input-${index}`}
          type="target"
          position={Position.Left}
          id={input.name}
          style={{ top: `${(index + 1) * 20}px` }}
          className="w-3 h-3 !bg-primary"
        />
      ))}

      {/* Node content */}
      <div>
        <div className="font-semibold text-sm">{label}</div>
        <div className="text-xs text-muted-foreground mt-1 capitalize">
          {nodeDefinition.category}
        </div>

        {/* Show configured parameters */}
        {Object.keys(config).length > 0 && (
          <div className="mt-2 pt-2 border-t border-border text-xs">
            {Object.entries(config).slice(0, 3).map(([key, value]) => (
              <div key={key} className="truncate">
                <span className="font-medium">{key}:</span> {String(value)}
              </div>
            ))}
            {Object.keys(config).length > 3 && (
              <div className="text-muted-foreground">
                +{Object.keys(config).length - 3} more
              </div>
            )}
          </div>
        )}
      </div>

      {/* Output handles */}
      {nodeDefinition.outputs?.map((output, index) => (
        <Handle
          key={`output-${index}`}
          type="source"
          position={Position.Right}
          id={output.name}
          style={{ top: `${(index + 1) * 20}px` }}
          className="w-3 h-3 !bg-primary"
        />
      ))}
    </div>
  );
});
