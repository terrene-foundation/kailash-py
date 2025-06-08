import { create } from "zustand";
import { Node, Edge, Connection, XYPosition, MarkerType } from "reactflow";

// Node category definitions synced with backend
export const NODE_CATEGORIES = {
  AI: {
    icon: "🤖",
    color: "#9b59b6",
    nodes: ["LLMAgentNode", "EmbeddingGeneratorNode", "IntelligentAgentOrchestratorNode"],
  },
  Data: {
    icon: "📊",
    color: "#3498db",
    nodes: ["CSVReaderNode", "CSVWriterNode", "JSONReaderNode", "SQLQueryNode", "VectorDBNode"],
  },
  Logic: {
    icon: "🔀",
    color: "#e74c3c",
    nodes: ["SwitchNode", "MergeNode", "LoopNode", "WorkflowNode"],
  },
  API: {
    icon: "🌐",
    color: "#f39c12",
    nodes: ["HTTPRequestNode", "RESTClientNode", "GraphQLNode"],
  },
  Code: {
    icon: "💻",
    color: "#27ae60",
    nodes: ["PythonCodeNode"],
  },
  Transform: {
    icon: "🔄",
    color: "#16a085",
    nodes: ["DataProcessorNode", "ChunkerNode", "JSONFormatterNode"],
  },
  MCP: {
    icon: "🔌",
    color: "#34495e",
    nodes: ["MCPClientNode", "MCPServerNode", "MCPResourceNode"],
  },
};

// Get category for a node type
export const getNodeCategory = (nodeType: string) => {
  for (const [category, data] of Object.entries(NODE_CATEGORIES)) {
    if (data.nodes.includes(nodeType)) {
      return { name: category, ...data };
    }
  }
  return { name: "Unknown", icon: "❓", color: "#95a5a6", nodes: [] };
};

// Node configuration metadata
export const NODE_CONFIGS = {
  SwitchNode: {
    outputs: { true: "True", false: "False" },
    inputs: 1,
  },
  MergeNode: {
    outputs: { output: "Output" },
    inputs: 2, // Can have multiple inputs
  },
  LoopNode: {
    outputs: { output: "Output" },  // LoopNode has a single output with control data
    inputs: 1,
  },
  default: {
    outputs: { output: "Output" },
    inputs: 1,
  },
};

interface NodeData {
  nodeType: string;
  label: string;
  config: Record<string, any>;
  inputs: number;
  outputs: Record<string, string>;
  category?: string;
  icon?: string;
  color?: string;
}

interface BackendNode {
  type: string;
  config: Record<string, any>;
  position?: { x: number; y: number };
}

interface BackendConnection {
  source_node: string;
  source_output: string;
  target_node: string;
  target_input: string;
}

interface BackendWorkflow {
  nodes: Record<string, BackendNode>;
  connections: BackendConnection[];
}

interface WorkflowState {
  // Canvas state
  nodes: Node<NodeData>[];
  edges: Edge[];
  selectedNodeId: string | null;

  // Workflow metadata
  workflowId: string;
  workflowName: string;
  isDirty: boolean;

  // Execution state
  isExecuting: boolean;
  executionResults: Map<string, any>;

