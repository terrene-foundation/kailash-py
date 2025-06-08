# Kailash Frontend Canvas Redesign - n8n Pattern Implementation

## Overview
Redesign the Kailash workflow canvas following n8n's proven patterns while maintaining compatibility with the Kailash Python SDK backend.

## Architecture Decisions

### 1. State Management
**Recommendation: Zustand**
- Lighter weight than Redux (3KB vs 10KB)
- Less boilerplate code
- Perfect for our workflow state complexity
- Better TypeScript support out of the box
- Easier integration with ReactFlow

### 2. Canvas Implementation Patterns

#### Node Categories (Synced with Backend)
Based on the Kailash node registry, organize nodes into these categories:

```typescript
const NODE_CATEGORIES = {
  'AI': {
    icon: '🤖',
    color: '#9b59b6',
    nodes: ['LLMAgentNode', 'EmbeddingGeneratorNode', 'IntelligentAgentOrchestratorNode']
  },
  'Data': {
    icon: '📊',
    color: '#3498db',
    nodes: ['CSVReaderNode', 'CSVWriterNode', 'JSONReaderNode', 'SQLQueryNode']
  },
  'Logic': {
    icon: '🔀',
    color: '#e74c3c',
    nodes: ['SwitchNode', 'MergeNode', 'LoopNode', 'WorkflowNode']
  },
  'API': {
    icon: '🌐',
    color: '#f39c12',
    nodes: ['HTTPRequestNode', 'RESTClientNode', 'GraphQLNode']
  },
  'Code': {
    icon: '💻',
    color: '#27ae60',
    nodes: ['PythonCodeNode']
  },
  'Transform': {
    icon: '🔄',
    color: '#16a085',
    nodes: ['DataProcessorNode', 'ChunkerNode', 'JSONFormatterNode']
  },
  'MCP': {
    icon: '🔌',
    color: '#34495e',
    nodes: ['MCPClientNode', 'MCPServerNode', 'MCPResourceNode']
  }
};
```

#### Connection Rules (n8n-style)
1. **Fixed Handle Positions**:
   - Input handles: Left side only
   - Output handles: Right side only
   - Multiple outputs allowed per node
   - Generally one input per node (with exceptions like MergeNode)

2. **Loop Implementation**:
   - Use the existing `LoopNode` from logic category
   - Visual indicator for loop connections (dashed line, different color)
   - Loop connections must go from a downstream node back to an upstream node

### 3. Frontend-Backend Workflow Mapping

#### Backend Workflow Structure
```python
{
  "nodes": {
    "node_id": {
      "type": "NodeClassName",
      "config": {...},
      "position": {"x": 100, "y": 200}  # Added for UI
    }
  },
  "connections": [
    {
      "source_node": "node_id_1",
      "source_output": "output",
      "target_node": "node_id_2",
      "target_input": "input"
    }
  ]
}
```

#### Frontend ReactFlow Structure
```typescript
{
  nodes: [
    {
      id: 'node_id',
      type: 'customNode',
      position: { x: 100, y: 200 },
      data: {
        nodeType: 'NodeClassName',
        label: 'Node Name',
        config: {...},
        inputs: 1,
        outputs: 1
      }
    }
  ],
  edges: [
    {
      id: 'e1-2',
      source: 'node_id_1',
      target: 'node_id_2',
      sourceHandle: 'output',
      targetHandle: 'input',
      type: 'smoothstep',
      animated: true
    }
  ]
}
```

### 4. Zustand Store Structure

```typescript
interface WorkflowState {
  // Canvas state
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;

  // Workflow metadata
  workflowId: string;
  workflowName: string;
  isDirty: boolean;

  // Execution state
  isExecuting: boolean;
  executionResults: Map<string, any>;

  // Actions
  addNode: (nodeType: string, position: XYPosition) => void;
  updateNode: (nodeId: string, data: Partial<NodeData>) => void;
  deleteNode: (nodeId: string) => void;

  addEdge: (connection: Connection) => void;
  deleteEdge: (edgeId: string) => void;

  // Conversion methods
  toBackendFormat: () => BackendWorkflow;
  fromBackendFormat: (workflow: BackendWorkflow) => void;

  // Execution
  executeWorkflow: () => Promise<void>;
  clearExecution: () => void;
}
```

