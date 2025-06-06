# Frontend Debugging Guide

This guide covers debugging techniques, tools, and best practices for troubleshooting Kailash frontend applications.

## 🔍 Debugging Overview

### Debugging Stack
```json
{
  "browser": "Chrome DevTools, React DevTools",
  "vscode": "Debugger for Chrome, Turbo Console Log",
  "network": "Network tab, Postman, Charles Proxy",
  "state": "Redux DevTools, React Query DevTools",
  "performance": "Performance Profiler, Lighthouse",
  "errors": "Error Boundaries, Sentry"
}
```

## 🛠️ Browser DevTools

### Chrome DevTools Setup
```javascript
// Enable source maps in webpack/vite config
// vite.config.ts
export default defineConfig({
  build: {
    sourcemap: true,
  },
  css: {
    devSourcemap: true,
  },
});

// webpack.config.js
module.exports = {
  devtool: 'source-map',
  // or for development:
  devtool: 'eval-source-map',
};
```

### Console Debugging Utilities
```typescript
// src/utils/debug.ts
export const debug = {
  // Enhanced console.log with styling
  log: (message: string, data?: any, style?: string) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(
        `%c[DEBUG] ${message}`,
        style || 'color: #3b82f6; font-weight: bold;',
        data || ''
      );
    }
  },

  // Group related logs
  group: (label: string, fn: () => void) => {
    if (process.env.NODE_ENV === 'development') {
      console.group(`🔍 ${label}`);
      fn();
      console.groupEnd();
    }
  },

  // Performance timing
  time: (label: string) => {
    if (process.env.NODE_ENV === 'development') {
      console.time(label);
    }
  },

  timeEnd: (label: string) => {
    if (process.env.NODE_ENV === 'development') {
      console.timeEnd(label);
    }
  },

  // Table for structured data
  table: (data: any[], columns?: string[]) => {
    if (process.env.NODE_ENV === 'development') {
      console.table(data, columns);
    }
  },

  // Stack trace
  trace: (message?: string) => {
    if (process.env.NODE_ENV === 'development') {
      console.trace(message || 'Stack trace');
    }
  },

  // Conditional breakpoint
  break: (condition: boolean, message?: string) => {
    if (process.env.NODE_ENV === 'development' && condition) {
      debugger; // eslint-disable-line no-debugger
      console.log(message || 'Breakpoint hit');
    }
  },
};

// Usage examples
debug.log('Component rendered', { props, state });
debug.group('API Call', () => {
  debug.log('Request', request);
  debug.log('Response', response);
});
debug.time('Heavy computation');
// ... computation
debug.timeEnd('Heavy computation');
```

### Component Debugging Helper
```typescript
// src/hooks/useDebugInfo.ts
export const useDebugInfo = (componentName: string, props: any) => {
  const renderCount = useRef(0);
  const previousProps = useRef(props);
  const changedProps = useRef<Record<string, any>>({});

  useEffect(() => {
    renderCount.current += 1;
  });

  useEffect(() => {
    if (previousProps.current) {
      const changes: Record<string, any> = {};

      Object.keys(props).forEach(key => {
        if (props[key] !== previousProps.current[key]) {
          changes[key] = {
            from: previousProps.current[key],
            to: props[key],
          };
        }
      });

      if (Object.keys(changes).length > 0) {
        changedProps.current = changes;
      }
    }

    previousProps.current = props;
  }, [props]);

  if (process.env.NODE_ENV === 'development') {
    console.group(`🔍 ${componentName} Debug Info`);
    console.log('Render count:', renderCount.current);
    console.log('Current props:', props);

    if (Object.keys(changedProps.current).length > 0) {
      console.log('Changed props:', changedProps.current);
    }

    console.groupEnd();
  }

  return {
    renderCount: renderCount.current,
    changedProps: changedProps.current,
  };
};

// Usage in component
export const MyComponent: React.FC<Props> = (props) => {
  useDebugInfo('MyComponent', props);

  // Component logic...
};
```

## 🔵 React DevTools

