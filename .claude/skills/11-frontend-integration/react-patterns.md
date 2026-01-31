---
name: react-patterns
description: "React and Next.js implementation patterns for Kailash SDK integration including React Flow workflow editors, TanStack Query, Zustand state, and Nexus/DataFlow/Kaizen clients. Use for 'react patterns', 'react flow', 'workflow editor', 'next.js patterns', or 'react kailash'."
---

# React Implementation Patterns

> **Skill Metadata**
> Category: `frontend`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> React Version: `19+`
> Next.js Version: `15+`

## Kailash SDK Integration

### Nexus API Client

```typescript
import axios from 'axios';

const nexusClient = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' }
});

async function executeWorkflow(workflowId: string, params: Record<string, any>) {
  const { data } = await nexusClient.post(`/workflows/${workflowId}/execute`, params);
  return data;
}
```

### DataFlow Admin Dashboard

```typescript
function DataFlowBulkOperations() {
  const { data, isPending } = useQuery({
    queryKey: ['dataflow-models'],
    queryFn: () => fetch('/api/dataflow/models').then(res => res.json())
  });

  if (isPending) return <DataFlowSkeleton />;

  return (
    <div className="grid gap-4">
      {data.models.map(model => (
        <BulkOperationCard key={model.name} model={model} />
      ))}
    </div>
  );
}
```

### Kaizen AI Chat Interface

```typescript
function KaizenChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);

  const { mutate: sendMessage, isPending } = useMutation({
    mutationFn: (text: string) =>
      fetch('/api/kaizen/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text })
      }).then(res => res.json()),
    onSuccess: (data) => {
      setMessages(prev => [...prev, data.response]);
    }
  });

  return <ChatUI messages={messages} onSend={sendMessage} loading={isPending} />;
}
```

## React Flow Workflow Editor

### Custom Node Implementation

```typescript
import { Handle, Position } from 'reactflow';

interface KaizenNodeProps {
  data: {
    label: string;
    agentType: string;
    parameters: Record<string, any>;
  };
}

export function KaizenAgentNode({ data }: KaizenNodeProps) {
  return (
    <div className="bg-white border-2 border-purple-500 rounded-lg p-4 shadow-lg">
      <Handle type="target" position={Position.Top} />

      <div className="flex items-center gap-2">
        <div className="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center">
          <span className="text-white text-xs">AI</span>
        </div>
        <div>
          <div className="font-semibold">{data.label}</div>
          <div className="text-xs text-gray-500">{data.agentType}</div>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

// Register custom node
const nodeTypes = {
  kaizenAgent: KaizenAgentNode,
  dataflowQuery: DataFlowQueryNode,
  nexusEndpoint: NexusEndpointNode
};

<ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} />
```

### Performance Optimization

```typescript
import { useNodesState, useEdgesState } from 'reactflow';

function WorkflowCanvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}  // Optimized updates
      onEdgesChange={onEdgesChange}  // Only changed elements
      fitView
    />
  );
}
```

### Drag & Drop from Palette

```typescript
function NodePalette() {
  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="node-palette">
      {nodeDefinitions.map(node => (
        <div
          key={node.type}
          draggable
          onDragStart={(e) => onDragStart(e, node.type)}
          className="cursor-move p-2 border rounded"
        >
          {node.label}
        </div>
      ))}
    </div>
  );
}

// Canvas drop handler
function WorkflowCanvas() {
  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    const type = event.dataTransfer.getData('application/reactflow');

    const position = reactFlowInstance.project({
      x: event.clientX,
      y: event.clientY,
    });

    const newNode = {
      id: `${type}-${Date.now()}`,
      type,
      position,
      data: { label: type }
    };

    setNodes(nds => [...nds, newNode]);
  }, [reactFlowInstance]);

  return (
    <div onDrop={onDrop} onDragOver={(e) => e.preventDefault()}>
      <ReactFlow ... />
    </div>
  );
}
```

## Architecture Patterns