### 5. Key Implementation Components

#### Custom Node Component
```tsx
const KailashNode = ({ id, data, selected }) => {
  const { updateNode } = useWorkflowStore();
  const nodeCategory = getNodeCategory(data.nodeType);

  return (
    <div className={`kailash-node ${selected ? 'selected' : ''}`}
         style={{ borderColor: nodeCategory.color }}>
      {/* Fixed input handle on left */}
      {data.inputs > 0 && (
        <Handle
          type="target"
          position={Position.Left}
          id="input"
          style={{ background: '#555' }}
        />
      )}

      <div className="node-header">
        <span className="node-icon">{nodeCategory.icon}</span>
        <span className="node-type">{data.label}</span>
      </div>

      <div className="node-content">
        {/* Node-specific content */}
      </div>

      {/* Fixed output handle(s) on right */}
      {data.outputs > 0 && (
        <Handle
          type="source"
          position={Position.Right}
          id="output"
          style={{ background: '#555' }}
        />
      )}

      {/* Multiple outputs for specific nodes */}
      {data.nodeType === 'SwitchNode' && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ top: '30%', background: '#0f0' }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id="false"
            style={{ top: '70%', background: '#f00' }}
          />
        </>
      )}
    </div>
  );
};
```

#### Loop Connection Validation
```typescript
const isValidConnection = (connection: Connection): boolean => {
  const { nodes, edges } = get();

  // Prevent self-connections
  if (connection.source === connection.target) return false;

  // Check if this creates a valid loop
  if (isLoopConnection(connection)) {
    // Must connect through a LoopNode
    const sourceNode = nodes.find(n => n.id === connection.source);
    const targetNode = nodes.find(n => n.id === connection.target);

    if (sourceNode?.data.nodeType !== 'LoopNode') {
      showError('Loop connections must go through a LoopNode');
      return false;
    }
  }

  // Check for duplicate connections
  const exists = edges.some(
    e => e.source === connection.source &&
         e.target === connection.target &&
         e.sourceHandle === connection.sourceHandle &&
         e.targetHandle === connection.targetHandle
  );

  return !exists;
};
```

### 6. Visual Design System

#### Node Styling
```css
.kailash-node {
  background: #fff;
  border: 2px solid #ddd;
  border-radius: 8px;
  padding: 10px;
  min-width: 180px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.kailash-node.selected {
  border-color: #0084ff;
  box-shadow: 0 0 0 2px rgba(0,132,255,0.3);
}

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}

/* Loop edge styling */
.react-flow__edge-path.loop-edge {
  stroke-dasharray: 5;
  stroke: #9b59b6;
  animation: dash 1s linear infinite;
}

@keyframes dash {
  to {
    stroke-dashoffset: -10;
  }
}
```

### 7. Migration Steps

1. **Remove current canvas implementation**
   - Delete existing WorkflowCanvas component
   - Remove mixed handle types

2. **Implement Zustand store**
   - Create workflow store with proper TypeScript types
   - Add conversion methods for backend format

3. **Create new node components**
   - Fixed left/right handles
   - Category-based styling
   - Support for multiple outputs where needed

4. **Implement node palette**
   - Categorized node list from backend registry
   - Drag-and-drop with proper node creation

5. **Add connection validation**
   - Loop detection and validation
   - Proper error messages

6. **Implement execution visualization**
   - Show data flow during execution
   - Node status indicators

## Next Steps

1. First, fix the LoopNode implementation errors in the backend
2. Create the Zustand store structure
3. Implement the new canvas with n8n patterns
4. Add proper state synchronization with backend
5. Implement execution visualization
