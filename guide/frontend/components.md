# Component Development Patterns

This guide covers best practices and patterns for developing reusable, maintainable React components for Kailash frontend applications.

## 🎯 Component Philosophy

### Core Principles
1. **Single Responsibility**: Each component should do one thing well
2. **Composition over Inheritance**: Build complex UIs from simple components
3. **Declarative over Imperative**: Describe what the UI should look like
4. **Type Safety**: Leverage TypeScript for all components
5. **Accessibility First**: Build inclusive components from the start

## 📦 Component Categories

### 1. Base Components (Atoms)
```typescript
// src/components/base/Button/Button.tsx
import React, { forwardRef } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/utils/cn';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input hover:bg-accent hover:text-accent-foreground',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'underline-offset-4 hover:underline text-primary',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4 py-2',
        lg: 'h-12 px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Spinner className="mr-2 h-4 w-4 animate-spin" />}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
```

### 2. Form Components
```typescript
// src/components/form/Input/Input.tsx
import React, { forwardRef } from 'react';
import { cn } from '@/utils/cn';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, leftIcon, rightIcon, id, ...props }, ref) => {
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              {leftIcon}
            </div>
          )}
          <input
            id={inputId}
            ref={ref}
            className={cn(
              'block w-full rounded-md border-gray-300 shadow-sm',
              'focus:border-primary focus:ring-primary sm:text-sm',
              leftIcon && 'pl-10',
              rightIcon && 'pr-10',
              error && 'border-red-500 focus:border-red-500 focus:ring-red-500',
              className
            )}
            aria-invalid={!!error}
            aria-describedby={error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
            {...props}
          />
          {rightIcon && (
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
              {rightIcon}
            </div>
          )}
        </div>
        {error && (
          <p id={`${inputId}-error`} className="mt-1 text-sm text-red-600">
            {error}
          </p>
        )}
        {helperText && !error && (
          <p id={`${inputId}-helper`} className="mt-1 text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

// src/components/form/Select/Select.tsx
interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps {
  options: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  label?: string;
  error?: string;
  multiple?: boolean;
}

export const Select: React.FC<SelectProps> = ({
  options,
  value,
  onChange,
  placeholder = 'Select an option',
  label,
  error,
  multiple = false,
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
        </label>
      )}
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        multiple={multiple}
        className={cn(
          'block w-full rounded-md border-gray-300 shadow-sm',
          'focus:border-primary focus:ring-primary sm:text-sm',
          error && 'border-red-500'
        )}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
};
```

### 3. Layout Components
```typescript
// src/components/layout/Card/Card.tsx
interface CardProps {
  children: React.ReactNode;
  className?: string;
  variant?: 'default' | 'bordered' | 'elevated';
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export const Card: React.FC<CardProps> & {
  Header: React.FC<{ children: React.ReactNode; className?: string }>;
  Body: React.FC<{ children: React.ReactNode; className?: string }>;
  Footer: React.FC<{ children: React.ReactNode; className?: string }>;
} = ({ children, className, variant = 'default', padding = 'md' }) => {
  const variantClasses = {
    default: 'bg-white',
    bordered: 'bg-white border border-gray-200',
    elevated: 'bg-white shadow-md',
  };

  const paddingClasses = {
    none: '',
    sm: 'p-3',
    md: 'p-6',
    lg: 'p-8',
  };

  return (
    <div
      className={cn(
        'rounded-lg',
        variantClasses[variant],
        paddingClasses[padding],
        className
      )}
    >
      {children}
    </div>
  );
};

Card.Header = ({ children, className }) => (
  <div className={cn('pb-4 border-b border-gray-200', className)}>
    {children}
  </div>
);

Card.Body = ({ children, className }) => (
  <div className={cn('py-4', className)}>{children}</div>
);

Card.Footer = ({ children, className }) => (
  <div className={cn('pt-4 border-t border-gray-200', className)}>
    {children}
  </div>
);

// src/components/layout/Grid/Grid.tsx
interface GridProps {
  children: React.ReactNode;
  cols?: 1 | 2 | 3 | 4 | 6 | 12;
  gap?: 'none' | 'sm' | 'md' | 'lg';
  className?: string;
}

export const Grid: React.FC<GridProps> = ({
  children,
  cols = 1,
  gap = 'md',
  className,
}) => {
  const colClasses = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
    6: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-6',
    12: 'grid-cols-3 md:grid-cols-6 lg:grid-cols-12',
  };

  const gapClasses = {
    none: 'gap-0',
    sm: 'gap-2',
    md: 'gap-4',
    lg: 'gap-6',
  };

  return (
    <div
      className={cn('grid', colClasses[cols], gapClasses[gap], className)}
    >
      {children}
    </div>
  );
};
```