### React DevTools Configuration
```typescript
// src/utils/devtools.ts
export const setupReactDevTools = () => {
  if (process.env.NODE_ENV === 'development') {
    // Add component display names for better debugging
    if (typeof window !== 'undefined' && window.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
      // Custom component names
      window.__REACT_DEVTOOLS_GLOBAL_HOOK__.onComponentDisplayName = (id: number, displayName: string) => {
        // Add custom prefixes or formatting
        return `🧩 ${displayName}`;
      };
    }
  }
};

// Component debugging with display names
export const WorkflowCard = React.memo<WorkflowCardProps>(({ workflow, onEdit, onDelete }) => {
  // Component implementation
});

// IMPORTANT: Set display name for debugging
WorkflowCard.displayName = 'WorkflowCard';

// HOC with preserved display name
export const withAuth = <P extends object>(Component: React.ComponentType<P>) => {
  const WithAuthComponent = (props: P) => {
    const { user } = useAuth();

    if (!user) {
      return <Navigate to="/login" />;
    }

    return <Component {...props} />;
  };

  // Preserve original component name
  WithAuthComponent.displayName = `withAuth(${Component.displayName || Component.name || 'Component'})`;

  return WithAuthComponent;
};
```

### Profiler API Usage
```typescript
// src/components/PerformanceMonitor.tsx
interface ProfilerData {
  id: string;
  phase: 'mount' | 'update';
  actualDuration: number;
  baseDuration: number;
  startTime: number;
  commitTime: number;
}

export const PerformanceMonitor: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [metrics, setMetrics] = useState<ProfilerData[]>([]);

  const onRender = (
    id: string,
    phase: 'mount' | 'update',
    actualDuration: number,
    baseDuration: number,
    startTime: number,
    commitTime: number
  ) => {
    const data: ProfilerData = {
      id,
      phase,
      actualDuration,
      baseDuration,
      startTime,
      commitTime,
    };

    if (process.env.NODE_ENV === 'development') {
      console.log(`⏱️ ${id} (${phase}):`, {
        actualDuration: `${actualDuration.toFixed(2)}ms`,
        baseDuration: `${baseDuration.toFixed(2)}ms`,
        slowRender: actualDuration > 16, // 60fps threshold
      });
    }

    setMetrics(prev => [...prev, data]);

    // Alert on slow renders
    if (actualDuration > 16) {
      console.warn(`🐌 Slow render detected in ${id}: ${actualDuration.toFixed(2)}ms`);
    }
  };

  return (
    <Profiler id="App" onRender={onRender}>
      {children}
      {process.env.NODE_ENV === 'development' && (
        <div className="fixed bottom-4 right-4 bg-black/80 text-white p-2 rounded text-xs">
          Last render: {metrics[metrics.length - 1]?.actualDuration.toFixed(2)}ms
        </div>
      )}
    </Profiler>
  );
};
```

## 🔴 Redux DevTools

### Redux DevTools Setup
```typescript
// src/store/store.ts
import { configureStore } from '@reduxjs/toolkit';
import { createLogger } from 'redux-logger';

const logger = createLogger({
  predicate: () => process.env.NODE_ENV === 'development',
  collapsed: true,
  duration: true,
  diff: true,
  colors: {
    title: () => '#139BFE',
    prevState: () => '#9E9E9E',
    action: () => '#03A9F4',
    nextState: () => '#4CAF50',
    error: () => '#F44336',
  },
});

export const store = configureStore({
  reducer: {
    // reducers
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types
        ignoredActions: ['persist/PERSIST'],
        // Ignore these paths in the state
        ignoredPaths: ['api.queries'],
      },
    }).concat(logger),
  devTools: process.env.NODE_ENV === 'development' && {
    name: 'Kailash App',
    trace: true,
    traceLimit: 25,
    actionSanitizer: (action) => {
      // Sanitize sensitive data
      if (action.type === 'auth/login/fulfilled') {
        return {
          ...action,
          payload: {
            ...action.payload,
            token: '[REDACTED]',
          },
        };
      }
      return action;
    },
    stateSanitizer: (state) => {
      // Sanitize sensitive state
      return {
        ...state,
        auth: {
          ...state.auth,
          token: state.auth?.token ? '[REDACTED]' : null,
        },
      };
    },
  },
});

// Custom middleware for debugging
const debugMiddleware: Middleware = (store) => (next) => (action) => {
  if (process.env.NODE_ENV === 'development') {
    console.group(`🔄 ${action.type}`);
    console.log('Previous State:', store.getState());
    console.log('Action:', action);

    const result = next(action);

    console.log('Next State:', store.getState());
    console.groupEnd();

    return result;
  }

  return next(action);
};
```

