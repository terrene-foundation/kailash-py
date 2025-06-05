import React, { createContext, useContext, ReactNode } from "react";
import { create } from "zustand";
import { Node, Edge, Connection } from "react-flow-renderer";

export interface NodeDefinition {
  id: string;
  category: string;
  name: string;
  description: string;
  parameters: Array<{
    name: string;
    type: string;
    required: boolean;
    description: string;
    default?: any;
  }>;
  inputs: Array<{ name: string; type: string }>;
  outputs: Array<{ name: string; type: string }>;
}

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  nodes: Node[];
  edges: Edge[];
  created_at?: string;
  updated_at?: string;
}

interface WorkflowState {
  // Current workflow
  currentWorkflow: Workflow | null;
  
  // UI state
  selectedNodeId: string | null;
  showExecutionPanel: boolean;
  isExecuting: boolean;
  
  // Node definitions from backend
  nodeCategories: Record<string, NodeDefinition[]>;
  
  // Actions
  setCurrentWorkflow: (workflow: Workflow) => void;
  updateWorkflow: (updates: Partial<Workflow>) => void;
  selectNode: (nodeId: string | null) => void;
  setShowExecutionPanel: (show: boolean) => void;
  setIsExecuting: (executing: boolean) => void;
  setNodeCategories: (categories: Record<string, NodeDefinition[]>) => void;
  
  // Node operations
  addNode: (node: Node) => void;
  updateNode: (nodeId: string, updates: Partial<Node>) => void;
  deleteNode: (nodeId: string) => void;
  
  // Edge operations
  addEdge: (edge: Edge) => void;
  deleteEdge: (edgeId: string) => void;
  onConnect: (connection: Connection) => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  // Initial state
  currentWorkflow: null,
  selectedNodeId: null,
  showExecutionPanel: false,
  isExecuting: false,
  nodeCategories: {},
  
  // Actions
  setCurrentWorkflow: (workflow) => set({ currentWorkflow: workflow }),
  
  updateWorkflow: (updates) => set((state) => ({
    currentWorkflow: state.currentWorkflow
      ? { ...state.currentWorkflow, ...updates }
      : null
  })),
  
  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),
  
  setShowExecutionPanel: (show) => set({ showExecutionPanel: show }),
  
  setIsExecuting: (executing) => set({ isExecuting: executing }),
  
  setNodeCategories: (categories) => set({ nodeCategories: categories }),
  
  // Node operations
  addNode: (node) => set((state) => {
    if (!state.currentWorkflow) return state;
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        nodes: [...state.currentWorkflow.nodes, node]
      }
    };
  }),
  
  updateNode: (nodeId, updates) => set((state) => {
    if (!state.currentWorkflow) return state;
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        nodes: state.currentWorkflow.nodes.map((node) =>
          node.id === nodeId ? { ...node, ...updates } : node
        )
      }
    };
  }),
  
  deleteNode: (nodeId) => set((state) => {
    if (!state.currentWorkflow) return state;
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        nodes: state.currentWorkflow.nodes.filter((node) => node.id !== nodeId),
        edges: state.currentWorkflow.edges.filter(
          (edge) => edge.source !== nodeId && edge.target !== nodeId
        )
      }
    };
  }),
  
  // Edge operations
  addEdge: (edge) => set((state) => {
    if (!state.currentWorkflow) return state;
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        edges: [...state.currentWorkflow.edges, edge]
      }
    };
  }),
  
  deleteEdge: (edgeId) => set((state) => {
    if (!state.currentWorkflow) return state;
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        edges: state.currentWorkflow.edges.filter((edge) => edge.id !== edgeId)
      }
    };
  }),
  
  onConnect: (connection) => set((state) => {
    if (!state.currentWorkflow || !connection.source || !connection.target) {
      return state;
    }
    
    const newEdge: Edge = {
      id: `${connection.source}-${connection.target}`,
      source: connection.source,
      target: connection.target,
      sourceHandle: connection.sourceHandle || undefined,
      targetHandle: connection.targetHandle || undefined,
    };
    
    return {
      currentWorkflow: {
        ...state.currentWorkflow,
        edges: [...state.currentWorkflow.edges, newEdge]
      }
    };
  }),
}));

// Context provider for convenience
const WorkflowContext = createContext<ReturnType<typeof useWorkflowStore> | null>(null);

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const store = useWorkflowStore();
  
  return (
    <WorkflowContext.Provider value={store}>
      {children}
    </WorkflowContext.Provider>
  );
}