## 🎨 Workflow-Specific Components

### Node Components
```typescript
// src/components/workflow/nodes/BaseNode/BaseNode.tsx
import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Card } from '@/components/layout/Card';
import { NodeIcon } from '../NodeIcon';

export interface BaseNodeData {
  label: string;
  type: string;
  config?: Record<string, any>;
  status?: 'idle' | 'running' | 'success' | 'error';
  error?: string;
}

export const BaseNode = memo<NodeProps<BaseNodeData>>(({ data, selected }) => {
  const statusColors = {
    idle: 'border-gray-300',
    running: 'border-blue-500 animate-pulse',
    success: 'border-green-500',
    error: 'border-red-500',
  };

  return (
    <Card
      variant="bordered"
      padding="sm"
      className={cn(
        'min-w-[200px] transition-all',
        selected && 'ring-2 ring-primary ring-offset-2',
        statusColors[data.status || 'idle']
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-gray-400 border-2 border-white"
      />

      <div className="flex items-center space-x-2">
        <NodeIcon type={data.type} status={data.status} />
        <div className="flex-1">
          <h4 className="font-medium text-sm">{data.label}</h4>
          <p className="text-xs text-gray-500">{data.type}</p>
        </div>
      </div>

      {data.status === 'error' && data.error && (
        <div className="mt-2 p-2 bg-red-50 rounded text-xs text-red-700">
          {data.error}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-gray-400 border-2 border-white"
      />
    </Card>
  );
});

BaseNode.displayName = 'BaseNode';

// src/components/workflow/nodes/DataReaderNode/DataReaderNode.tsx
export const DataReaderNode = memo<NodeProps<DataReaderNodeData>>(({ data, id }) => {
  const { config = {} } = data;

  return (
    <BaseNode data={data} id={id}>
      <div className="mt-2 space-y-1">
        <div className="text-xs">
          <span className="text-gray-500">Source:</span>
          <span className="ml-1 font-medium">{config.source || 'Not configured'}</span>
        </div>
        {config.format && (
          <div className="text-xs">
            <span className="text-gray-500">Format:</span>
            <span className="ml-1 font-medium">{config.format}</span>
          </div>
        )}
      </div>
    </BaseNode>
  );
});
```

### Workflow Canvas Component
```typescript
// src/components/workflow/WorkflowCanvas/WorkflowCanvas.tsx
import React, { useCallback, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Controls,
  MiniMap,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { DataReaderNode } from '../nodes/DataReaderNode';
import { TransformNode } from '../nodes/TransformNode';
import { OutputNode } from '../nodes/OutputNode';

const nodeTypes = {
  dataReader: DataReaderNode,
  transform: TransformNode,
  output: OutputNode,
};

interface WorkflowCanvasProps {
  initialNodes?: Node[];
  initialEdges?: Edge[];
  onNodesChange?: (nodes: Node[]) => void;
  onEdgesChange?: (edges: Edge[]) => void;
  onNodeDoubleClick?: (node: Node) => void;
  readOnly?: boolean;
}

export const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  initialNodes = [],
  initialEdges = [],
  onNodesChange: onNodesChangeProp,
  onEdgesChange: onEdgesChangeProp,
  onNodeDoubleClick,
  readOnly = false,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => {
      const newEdge = {
        ...params,
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
      };
      setEdges((eds) => addEdge(newEdge, eds));
    },
    [setEdges]
  );

  const handleNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      onNodesChangeProp?.(nodes);
    },
    [nodes, onNodesChange, onNodesChangeProp]
  );

  const handleEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      onEdgesChangeProp?.(edges);
    },
    [edges, onEdgesChange, onEdgesChangeProp]
  );

  const proOptions = useMemo(() => ({ hideAttribution: true }), []);

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeDoubleClick={(_, node) => onNodeDoubleClick?.(node)}
        nodeTypes={nodeTypes}
        fitView
        proOptions={proOptions}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
      >
        <Background variant="dots" gap={16} size={1} />
        <Controls />
        <MiniMap
          nodeStrokeColor={(node) => {
            if (node.data?.status === 'error') return '#ef4444';
            if (node.data?.status === 'success') return '#10b981';
            if (node.data?.status === 'running') return '#3b82f6';
            return '#9ca3af';
          }}
          nodeColor="#f3f4f6"
          nodeBorderRadius={8}
        />
      </ReactFlow>
    </div>
  );
};
```