### Redux DevTools Commands
```typescript
// src/utils/reduxDebug.ts
export const reduxDebug = {
  // Jump to specific state
  jumpToState: (stateIndex: number) => {
    if (window.__REDUX_DEVTOOLS_EXTENSION__) {
      window.__REDUX_DEVTOOLS_EXTENSION__.send(
        { type: 'JUMP_TO_STATE', index: stateIndex },
        {}
      );
    }
  },

  // Import/Export state
  exportState: () => {
    const state = store.getState();
    const blob = new Blob([JSON.stringify(state, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `redux-state-${Date.now()}.json`;
    a.click();
  },

  importState: (stateJson: string) => {
    try {
      const state = JSON.parse(stateJson);
      store.dispatch({ type: 'DEBUG/IMPORT_STATE', payload: state });
    } catch (error) {
      console.error('Failed to import state:', error);
    }
  },

  // Log specific slice
  logSlice: (sliceName: keyof RootState) => {
    const state = store.getState();
    console.log(`🗂️ ${sliceName} slice:`, state[sliceName]);
  },

  // Monitor specific actions
  monitorActions: (actionTypes: string[]) => {
    const unsubscribe = store.subscribe(() => {
      const action = store.getState()._lastAction;
      if (action && actionTypes.includes(action.type)) {
        console.log(`🎯 Monitored action: ${action.type}`, action);
      }
    });
    return unsubscribe;
  },
};
```

## 🌐 Network Debugging

### API Request Interceptor
```typescript
// src/utils/networkDebug.ts
export class NetworkDebugger {
  private requests: Map<string, any> = new Map();

  interceptRequests() {
    if (process.env.NODE_ENV !== 'development') return;

    // Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const [url, config] = args;
      const requestId = this.generateRequestId();

      console.group(`🔄 API Request: ${config?.method || 'GET'} ${url}`);
      console.log('Request ID:', requestId);
      console.log('Headers:', config?.headers);
      console.log('Body:', config?.body);
      console.groupEnd();

      const startTime = performance.now();

      try {
        const response = await originalFetch(...args);
        const duration = performance.now() - startTime;

        const clonedResponse = response.clone();
        const responseData = await clonedResponse.json().catch(() => null);

        console.group(`✅ API Response: ${config?.method || 'GET'} ${url}`);
        console.log('Status:', response.status);
        console.log('Duration:', `${duration.toFixed(2)}ms`);
        console.log('Data:', responseData);
        console.groupEnd();

        this.requests.set(requestId, {
          url,
          method: config?.method || 'GET',
          status: response.status,
          duration,
          timestamp: new Date(),
          request: config,
          response: responseData,
        });

        return response;
      } catch (error) {
        const duration = performance.now() - startTime;

        console.group(`❌ API Error: ${config?.method || 'GET'} ${url}`);
        console.error('Error:', error);
        console.log('Duration:', `${duration.toFixed(2)}ms`);
        console.groupEnd();

        throw error;
      }
    };

    // Intercept XMLHttpRequest
    const originalXHROpen = XMLHttpRequest.prototype.open;
    const originalXHRSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(method, url, ...args) {
      this._debugInfo = { method, url, startTime: 0 };
      return originalXHROpen.apply(this, [method, url, ...args]);
    };

    XMLHttpRequest.prototype.send = function(body) {
      if (this._debugInfo) {
        this._debugInfo.startTime = performance.now();
        this._debugInfo.body = body;

        console.log(`🔄 XHR Request: ${this._debugInfo.method} ${this._debugInfo.url}`, body);

        this.addEventListener('load', () => {
          const duration = performance.now() - this._debugInfo.startTime;
          console.log(`✅ XHR Response: ${this._debugInfo.method} ${this._debugInfo.url}`, {
            status: this.status,
            duration: `${duration.toFixed(2)}ms`,
            response: this.responseText,
          });
        });
      }

      return originalXHRSend.apply(this, [body]);
    };
  }

  private generateRequestId(): string {
    return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  getRequests() {
    return Array.from(this.requests.values());
  }

  clearRequests() {
    this.requests.clear();
  }

  exportHAR() {
    // Export requests in HAR format for analysis
    const har = {
      log: {
        version: '1.2',
        creator: {
          name: 'Kailash Network Debugger',
          version: '1.0',
        },
        entries: this.getRequests().map(req => ({
          startedDateTime: req.timestamp.toISOString(),
          time: req.duration,
          request: {
            method: req.method,
            url: req.url,
            headers: req.request?.headers || [],
            postData: req.request?.body,
          },
          response: {
            status: req.status,
            content: {
              text: JSON.stringify(req.response),
              mimeType: 'application/json',
            },
          },
        })),
      },
    };

    const blob = new Blob([JSON.stringify(har, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `network-log-${Date.now()}.har`;
    a.click();
  }
}

// Initialize network debugger
const networkDebugger = new NetworkDebugger();
networkDebugger.interceptRequests();

// Expose to window for console access
if (process.env.NODE_ENV === 'development') {
  window.networkDebugger = networkDebugger;
}
```