### Modular Component Structure

```
[feature]/
├── index.tsx           # Entry point: QueryClientProvider + orchestration
├── elements/           # Low-level UI building blocks
│   ├── WorkflowCanvas.tsx
│   ├── NodePalette.tsx
│   ├── PropertyPanel.tsx
│   ├── ExecutionStatus.tsx
│   └── [Feature]Skeleton.tsx
```

### One API Call Per Component

```typescript
// elements/WorkflowList.tsx - CORRECT
function WorkflowList() {
  const { isPending, error, data } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => fetch('/api/workflows').then(res => res.json())
  });

  if (isPending) return <WorkflowListSkeleton />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <div className="grid gap-4">
      {data.workflows.map(workflow => (
        <WorkflowCard key={workflow.id} workflow={workflow} />
      ))}
    </div>
  );
}

// DON'T DO THIS - Multiple API calls in one component
function Dashboard() {
  const workflows = useQuery({...});     // NO!
  const executions = useQuery({...});    // Split into
  const agents = useQuery({...});        // separate components!
}
```

## VS Code Webview Integration

```typescript
declare function acquireVsCodeApi(): {
  postMessage: (message: any) => void;
  setState: (state: any) => void;
  getState: () => any;
};

const vscode = acquireVsCodeApi();

// React → VS Code
function saveWorkflow(workflow: Workflow) {
  vscode.postMessage({
    type: 'saveWorkflow',
    workflow
  });
}

// VS Code → React
useEffect(() => {
  window.addEventListener('message', (event) => {
    const message = event.data;

    switch (message.type) {
      case 'loadWorkflow':
        setNodes(message.workflow.nodes);
        setEdges(message.workflow.edges);
        break;
    }
  });
}, []);
```

## Workflow Execution

```typescript
async function executeKailashWorkflow(workflowDef: WorkflowDefinition) {
  const response = await fetch('/api/workflows/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_definition: workflowDef })
  });

  if (!response.ok) throw new Error('Workflow execution failed');
  return response.json();
}

function WorkflowExecutor({ workflow }: { workflow: WorkflowDefinition }) {
  const { mutate: execute, isPending, data } = useMutation({
    mutationFn: executeKailashWorkflow,
    onSuccess: (result) => {
      toast.success('Workflow executed successfully');
    },
    onError: (error) => {
      toast.error(`Execution failed: ${error.message}`);
    }
  });

  return (
    <Button onClick={() => execute(workflow)} disabled={isPending}>
      {isPending ? 'Executing...' : 'Execute Workflow'}
    </Button>
  );
}
```

## Real-Time Updates (WebSockets)

```typescript
function useWorkflowExecution(executionId: string) {
  const [status, setStatus] = useState<ExecutionStatus>('pending');
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/executions/${executionId}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'status') setStatus(data.status);
      if (data.type === 'log') setLogs(prev => [...prev, data.message]);
    };

    return () => ws.close();
  }, [executionId]);

  return { status, logs };
}
```

## Responsive Design

```typescript
// Tailwind responsive classes
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {/* Auto-adapts: 1 col mobile, 2 cols tablet, 3 cols desktop */}
</div>

// Conditional rendering
const isMobile = useMediaQuery('(max-width: 768px)');
return isMobile ? <MobileLayout /> : <DesktopLayout />;
```

## Loading States with shadcn

```typescript
import { Skeleton } from '@/components/ui/skeleton';

function WorkflowListSkeleton() {
  return (
    <div className="grid gap-4">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex gap-4 items-center">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

## TypeScript Best Practices

```typescript
// Use strict types
interface WorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, any>;
}

// Avoid 'any' - use generics or unknown
function executeWorkflow<T extends Record<string, any>>(params: T): Promise<WorkflowResult> {
  // ...
}
```

<!-- Trigger Keywords: react patterns, react flow, workflow editor, next.js patterns, react kailash, react nexus, react dataflow, react kaizen, tanstack query, zustand, react state management -->