### Parameter Form Component
```typescript
// src/components/workflow/ParameterForm/ParameterForm.tsx
import React from 'react';
import { Input } from '@/components/form/Input';
import { Select } from '@/components/form/Select';
import { Switch } from '@/components/form/Switch';
import { FileUpload } from '@/components/form/FileUpload';

export interface Parameter {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'file' | 'json';
  label: string;
  description?: string;
  required?: boolean;
  default?: any;
  options?: Array<{ value: string; label: string }>;
  validation?: {
    min?: number;
    max?: number;
    pattern?: string;
    maxSize?: number;
    allowedTypes?: string[];
  };
}

interface ParameterFormProps {
  parameters: Parameter[];
  values: Record<string, any>;
  onChange: (name: string, value: any) => void;
  errors?: Record<string, string>;
}

export const ParameterForm: React.FC<ParameterFormProps> = ({
  parameters,
  values,
  onChange,
  errors = {},
}) => {
  const renderField = (param: Parameter) => {
    const value = values[param.name] ?? param.default;
    const error = errors[param.name];

    switch (param.type) {
      case 'string':
        return (
          <Input
            value={value || ''}
            onChange={(e) => onChange(param.name, e.target.value)}
            label={param.label}
            error={error}
            helperText={param.description}
            required={param.required}
          />
        );

      case 'number':
        return (
          <Input
            type="number"
            value={value || ''}
            onChange={(e) => onChange(param.name, parseFloat(e.target.value))}
            label={param.label}
            error={error}
            helperText={param.description}
            required={param.required}
            min={param.validation?.min}
            max={param.validation?.max}
          />
        );

      case 'boolean':
        return (
          <Switch
            checked={value || false}
            onChange={(checked) => onChange(param.name, checked)}
            label={param.label}
            helperText={param.description}
          />
        );

      case 'select':
        return (
          <Select
            value={value || ''}
            onChange={(val) => onChange(param.name, val)}
            options={param.options || []}
            label={param.label}
            error={error}
            placeholder={`Select ${param.label}`}
          />
        );

      case 'file':
        return (
          <FileUpload
            value={value}
            onChange={(file) => onChange(param.name, file)}
            label={param.label}
            error={error}
            helperText={param.description}
            accept={param.validation?.allowedTypes?.join(',')}
            maxSize={param.validation?.maxSize}
          />
        );

      case 'json':
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {param.label}
            </label>
            <textarea
              value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  onChange(param.name, parsed);
                } catch {
                  onChange(param.name, e.target.value);
                }
              }}
              className={cn(
                'block w-full rounded-md border-gray-300 shadow-sm',
                'focus:border-primary focus:ring-primary sm:text-sm',
                'font-mono text-xs',
                error && 'border-red-500'
              )}
              rows={6}
            />
            {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
            {param.description && (
              <p className="mt-1 text-sm text-gray-500">{param.description}</p>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-4">
      {parameters.map((param) => (
        <div key={param.name}>{renderField(param)}</div>
      ))}
    </div>
  );
};
```

## 🚀 Advanced Component Patterns

