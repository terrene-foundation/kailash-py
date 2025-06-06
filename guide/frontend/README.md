# Kailash Frontend Development Guide

Welcome to the Kailash Frontend Development Guide. This comprehensive documentation provides guidelines, patterns, and best practices for building frontend applications that integrate with the Kailash Python SDK.

## 📚 Documentation Structure

### Core Guidelines
- **[Architecture](architecture.md)** - System design, state management, and architectural patterns
- **[Components](components.md)** - Component development patterns and reusable UI elements
- **[API Integration](api-integration.md)** - Backend communication and data flow patterns
- **[Styling](styling.md)** - UI/UX guidelines, theming, and responsive design
- **[Testing](testing.md)** - Testing strategies and implementation
- **[Debugging](debugging.md)** - Debugging techniques and troubleshooting

## 🚀 Quick Start

### 1. Technology Stack
```javascript
// Recommended stack for Kailash frontend applications
{
  "framework": "React 18+",
  "typescript": "5.0+",
  "state": "Redux Toolkit / Zustand",
  "styling": "Tailwind CSS / CSS Modules",
  "api": "Axios / React Query",
  "testing": "Jest + React Testing Library",
  "build": "Vite / Next.js"
}
```

### 2. Project Setup
```bash
# Create new Kailash frontend project
npx create-vite@latest kailash-ui --template react-ts
cd kailash-ui

# Install core dependencies
npm install axios react-query @reduxjs/toolkit react-redux
npm install -D @testing-library/react @testing-library/jest-dom
npm install -D tailwindcss postcss autoprefixer
```

### 3. Basic Integration Example
```typescript
// src/services/kailash.ts
import axios from 'axios';

const API_BASE_URL = process.env.VITE_KAILASH_API_URL || 'http://localhost:8000';

export const kailashAPI = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Workflow execution
export const executeWorkflow = async (workflowId: string, parameters: Record<string, any>) => {
  const response = await kailashAPI.post(`/workflows/${workflowId}/execute`, { parameters });
  return response.data;
};
```

## 📋 Development Workflow

### 1. Component Development
```typescript
// Follow the component pattern
// src/components/WorkflowRunner/WorkflowRunner.tsx
import React, { useState } from 'react';
import { useWorkflowExecution } from '../../hooks/useWorkflowExecution';
import { WorkflowStatus } from './WorkflowStatus';
import { ParameterForm } from './ParameterForm';

export const WorkflowRunner: React.FC<{ workflowId: string }> = ({ workflowId }) => {
  const [parameters, setParameters] = useState({});
  const { execute, status, result, error } = useWorkflowExecution(workflowId);

  const handleSubmit = () => {
    execute(parameters);
  };

  return (
    <div className="workflow-runner">
      <ParameterForm onChange={setParameters} />
      <button onClick={handleSubmit}>Execute Workflow</button>
      <WorkflowStatus status={status} result={result} error={error} />
    </div>
  );
};
```

### 2. State Management Pattern
```typescript
// src/store/workflowSlice.ts
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { executeWorkflow } from '../services/kailash';

export const runWorkflow = createAsyncThunk(
  'workflow/execute',
  async ({ id, parameters }: { id: string; parameters: any }) => {
    return await executeWorkflow(id, parameters);
  }
);

const workflowSlice = createSlice({
  name: 'workflow',
  initialState: {
    executions: {},
    status: 'idle',
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(runWorkflow.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(runWorkflow.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.executions[action.meta.arg.id] = action.payload;
      });
  },
});
```

## 🎯 Key Principles

### 1. Component Architecture
- **Atomic Design**: Build from atoms → molecules → organisms → templates → pages
- **Single Responsibility**: Each component should do one thing well
- **Composition over Inheritance**: Use component composition patterns
- **Type Safety**: Leverage TypeScript for all components and utilities

### 2. State Management
- **Local State First**: Use component state for UI-only concerns
- **Global State When Needed**: Use Redux/Zustand for cross-component state
- **Server State Separately**: Use React Query for server data caching
- **Immutable Updates**: Never mutate state directly

### 3. Performance
- **Code Splitting**: Lazy load routes and heavy components
- **Memoization**: Use React.memo, useMemo, useCallback appropriately
- **Virtual Lists**: For large data sets, use windowing techniques
- **Bundle Optimization**: Monitor and optimize bundle size

### 4. Accessibility
- **Semantic HTML**: Use proper HTML elements for their intended purpose
- **ARIA Labels**: Add appropriate ARIA attributes when needed
- **Keyboard Navigation**: Ensure all interactive elements are keyboard accessible
- **Screen Reader Support**: Test with screen readers regularly

## 🔧 Common Patterns

### Workflow Visualization
```typescript
// Render workflow graph using D3.js or React Flow
import ReactFlow from 'reactflow';

export const WorkflowGraph: React.FC<{ workflow: Workflow }> = ({ workflow }) => {
  const nodes = workflow.nodes.map(node => ({
    id: node.id,
    data: { label: node.name },
    position: { x: node.x || 0, y: node.y || 0 },
  }));

  const edges = workflow.connections.map(conn => ({
    id: `${conn.from}-${conn.to}`,
    source: conn.from,
    target: conn.to,
  }));

  return <ReactFlow nodes={nodes} edges={edges} fitView />;
};
```

### Real-time Updates
```typescript
// WebSocket integration for live workflow status
useEffect(() => {
  const ws = new WebSocket(`ws://localhost:8000/ws/workflow/${workflowId}`);

  ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    dispatch(updateWorkflowStatus(update));
  };

  return () => ws.close();
}, [workflowId]);
```

## 📊 Monitoring & Analytics

### Performance Monitoring
```typescript
// Track component render performance
import { Profiler } from 'react';

<Profiler
  id="WorkflowRunner"
  onRender={(id, phase, actualDuration) => {
    console.log(`${id} (${phase}) took ${actualDuration}ms`);
  }}
>
  <WorkflowRunner />
</Profiler>
```

### Error Tracking
```typescript
// Global error boundary
export class ErrorBoundary extends React.Component {
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('UI Error:', error, errorInfo);
    // Send to monitoring service
  }
}
```

## 🚦 Getting Started Checklist

- [ ] Set up development environment with recommended tools
- [ ] Review [Architecture Guidelines](architecture.md)
- [ ] Understand [Component Patterns](components.md)
- [ ] Learn [API Integration](api-integration.md) patterns
- [ ] Apply [Styling Guidelines](styling.md)
- [ ] Implement [Testing Strategy](testing.md)
- [ ] Set up [Debugging Tools](debugging.md)

## 📖 Additional Resources

### Internal Documentation
- [Kailash Python SDK Documentation](../../README.md)
- [API Reference](../reference/api-registry.yaml)
- [Workflow Patterns](../reference/pattern-library.md)

### External Resources
- [React Documentation](https://react.dev)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Redux Toolkit Guide](https://redux-toolkit.js.org)
- [React Query Documentation](https://tanstack.com/query)

## 🤝 Contributing

When contributing to frontend code:
1. Follow the established patterns in this guide
2. Write comprehensive tests for new features
3. Update documentation as needed
4. Ensure accessibility standards are met
5. Optimize for performance

For questions or suggestions, please refer to the main [Contributing Guide](../../CONTRIBUTING.md).
