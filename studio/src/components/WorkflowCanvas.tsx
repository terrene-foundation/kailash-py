import React, { useCallback, DragEvent } from "react";
import ReactFlow, {
  Controls,
  Background,
  MiniMap,
  useReactFlow,
  ReactFlowProvider,
  ConnectionMode,
  Node,
  Connection,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";

import { useWorkflowStore } from "../store/workflowStore";
import KailashNode from "./nodes/KailashNode";
import CustomEdge from "./edges/CustomEdge";

const nodeTypes = {
  kailashNode: KailashNode,
};

const edgeTypes = {
  custom: CustomEdge,
};

function Flow() {
  const { screenToFlowPosition } = useReactFlow();
  const {
    nodes,
    edges,
    addNode,
    onNodesChange,
    onEdgesChange,
    onConnect,
    setSelectedNode,
  } = useWorkflowStore();

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const nodeType = event.dataTransfer.getData("application/reactflow");
      if (!nodeType) return;

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      addNode(nodeType, position);
    },
    [screenToFlowPosition, addNode]
  );

  const onNodeClick = useCallback(
    (_: any, node: Node) => {
      setSelectedNode(node.id);
    },
    [setSelectedNode]
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, [setSelectedNode]);

  // Custom connection validation
  const isValidConnection = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return false;

      // Prevent self-connections
      if (connection.source === connection.target) return false;

      // Allow connections - validation happens in the store
      return true;
    },
    []
  );

  return (
    <main className="workflow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        connectionMode={ConnectionMode.Loose}
        isValidConnection={isValidConnection}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        fitView={false}
        deleteKeyCode={["Delete", "Backspace"]}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#e0e0e0"
        />
        <Controls
          showZoom={true}
          showFitView={true}
          showInteractive={false}
        />
        <MiniMap
          nodeStrokeColor={(n) => {
            if (n.selected) return "#0084ff";
            return n.data?.color || "#999";
          }}
          nodeColor={(n) => n.data?.color || "#fff"}
          nodeBorderRadius={8}
          maskColor="rgba(50, 50, 50, 0.8)"
          style={{
            background: "#f8f8f8",
            border: "1px solid #ddd",
          }}
        />
      </ReactFlow>
    </main>
  );
}

export function WorkflowCanvas() {
  return (
    <ReactFlowProvider>
      <Flow />
    </ReactFlowProvider>
  );
}