### GraphQL Debugging
```typescript
// src/utils/graphqlDebug.ts
import { ApolloLink } from '@apollo/client';

export const debugLink = new ApolloLink((operation, forward) => {
  if (process.env.NODE_ENV === 'development') {
    const startTime = performance.now();

    console.group(`🚀 GraphQL ${operation.operationName}`);
    console.log('Query:', operation.query.loc?.source.body);
    console.log('Variables:', operation.variables);
    console.groupEnd();

    return forward(operation).map(response => {
      const duration = performance.now() - startTime;

      console.group(`✅ GraphQL Response ${operation.operationName}`);
      console.log('Duration:', `${duration.toFixed(2)}ms`);
      console.log('Data:', response.data);
      if (response.errors) {
        console.error('Errors:', response.errors);
      }
      console.groupEnd();

      return response;
    });
  }

  return forward(operation);
});
```

## 🎯 State Debugging

### React Query DevTools
```typescript
// src/App.tsx
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

export const App: React.FC = () => {
  return (
    <>
      <Router>
        {/* Your app */}
      </Router>
      {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools
          initialIsOpen={false}
          position="bottom-right"
          toggleButtonProps={{
            style: {
              marginLeft: '5rem',
              marginBottom: '2rem',
            },
          }}
        />
      )}
    </>
  );
};

// Custom query debugging
export const useDebugQuery = <TData, TError = unknown>(
  queryKey: any[],
  queryFn: () => Promise<TData>,
  options?: UseQueryOptions<TData, TError>
) => {
  const query = useQuery(queryKey, queryFn, options);

  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      console.log(`🔍 Query Debug [${queryKey.join(', ')}]:`, {
        status: query.status,
        data: query.data,
        error: query.error,
        isFetching: query.isFetching,
        isStale: query.isStale,
      });
    }
  }, [query.status, query.data, query.error]);

  return query;
};
```

### Context Debugging
```typescript
// src/utils/contextDebug.tsx
export const createDebugContext = <T,>(
  name: string,
  defaultValue: T
): [React.Context<T>, React.FC<{ value: T; children: React.ReactNode }>] => {
  const Context = React.createContext<T>(defaultValue);

  if (process.env.NODE_ENV === 'development') {
    Context.displayName = name;
  }

  const Provider: React.FC<{ value: T; children: React.ReactNode }> = ({
    value,
    children,
  }) => {
    const previousValue = useRef(value);

    useEffect(() => {
      if (process.env.NODE_ENV === 'development') {
        console.group(`🔄 ${name} Context Update`);
        console.log('Previous:', previousValue.current);
        console.log('Current:', value);

        // Deep diff for objects
        if (typeof value === 'object' && value !== null) {
          const changes = getObjectDiff(previousValue.current, value);
          if (Object.keys(changes).length > 0) {
            console.log('Changes:', changes);
          }
        }

        console.groupEnd();
      }

      previousValue.current = value;
    }, [value]);

    return <Context.Provider value={value}>{children}</Context.Provider>;
  };

  return [Context, Provider];
};

// Usage
const [ThemeContext, ThemeProvider] = createDebugContext('Theme', {
  mode: 'light',
  primaryColor: '#3b82f6',
});
```

## 🐛 Error Debugging