### Render Props Pattern
```typescript
// src/components/patterns/DataFetcher/DataFetcher.tsx
interface DataFetcherProps<T> {
  url: string;
  children: (props: {
    data: T | null;
    loading: boolean;
    error: Error | null;
    refetch: () => void;
  }) => React.ReactNode;
}

export function DataFetcher<T>({ url, children }: DataFetcherProps<T>) {
  const [state, setState] = useState<{
    data: T | null;
    loading: boolean;
    error: Error | null;
  }>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchData = useCallback(async () => {
    setState({ data: null, loading: true, error: null });
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      setState({ data, loading: false, error: null });
    } catch (error) {
      setState({ data: null, loading: false, error: error as Error });
    }
  }, [url]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return <>{children({ ...state, refetch: fetchData })}</>;
}

// Usage
<DataFetcher<Workflow[]> url="/api/workflows">
  {({ data, loading, error, refetch }) => {
    if (loading) return <Spinner />;
    if (error) return <ErrorMessage error={error} onRetry={refetch} />;
    return <WorkflowList workflows={data!} />;
  }}
</DataFetcher>
```

### Higher-Order Component Pattern
```typescript
// src/components/hoc/withErrorBoundary.tsx
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ComponentType<{ error: Error }> },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Component error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError && this.state.error) {
      const Fallback = this.props.fallback || DefaultErrorFallback;
      return <Fallback error={this.state.error} />;
    }

    return this.props.children;
  }
}

export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: React.ComponentType<{ error: Error }>
) {
  return (props: P) => (
    <ErrorBoundary fallback={fallback}>
      <Component {...props} />
    </ErrorBoundary>
  );
}

// Usage
const SafeWorkflowCanvas = withErrorBoundary(WorkflowCanvas, WorkflowErrorFallback);
```

### Custom Hook Pattern
```typescript
// src/hooks/useDebounce.ts
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

// src/hooks/useLocalStorage.ts
export function useLocalStorage<T>(
  key: string,
  initialValue: T
): [T, (value: T | ((val: T) => T)) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(`Error loading localStorage key "${key}":`, error);
      return initialValue;
    }
  });

  const setValue = (value: T | ((val: T) => T)) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(`Error saving localStorage key "${key}":`, error);
    }
  };

  return [storedValue, setValue];
}

// src/hooks/useAsync.ts
interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

export function useAsync<T>(
  asyncFunction: () => Promise<T>,
  immediate = true
): AsyncState<T> & { execute: () => Promise<void> } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: immediate,
  });

  const execute = useCallback(async () => {
    setState({ data: null, error: null, loading: true });
    try {
      const data = await asyncFunction();
      setState({ data, error: null, loading: false });
    } catch (error) {
      setState({ data: null, error: error as Error, loading: false });
    }
  }, [asyncFunction]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate]);

  return { ...state, execute };
}
```

## 📐 Component Testing

### Unit Testing
```typescript
// src/components/base/Button/Button.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('renders children correctly', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button')).toHaveTextContent('Click me');
  });

  it('handles click events', () => {
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('disables button when loading', () => {
    render(<Button loading>Click me</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies variant classes correctly', () => {
    const { rerender } = render(<Button variant="primary">Click me</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-primary');

    rerender(<Button variant="destructive">Click me</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-destructive');
  });
});
```

### Integration Testing
```typescript
// src/components/workflow/WorkflowRunner/WorkflowRunner.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { WorkflowRunner } from './WorkflowRunner';
import { workflowReducer } from '@/store/slices/workflowSlice';

const renderWithStore = (component: React.ReactElement) => {
  const store = configureStore({
    reducer: { workflow: workflowReducer },
  });
  return render(<Provider store={store}>{component}</Provider>);
};

describe('WorkflowRunner', () => {
  it('executes workflow with parameters', async () => {
    const mockWorkflow = {
      id: '1',
      name: 'Test Workflow',
      parameters: [
        { name: 'input', type: 'string', label: 'Input Data' },
      ],
    };

    renderWithStore(<WorkflowRunner workflow={mockWorkflow} />);

    // Fill in parameters
    const input = screen.getByLabelText('Input Data');
    await userEvent.type(input, 'test data');

    // Execute workflow
    const executeButton = screen.getByRole('button', { name: /execute/i });
    await userEvent.click(executeButton);

    // Wait for execution to complete
    await waitFor(() => {
      expect(screen.getByText(/execution complete/i)).toBeInTheDocument();
    });
  });
});
```

## 🎯 Performance Optimization