  // Actions - Canvas
  addNode: (nodeType: string, position: XYPosition) => void;
  updateNode: (nodeId: string, updates: Partial<Node<NodeData>>) => void;
  deleteNode: (nodeId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;

  onNodesChange: (changes: any) => void;
  onEdgesChange: (changes: any) => void;
  onConnect: (connection: Connection) => void;

  // Actions - Edges
  deleteEdge: (edgeId: string) => void;

  // Conversion methods
  toBackendFormat: () => BackendWorkflow;
  fromBackendFormat: (workflow: BackendWorkflow) => void;

  // Execution
  executeWorkflow: () => Promise<void>;
  clearExecution: () => void;

  // Utility
  resetCanvas: () => void;
  setDirty: (dirty: boolean) => void;
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  // Initial state
  nodes: [],
  edges: [],
  selectedNodeId: null,
  workflowId: "",
  workflowName: "Untitled Workflow",
  isDirty: false,
  isExecuting: false,
  executionResults: new Map(),

  // Canvas actions
  addNode: (nodeType: string, position: XYPosition) => {
    const nodeId = `${nodeType.toLowerCase()}_${Date.now()}`;
    const category = getNodeCategory(nodeType);
    const nodeConfig = NODE_CONFIGS[nodeType] || NODE_CONFIGS.default;

    const newNode: Node<NodeData> = {
      id: nodeId,
      type: "kailashNode",
      position,
      data: {
        nodeType,
        label: nodeType.replace("Node", ""),
        config: {},
        inputs: nodeConfig.inputs,
        outputs: nodeConfig.outputs,
        category: category.name,
        icon: category.icon,
        color: category.color,
      },
    };

    set((state) => ({
      nodes: [...state.nodes, newNode],
      isDirty: true,
    }));
  },

  updateNode: (nodeId: string, updates: Partial<Node<NodeData>>) => {
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === nodeId ? { ...node, ...updates } : node
      ),
      isDirty: true,
    }));
  },

  deleteNode: (nodeId: string) => {
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== nodeId),
      edges: state.edges.filter(
        (edge) => edge.source !== nodeId && edge.target !== nodeId
      ),
      selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
      isDirty: true,
    }));
  },

  setSelectedNode: (nodeId: string | null) => {
    set({ selectedNodeId: nodeId });
  },

  onNodesChange: (changes: any) => {
    // Handle node changes from ReactFlow
    set((state) => {
      // Apply changes to nodes
      let updatedNodes = [...state.nodes];

      changes.forEach((change: any) => {
        if (change.type === "position" && change.dragging === false) {
          updatedNodes = updatedNodes.map((node) =>
            node.id === change.id
              ? { ...node, position: change.position }
              : node
          );
        }
      });

      return { nodes: updatedNodes, isDirty: true };
    });
  },

  onEdgesChange: (changes: any) => {
    // Handle edge changes from ReactFlow
    set((state) => ({
      edges: state.edges,
      isDirty: true,
    }));
  },

  onConnect: (connection: Connection) => {
    if (!connection.source || !connection.target) return;

    const { nodes, edges } = get();

    // Prevent self-connections
    if (connection.source === connection.target) return;

    // Check if connection already exists
    const exists = edges.some(
      (edge) =>
        edge.source === connection.source &&
        edge.target === connection.target &&
        edge.sourceHandle === connection.sourceHandle &&
        edge.targetHandle === connection.targetHandle
    );

    if (exists) return;

    // Check if this is a loop connection
    const sourceNode = nodes.find((n) => n.id === connection.source);
    const isLoopConnection = sourceNode?.data.nodeType === "LoopNode" &&
                           connection.sourceHandle === "continue";

    const newEdge: Edge = {
      id: `${connection.source}-${connection.target}-${Date.now()}`,
      source: connection.source!,
      target: connection.target!,
      sourceHandle: connection.sourceHandle || "output",
      targetHandle: connection.targetHandle || "input",
      type: "smoothstep",
      animated: true,
      style: isLoopConnection ? {
        stroke: "#9b59b6",
        strokeDasharray: 5,
      } : {
        stroke: "#b1b1b7",
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 15,
        height: 15,
        color: isLoopConnection ? "#9b59b6" : "#b1b1b7",
      },
    };

    set((state) => ({
      edges: [...state.edges, newEdge],
      isDirty: true,
    }));
  },

  deleteEdge: (edgeId: string) => {
    set((state) => ({
      edges: state.edges.filter((edge) => edge.id !== edgeId),
      isDirty: true,
    }));
  },

  // Conversion methods
  toBackendFormat: () => {
    const { nodes, edges } = get();
    const backendNodes: Record<string, BackendNode> = {};
    const backendConnections: BackendConnection[] = [];

    // Convert nodes
    nodes.forEach((node) => {
      backendNodes[node.id] = {
        type: node.data.nodeType,
        config: node.data.config,
        position: node.position,
      };
    });

    // Convert edges
    edges.forEach((edge) => {
      backendConnections.push({
        source_node: edge.source,
        source_output: edge.sourceHandle || "output",
        target_node: edge.target,
        target_input: edge.targetHandle || "input",
      });
    });

    return {
      nodes: backendNodes,
      connections: backendConnections,
    };
  },

  fromBackendFormat: (workflow: BackendWorkflow) => {
    const nodes: Node<NodeData>[] = [];
    const edges: Edge[] = [];

    // Convert nodes
    Object.entries(workflow.nodes).forEach(([nodeId, nodeData]) => {
      const category = getNodeCategory(nodeData.type);
      const nodeConfig = NODE_CONFIGS[nodeData.type] || NODE_CONFIGS.default;

      nodes.push({
        id: nodeId,
        type: "kailashNode",
        position: nodeData.position || { x: 100, y: 100 },
        data: {
          nodeType: nodeData.type,
          label: nodeData.type.replace("Node", ""),
          config: nodeData.config,
          inputs: nodeConfig.inputs,
          outputs: nodeConfig.outputs,
          category: category.name,
          icon: category.icon,
          color: category.color,
        },
      });
    });

    // Convert connections
    workflow.connections.forEach((conn, index) => {
      const sourceNode = nodes.find((n) => n.id === conn.source_node);
      const isLoopConnection = sourceNode?.data.nodeType === "LoopNode" &&
                             conn.source_output === "continue";

      edges.push({
        id: `edge-${index}`,
        source: conn.source_node,
        target: conn.target_node,
        sourceHandle: conn.source_output,
        targetHandle: conn.target_input,
        type: "smoothstep",
        animated: true,
        style: isLoopConnection ? {
          stroke: "#9b59b6",
          strokeDasharray: 5,
        } : {
          stroke: "#b1b1b7",
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 15,
          height: 15,
          color: isLoopConnection ? "#9b59b6" : "#b1b1b7",
        },
      });
    });

    set({
      nodes,
      edges,
      isDirty: false,
    });
  },

  // Execution
  executeWorkflow: async () => {
    set({ isExecuting: true, executionResults: new Map() });

    try {
      const workflow = get().toBackendFormat();

      // TODO: Call backend API to execute workflow
      const response = await fetch("/api/workflow/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(workflow),
      });

      if (!response.ok) {
        throw new Error("Workflow execution failed");
      }

      const results = await response.json();

      // Store results by node ID
      const resultsMap = new Map(Object.entries(results));
      set({ executionResults: resultsMap });
    } catch (error) {
      console.error("Workflow execution error:", error);
      // TODO: Show error notification
    } finally {
      set({ isExecuting: false });
    }
  },

  clearExecution: () => {
    set({ executionResults: new Map() });
  },

  // Utility
  resetCanvas: () => {
    set({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      isDirty: false,
      executionResults: new Map(),
    });
  },

  setDirty: (dirty: boolean) => {
    set({ isDirty: dirty });
  },
}));
