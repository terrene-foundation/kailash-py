import React from "react";
import { NodeDefinition } from "@/store/workflowStore";
import { useWorkflowStore } from "@/store/workflowStore";

interface NodeCardProps {
  node: NodeDefinition;
}

export function NodeCard({ node }: NodeCardProps) {
  const { addNode } = useWorkflowStore();

  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData("application/reactflow", JSON.stringify(node));
    event.dataTransfer.effectAllowed = "move";
  };

  const handleClick = () => {
    // Add node at center of canvas when clicked
    const newNode = {
      id: `${node.id}_${Date.now()}`,
      type: "custom",
      position: { x: 400, y: 300 },
      data: {
        nodeDefinition: node,
        label: node.name,
        config: {},
      },
    };
    addNode(newNode);
  };

  return (
    <div
      className="p-3 bg-background border border-border rounded-md cursor-move hover:border-primary transition-colors"
      draggable
      onDragStart={onDragStart}
      onClick={handleClick}
    >
      <div className="font-medium text-sm mb-1">{node.name}</div>
      <div className="text-xs text-muted-foreground line-clamp-2">
        {node.description}
      </div>
      {node.parameters.length > 0 && (
        <div className="mt-2 text-xs text-muted-foreground">
          {node.parameters.filter((p) => p.required).length} required params
        </div>
      )}
    </div>
  );
}