### Enhanced Error Boundaries
```typescript
// src/components/ErrorBoundary/DebugErrorBoundary.tsx
interface ErrorInfo {
  componentStack: string;
  errorBoundary?: boolean;
  errorBoundaryFound?: boolean;
  errorBoundaryName?: string;
}

interface DebugErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorCount: number;
}

export class DebugErrorBoundary extends Component<
  { children: ReactNode; fallback?: ComponentType<any> },
  DebugErrorBoundaryState
> {
  state: DebugErrorBoundaryState = {
    hasError: false,
    error: null,
    errorInfo: null,
    errorCount: 0,
  };

  static getDerivedStateFromError(error: Error): Partial<DebugErrorBoundaryState> {
    return {
      hasError: true,
      error,
      errorCount: (prevState?.errorCount || 0) + 1,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console with styling
    console.group(
      '%c🚨 React Error Caught',
      'color: white; background: #e11d48; padding: 2px 6px; border-radius: 3px;'
    );
    console.error('Error:', error);
    console.error('Component Stack:', errorInfo.componentStack);
    console.log('Props:', this.props);
    console.log('Error Count:', this.state.errorCount);
    console.groupEnd();

    // Save error details
    this.setState({ errorInfo });

    // Log to error service in production
    if (process.env.NODE_ENV === 'production') {
      // Sentry.captureException(error, { contexts: { react: errorInfo } });
    }

    // Save to localStorage for persistence
    this.saveErrorToStorage(error, errorInfo);
  }

  saveErrorToStorage(error: Error, errorInfo: ErrorInfo) {
    const errorLog = {
      timestamp: new Date().toISOString(),
      error: {
        message: error.message,
        stack: error.stack,
      },
      errorInfo,
      url: window.location.href,
      userAgent: navigator.userAgent,
    };

    const existingErrors = JSON.parse(
      localStorage.getItem('debug_errors') || '[]'
    );
    existingErrors.push(errorLog);

    // Keep only last 10 errors
    if (existingErrors.length > 10) {
      existingErrors.shift();
    }

    localStorage.setItem('debug_errors', JSON.stringify(existingErrors));
  }

  render() {
    if (this.state.hasError && this.state.error) {
      if (process.env.NODE_ENV === 'development') {
        // Development error UI
        return (
          <div className="min-h-screen bg-red-50 p-8">
            <div className="max-w-4xl mx-auto">
              <div className="bg-white rounded-lg shadow-lg p-6">
                <h1 className="text-2xl font-bold text-red-600 mb-4">
                  🚨 Development Error
                </h1>

                <div className="mb-6">
                  <h2 className="text-lg font-semibold mb-2">Error Message</h2>
                  <pre className="bg-gray-100 p-4 rounded overflow-x-auto">
                    {this.state.error.message}
                  </pre>
                </div>

                <div className="mb-6">
                  <h2 className="text-lg font-semibold mb-2">Stack Trace</h2>
                  <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-sm">
                    {this.state.error.stack}
                  </pre>
                </div>

                <div className="mb-6">
                  <h2 className="text-lg font-semibold mb-2">Component Stack</h2>
                  <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-sm">
                    {this.state.errorInfo?.componentStack}
                  </pre>
                </div>

                <div className="flex gap-4">
                  <button
                    onClick={() => window.location.reload()}
                    className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                  >
                    Reload Page
                  </button>
                  <button
                    onClick={() => this.setState({ hasError: false })}
                    className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
                  >
                    Dismiss Error
                  </button>
                  <button
                    onClick={() => navigator.clipboard.writeText(this.state.error?.stack || '')}
                    className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
                  >
                    Copy Stack Trace
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      }

      // Production fallback
      const Fallback = this.props.fallback || DefaultErrorFallback;
      return <Fallback error={this.state.error} retry={() => this.setState({ hasError: false })} />;
    }

    return this.props.children;
  }
}
```

