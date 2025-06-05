import React from "react";
import { useWorkflowStore } from "@/store/workflowStore";
import { ParameterForm } from "./ParameterForm";
import { X } from "lucide-react";

export function PropertyPanel() {
  const { selectedNodeId, currentWorkflow, selectNode } = useWorkflowStore();

  const selectedNode = currentWorkflow?.nodes.find(
    (node) => node.id === selectedNodeId
  );

  if (!selectedNode) {
    return (
      <div className="w-80 bg-card border-l border-border p-4">
        <div className="text-muted-foreground text-center mt-8">
          Select a node to view its properties
        </div>
      </div>
    );
  }

  const nodeDefinition = selectedNode.data.nodeDefinition;

  return (
    <div className="w-80 bg-card border-l border-border flex flex-col">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{nodeDefinition.name}</h3>
          <p className="text-sm text-muted-foreground capitalize">
            {nodeDefinition.category}
          </p>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="p-1 hover:bg-accent rounded"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-4">
          <h4 className="text-sm font-medium mb-2">Description</h4>
          <p className="text-sm text-muted-foreground">
            {nodeDefinition.description}
          </p>
        </div>

        <div className="mb-4">
          <h4 className="text-sm font-medium mb-2">Node ID</h4>
          <p className="text-sm font-mono bg-muted px-2 py-1 rounded">
            {selectedNode.id}
          </p>
        </div>

        <div>
          <h4 className="text-sm font-medium mb-2">Parameters</h4>
          <ParameterForm
            node={selectedNode}
            nodeDefinition={nodeDefinition}
          />
        </div>
      </div>
    </div>
  );
}