### Memoization
```typescript
// src/components/expensive/DataGrid/DataGrid.tsx
import React, { memo, useMemo } from 'react';

interface DataGridProps {
  data: any[];
  columns: Column[];
  onRowClick?: (row: any) => void;
}

export const DataGrid = memo<DataGridProps>(
  ({ data, columns, onRowClick }) => {
    // Memoize expensive calculations
    const processedData = useMemo(() => {
      return data.map((row) => ({
        ...row,
        _processed: true,
        _id: row.id || Math.random(),
      }));
    }, [data]);

    const sortedColumns = useMemo(() => {
      return [...columns].sort((a, b) => (a.order || 0) - (b.order || 0));
    }, [columns]);

    return (
      <table className="data-grid">
        <thead>
          <tr>
            {sortedColumns.map((col) => (
              <th key={col.key}>{col.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {processedData.map((row) => (
            <DataGridRow
              key={row._id}
              row={row}
              columns={sortedColumns}
              onClick={onRowClick}
            />
          ))}
        </tbody>
      </table>
    );
  },
  // Custom comparison function
  (prevProps, nextProps) => {
    return (
      prevProps.data === nextProps.data &&
      prevProps.columns === nextProps.columns &&
      prevProps.onRowClick === nextProps.onRowClick
    );
  }
);

const DataGridRow = memo<{
  row: any;
  columns: Column[];
  onClick?: (row: any) => void;
}>(({ row, columns, onClick }) => {
  const handleClick = useCallback(() => {
    onClick?.(row);
  }, [onClick, row]);

  return (
    <tr onClick={handleClick} className="cursor-pointer hover:bg-gray-50">
      {columns.map((col) => (
        <td key={col.key}>{col.render ? col.render(row) : row[col.key]}</td>
      ))}
    </tr>
  );
});
```

### Code Splitting
```typescript
// src/components/heavy/ChartVisualization/ChartVisualization.tsx
import React, { lazy, Suspense } from 'react';
import { Spinner } from '@/components/base/Spinner';

// Lazy load heavy chart library
const Chart = lazy(() => import('react-chartjs-2').then(module => ({ default: module.Chart })));

interface ChartVisualizationProps {
  data: any;
  type: 'line' | 'bar' | 'pie';
}

export const ChartVisualization: React.FC<ChartVisualizationProps> = ({ data, type }) => {
  return (
    <Suspense fallback={<Spinner />}>
      <Chart type={type} data={data} />
    </Suspense>
  );
};
```

## 🔍 Component Documentation

### Storybook Integration
```typescript
// src/components/base/Button/Button.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'Base/Button',
  component: Button,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: { type: 'select' },
      options: ['primary', 'secondary', 'destructive', 'outline', 'ghost', 'link'],
    },
    size: {
      control: { type: 'select' },
      options: ['sm', 'md', 'lg', 'icon'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    variant: 'primary',
    children: 'Primary Button',
  },
};

export const WithLoading: Story = {
  args: {
    loading: true,
    children: 'Loading...',
  },
};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-col space-y-4">
      <Button variant="primary">Primary</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="destructive">Destructive</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="link">Link</Button>
    </div>
  ),
};
```

## 📋 Component Checklist

When creating new components, ensure:

- [ ] **TypeScript**: Full type safety with proper interfaces
- [ ] **Props**: Well-defined props with defaults where appropriate
- [ ] **Accessibility**: ARIA labels, keyboard navigation, screen reader support
- [ ] **Styling**: Uses design system tokens and responsive design
- [ ] **Performance**: Memoization where needed, lazy loading for heavy components
- [ ] **Testing**: Unit tests with good coverage
- [ ] **Documentation**: Storybook stories and JSDoc comments
- [ ] **Error Handling**: Graceful error states and boundaries
- [ ] **Loading States**: Appropriate loading indicators
- [ ] **Responsive**: Works on all screen sizes

## 🚀 Best Practices

1. **Keep It Simple**: Start with the simplest implementation
2. **Composition**: Build complex components from simple ones
3. **Reusability**: Design components to be reused across the application
4. **Testability**: Write components that are easy to test
5. **Performance**: Optimize only when necessary, measure first
6. **Accessibility**: Build inclusive components from the start
7. **Documentation**: Document props, usage, and examples