### Error Logging Service
```typescript
// src/services/errorLogger.ts
interface ErrorLog {
  message: string;
  stack?: string;
  source?: string;
  lineno?: number;
  colno?: number;
  timestamp: string;
  userAgent: string;
  url: string;
  componentStack?: string;
}

class ErrorLogger {
  private logs: ErrorLog[] = [];
  private maxLogs = 50;

  init() {
    if (process.env.NODE_ENV === 'development') {
      this.setupGlobalErrorHandlers();
      this.setupUnhandledRejectionHandler();
      this.exposeDebugMethods();
    }
  }

  private setupGlobalErrorHandlers() {
    window.addEventListener('error', (event) => {
      this.logError({
        message: event.message,
        source: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    });
  }

  private setupUnhandledRejectionHandler() {
    window.addEventListener('unhandledrejection', (event) => {
      this.logError({
        message: `Unhandled Promise Rejection: ${event.reason}`,
        stack: event.reason?.stack,
      });
    });
  }

  logError(error: Partial<ErrorLog>) {
    const errorLog: ErrorLog = {
      message: error.message || 'Unknown error',
      stack: error.stack,
      source: error.source,
      lineno: error.lineno,
      colno: error.colno,
      timestamp: new Date().toISOString(),
      userAgent: navigator.userAgent,
      url: window.location.href,
      componentStack: error.componentStack,
    };

    this.logs.push(errorLog);

    // Keep only recent logs
    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }

    // Console output with styling
    console.group(
      '%c🐛 Error Logged',
      'color: white; background: #ef4444; padding: 2px 6px; border-radius: 3px;'
    );
    console.error(errorLog);
    console.groupEnd();

    // Save to localStorage
    this.saveToStorage();
  }

  private saveToStorage() {
    try {
      localStorage.setItem('error_logs', JSON.stringify(this.logs));
    } catch (e) {
      console.error('Failed to save error logs:', e);
    }
  }

  private exposeDebugMethods() {
    if (typeof window !== 'undefined') {
      window.errorLogger = {
        getLogs: () => this.logs,
        clearLogs: () => {
          this.logs = [];
          localStorage.removeItem('error_logs');
        },
        exportLogs: () => this.exportLogs(),
        search: (query: string) => this.searchLogs(query),
      };
    }
  }

  private searchLogs(query: string): ErrorLog[] {
    return this.logs.filter(log =>
      log.message.toLowerCase().includes(query.toLowerCase()) ||
      log.stack?.toLowerCase().includes(query.toLowerCase())
    );
  }

  private exportLogs() {
    const blob = new Blob([JSON.stringify(this.logs, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `error-logs-${Date.now()}.json`;
    a.click();
  }
}

export const errorLogger = new ErrorLogger();
errorLogger.init();
```

## 🎭 Visual Debugging

### Visual Debug Overlay
```typescript
// src/components/DebugOverlay/DebugOverlay.tsx
export const DebugOverlay: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [tab, setTab] = useState<'state' | 'network' | 'performance'>('state');

  if (process.env.NODE_ENV !== 'development') {
    return null;
  }

  return (
    <>
      {/* Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-4 left-4 p-2 bg-blue-500 text-white rounded-full shadow-lg z-50"
        title="Toggle Debug Panel"
      >
        🐛
      </button>

      {/* Debug Panel */}
      {isOpen && (
        <div className="fixed bottom-0 left-0 right-0 h-96 bg-gray-900 text-white shadow-2xl z-40">
          {/* Tabs */}
          <div className="flex border-b border-gray-700">
            <button
              onClick={() => setTab('state')}
              className={`px-4 py-2 ${tab === 'state' ? 'bg-gray-800' : ''}`}
            >
              State
            </button>
            <button
              onClick={() => setTab('network')}
              className={`px-4 py-2 ${tab === 'network' ? 'bg-gray-800' : ''}`}
            >
              Network
            </button>
            <button
              onClick={() => setTab('performance')}
              className={`px-4 py-2 ${tab === 'performance' ? 'bg-gray-800' : ''}`}
            >
              Performance
            </button>
          </div>

          {/* Content */}
          <div className="p-4 overflow-auto h-full">
            {tab === 'state' && <StateDebugger />}
            {tab === 'network' && <NetworkDebugger />}
            {tab === 'performance' && <PerformanceDebugger />}
          </div>
        </div>
      )}
    </>
  );
};

// State debugger tab
const StateDebugger: React.FC = () => {
  const state = useAppSelector(state => state);

  return (
    <div>
      <h3 className="text-lg font-bold mb-2">Redux State</h3>
      <pre className="text-xs overflow-auto">
        {JSON.stringify(state, null, 2)}
      </pre>
    </div>
  );
};

// Network debugger tab
const NetworkDebugger: React.FC = () => {
  const requests = window.networkDebugger?.getRequests() || [];

  return (
    <div>
      <h3 className="text-lg font-bold mb-2">Network Requests</h3>
      <div className="space-y-2">
        {requests.map((req, index) => (
          <div key={index} className="bg-gray-800 p-2 rounded text-xs">
            <div className="flex justify-between">
              <span>{req.method} {req.url}</span>
              <span className={req.status < 400 ? 'text-green-400' : 'text-red-400'}>
                {req.status}
              </span>
            </div>
            <div className="text-gray-400">
              {req.duration.toFixed(2)}ms
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Performance debugger tab
const PerformanceDebugger: React.FC = () => {
  const [fps, setFps] = useState(0);

  useEffect(() => {
    let lastTime = performance.now();
    let frames = 0;

    const measureFPS = () => {
      frames++;
      const currentTime = performance.now();

      if (currentTime >= lastTime + 1000) {
        setFps(Math.round((frames * 1000) / (currentTime - lastTime)));
        frames = 0;
        lastTime = currentTime;
      }

      requestAnimationFrame(measureFPS);
    };

    measureFPS();
  }, []);

  return (
    <div>
      <h3 className="text-lg font-bold mb-2">Performance Metrics</h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-gray-400">FPS</div>
          <div className="text-2xl">{fps}</div>
        </div>
        <div>
          <div className="text-gray-400">Memory</div>
          <div className="text-2xl">
            {(performance as any).memory
              ? `${Math.round((performance as any).memory.usedJSHeapSize / 1048576)}MB`
              : 'N/A'}
          </div>
        </div>
      </div>
    </div>
  );
};
```

## 🛠️ VS Code Debugging

### Launch Configuration
```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "chrome",
      "request": "launch",
      "name": "Launch Chrome against localhost",
      "url": "http://localhost:3000",
      "webRoot": "${workspaceFolder}/src",
      "sourceMaps": true,
      "runtimeArgs": ["--disable-web-security"],
      "sourceMapPathOverrides": {
        "webpack:///src/*": "${webRoot}/*"
      }
    },
    {
      "type": "chrome",
      "request": "attach",
      "name": "Attach to Chrome",
      "port": 9222,
      "webRoot": "${workspaceFolder}/src",
      "sourceMaps": true
    },
    {
      "type": "node",
      "request": "launch",
      "name": "Jest Debug",
      "program": "${workspaceFolder}/node_modules/.bin/jest",
      "args": ["--runInBand", "--watchAll=false"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal",
      "internalConsoleOptions": "neverOpen"
    }
  ]
}
```

### Debugging Snippets
```json
// .vscode/snippets/debug.code-snippets
{
  "Debug Log": {
    "prefix": "dlog",
    "body": [
      "console.log('🔍 ${1:label}:', ${2:variable});"
    ],
    "description": "Console log with emoji"
  },
  "Debug Group": {
    "prefix": "dgroup",
    "body": [
      "console.group('🔍 ${1:Group Name}');",
      "${2:// logs}",
      "console.groupEnd();"
    ],
    "description": "Console group for debugging"
  },
  "Debug Breakpoint": {
    "prefix": "dbr",
    "body": [
      "debugger; // TODO: Remove before commit"
    ],
    "description": "Debugger statement"
  },
  "Performance Timer": {
    "prefix": "dperf",
    "body": [
      "console.time('${1:timer}');",
      "${2:// code to measure}",
      "console.timeEnd('${1:timer}');"
    ],
    "description": "Performance timing"
  }
}
```

## 🎯 Debugging Best Practices

### 1. Console Debugging
- Use descriptive labels and emojis for clarity
- Group related logs together
- Clean up console logs before committing
- Use conditional logging for production

### 2. Browser DevTools
- Master keyboard shortcuts
- Use conditional breakpoints
- Leverage the Network tab for API debugging
- Profile performance regularly

### 3. React DevTools
- Name your components properly
- Use the Profiler for performance issues
- Inspect component props and state
- Track unnecessary re-renders

### 4. Error Handling
- Implement comprehensive error boundaries
- Log errors with full context
- Use source maps in production
- Monitor errors in real-time

### 5. State Management
- Use Redux DevTools time-travel
- Export and import state for testing
- Monitor action dispatches
- Track state changes

### 6. Network Debugging
- Log all API requests in development
- Mock API responses for testing
- Monitor request performance
- Handle network failures gracefully

### 7. Performance
- Use React Profiler API
- Monitor FPS and memory usage
- Identify performance bottlenecks
- Optimize based on measurements
