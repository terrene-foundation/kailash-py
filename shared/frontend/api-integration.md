# API Integration Guide

This guide covers best practices for integrating frontend applications with the Kailash Python SDK backend services.

## 🌐 API Overview

### Available APIs
```typescript
// API Endpoints Structure
const KAILASH_APIS = {
  // Workflow Management
  workflows: {
    list: 'GET /api/workflows',
    get: 'GET /api/workflows/:id',
    create: 'POST /api/workflows',
    update: 'PUT /api/workflows/:id',
    delete: 'DELETE /api/workflows/:id',
    execute: 'POST /api/workflows/:id/execute',
    status: 'GET /api/workflows/:id/executions/:executionId',
  },

  // Gateway API
  gateway: {
    status: 'GET /api/gateway/status',
    routes: 'GET /api/gateway/routes',
    register: 'POST /api/gateway/routes',
  },

  // Node Management
  nodes: {
    list: 'GET /api/nodes',
    types: 'GET /api/nodes/types',
    validate: 'POST /api/nodes/validate',
  },

  // Real-time Updates
  websocket: {
    workflow: 'ws://localhost:8000/ws/workflow/:id',
    metrics: 'ws://localhost:8000/ws/metrics',
  },

  // MCP Integration
  mcp: {
    tools: 'GET /api/mcp/tools',
    resources: 'GET /api/mcp/resources',
    execute: 'POST /api/mcp/tools/:name/execute',
  },
};
```

## 🔧 HTTP Client Setup

### Axios Configuration
```typescript
// src/services/api/client.ts
import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import { toast } from 'react-toastify';

interface ApiError {
  message: string;
  code: string;
  details?: any;
}

class ApiClient {
  private client: AxiosInstance;
  private refreshPromise: Promise<string> | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add auth token
        const token = this.getAuthToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }

        // Add request ID for tracking
        config.headers['X-Request-ID'] = this.generateRequestId();

        // Log request in development
        if (process.env.NODE_ENV === 'development') {
          console.log(`🚀 ${config.method?.toUpperCase()} ${config.url}`, config.data);
        }

        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => {
        // Log response in development
        if (process.env.NODE_ENV === 'development') {
          console.log(`✅ ${response.config.method?.toUpperCase()} ${response.config.url}`, response.data);
        }
        return response;
      },
      async (error: AxiosError<ApiError>) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

        // Handle 401 - Token expired
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          try {
            const newToken = await this.refreshToken();
            originalRequest.headers!.Authorization = `Bearer ${newToken}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            this.handleAuthError();
            return Promise.reject(refreshError);
          }
        }

        // Handle other errors
        this.handleApiError(error);
        return Promise.reject(error);
      }
    );
  }

  private async refreshToken(): Promise<string> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.performTokenRefresh();
    }

    try {
      const token = await this.refreshPromise;
      return token;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async performTokenRefresh(): Promise<string> {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await this.client.post('/auth/refresh', { refreshToken });
    const { accessToken, refreshToken: newRefreshToken } = response.data;

    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', newRefreshToken);

    return accessToken;
  }

  private handleApiError(error: AxiosError<ApiError>) {
    if (error.response) {
      // Server responded with error
      const message = error.response.data?.message || 'An error occurred';
      const code = error.response.data?.code || 'UNKNOWN_ERROR';

      switch (error.response.status) {
        case 400:
          toast.error(`Bad Request: ${message}`);
          break;
        case 403:
          toast.error('Access denied. You don\'t have permission to perform this action.');
          break;
        case 404:
          toast.error('Resource not found.');
          break;
        case 429:
          toast.error('Too many requests. Please try again later.');
          break;
        case 500:
          toast.error('Server error. Please try again later.');
          break;
        default:
          toast.error(message);
      }

      // Log detailed error in development
      if (process.env.NODE_ENV === 'development') {
        console.error('API Error:', {
          status: error.response.status,
          code,
          message,
          details: error.response.data?.details,
        });
      }
    } else if (error.request) {
      // Request made but no response
      toast.error('Network error. Please check your connection.');
    } else {
      // Something else happened
      toast.error('An unexpected error occurred.');
    }
  }

  private handleAuthError() {
    // Clear auth data
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');

    // Redirect to login
    window.location.href = '/login';
  }

  private getAuthToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private generateRequestId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  // Public methods
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }

  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.put<T>(url, data, config);
    return response.data;
  }

  async patch<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.patch<T>(url, data, config);
    return response.data;
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config);
    return response.data;
  }

  // File upload
  async upload<T>(url: string, file: File, onProgress?: (progress: number) => void): Promise<T> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post<T>(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(progress);
        }
      },
    });

    return response.data;
  }
}

export const apiClient = new ApiClient();
```

## 📡 Service Layer Implementation

### Workflow Service
```typescript
// src/services/api/workflow.service.ts
import { apiClient } from './client';
import type { Workflow, WorkflowExecution, CreateWorkflowDto, UpdateWorkflowDto } from '@/types';

export class WorkflowService {
  async listWorkflows(params?: {
    page?: number;
    limit?: number;
    search?: string;
    tags?: string[];
  }): Promise<{ data: Workflow[]; total: number; page: number; limit: number }> {
    return apiClient.get('/api/workflows', { params });
  }

  async getWorkflow(id: string): Promise<Workflow> {
    return apiClient.get(`/api/workflows/${id}`);
  }

  async createWorkflow(data: CreateWorkflowDto): Promise<Workflow> {
    return apiClient.post('/api/workflows', data);
  }

  async updateWorkflow(id: string, data: UpdateWorkflowDto): Promise<Workflow> {
    return apiClient.put(`/api/workflows/${id}`, data);
  }

  async deleteWorkflow(id: string): Promise<void> {
    return apiClient.delete(`/api/workflows/${id}`);
  }

  async duplicateWorkflow(id: string, name: string): Promise<Workflow> {
    return apiClient.post(`/api/workflows/${id}/duplicate`, { name });
  }

  async executeWorkflow(
    id: string,
    parameters: Record<string, any>
  ): Promise<WorkflowExecution> {
    return apiClient.post(`/api/workflows/${id}/execute`, { parameters });
  }

  async getExecutionStatus(workflowId: string, executionId: string): Promise<WorkflowExecution> {
    return apiClient.get(`/api/workflows/${workflowId}/executions/${executionId}`);
  }

  async listExecutions(
    workflowId: string,
    params?: { page?: number; limit?: number; status?: string }
  ): Promise<{ data: WorkflowExecution[]; total: number }> {
    return apiClient.get(`/api/workflows/${workflowId}/executions`, { params });
  }

  async cancelExecution(workflowId: string, executionId: string): Promise<void> {
    return apiClient.post(`/api/workflows/${workflowId}/executions/${executionId}/cancel`);
  }

  async exportWorkflow(id: string, format: 'yaml' | 'json' = 'yaml'): Promise<Blob> {
    const response = await apiClient.get(`/api/workflows/${id}/export`, {
      params: { format },
      responseType: 'blob',
    });
    return response as unknown as Blob;
  }

  async importWorkflow(file: File): Promise<Workflow> {
    return apiClient.upload('/api/workflows/import', file);
  }

  async validateWorkflow(workflow: Partial<Workflow>): Promise<{
    valid: boolean;
    errors: Array<{ field: string; message: string }>;
  }> {
    return apiClient.post('/api/workflows/validate', workflow);
  }
}

export const workflowService = new WorkflowService();
```

### Node Service
```typescript
// src/services/api/node.service.ts
export class NodeService {
  async getNodeTypes(): Promise<NodeType[]> {
    return apiClient.get('/api/nodes/types');
  }

  async getNodeSchema(type: string): Promise<NodeSchema> {
    return apiClient.get(`/api/nodes/types/${type}/schema`);
  }

  async validateNodeConfig(type: string, config: any): Promise<ValidationResult> {
    return apiClient.post('/api/nodes/validate', { type, config });
  }

  async getNodeDocumentation(type: string): Promise<NodeDocumentation> {
    return apiClient.get(`/api/nodes/types/${type}/docs`);
  }

  async searchNodes(query: string): Promise<NodeType[]> {
    return apiClient.get('/api/nodes/search', { params: { q: query } });
  }
}

export const nodeService = new NodeService();
```

## 🔄 React Query Integration

### Query Client Setup
```typescript
// src/lib/react-query.ts
import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query';
import { toast } from 'react-toastify';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      cacheTime: 1000 * 60 * 10, // 10 minutes
      retry: (failureCount, error: any) => {
        // Don't retry on 4xx errors
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        return failureCount < 3;
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
  queryCache: new QueryCache({
    onError: (error: any) => {
      if (error?.response?.status !== 401) {
        toast.error(error?.message || 'An error occurred');
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error: any) => {
      if (error?.response?.status !== 401) {
        toast.error(error?.message || 'An error occurred');
      }
    },
  }),
});
```

### Query Hooks
```typescript
// src/hooks/queries/useWorkflows.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workflowService } from '@/services/api/workflow.service';

// Query keys factory
export const workflowKeys = {
  all: ['workflows'] as const,
  lists: () => [...workflowKeys.all, 'list'] as const,
  list: (params?: any) => [...workflowKeys.lists(), params] as const,
  details: () => [...workflowKeys.all, 'detail'] as const,
  detail: (id: string) => [...workflowKeys.details(), id] as const,
  executions: (id: string) => [...workflowKeys.detail(id), 'executions'] as const,
};

// List workflows
export const useWorkflows = (params?: {
  page?: number;
  limit?: number;
  search?: string;
}) => {
  return useQuery({
    queryKey: workflowKeys.list(params),
    queryFn: () => workflowService.listWorkflows(params),
    keepPreviousData: true, // For pagination
  });
};

// Get single workflow
export const useWorkflow = (id: string, enabled = true) => {
  return useQuery({
    queryKey: workflowKeys.detail(id),
    queryFn: () => workflowService.getWorkflow(id),
    enabled: enabled && !!id,
  });
};

// Create workflow
export const useCreateWorkflow = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: workflowService.createWorkflow,
    onSuccess: (data) => {
      // Invalidate list queries
      queryClient.invalidateQueries(workflowKeys.lists());

      // Optionally set the new workflow in cache
      queryClient.setQueryData(workflowKeys.detail(data.id), data);

      toast.success('Workflow created successfully');
    },
  });
};

// Update workflow
export const useUpdateWorkflow = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateWorkflowDto }) =>
      workflowService.updateWorkflow(id, data),
    onMutate: async ({ id, data }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries(workflowKeys.detail(id));

      // Snapshot previous value
      const previousWorkflow = queryClient.getQueryData(workflowKeys.detail(id));

      // Optimistically update
      queryClient.setQueryData(workflowKeys.detail(id), (old: any) => ({
        ...old,
        ...data,
      }));

      return { previousWorkflow };
    },
    onError: (err, variables, context) => {
      // Rollback on error
      if (context?.previousWorkflow) {
        queryClient.setQueryData(
          workflowKeys.detail(variables.id),
          context.previousWorkflow
        );
      }
    },
    onSettled: (data, error, variables) => {
      // Refetch after error or success
      queryClient.invalidateQueries(workflowKeys.detail(variables.id));
      queryClient.invalidateQueries(workflowKeys.lists());
    },
    onSuccess: () => {
      toast.success('Workflow updated successfully');
    },
  });
};

// Execute workflow
export const useExecuteWorkflow = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, parameters }: { id: string; parameters: any }) =>
      workflowService.executeWorkflow(id, parameters),
    onSuccess: (data, variables) => {
      // Invalidate executions list
      queryClient.invalidateQueries(workflowKeys.executions(variables.id));

      toast.success('Workflow execution started');
    },
  });
};

// Workflow execution status with polling
export const useExecutionStatus = (
  workflowId: string,
  executionId: string,
  options?: { enabled?: boolean; refetchInterval?: number }
) => {
  return useQuery({
    queryKey: ['execution', workflowId, executionId],
    queryFn: () => workflowService.getExecutionStatus(workflowId, executionId),
    enabled: options?.enabled ?? true,
    refetchInterval: (data) => {
      // Poll while execution is running
      if (data?.status === 'running') {
        return options?.refetchInterval ?? 1000;
      }
      return false;
    },
  });
};
```

## 🔌 WebSocket Integration

### WebSocket Manager
```typescript
// src/services/websocket/WebSocketManager.ts
import { EventEmitter } from 'events';

interface WebSocketMessage {
  type: string;
  payload: any;
  timestamp: number;
}

export class WebSocketManager extends EventEmitter {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: NodeJS.Timeout | null = null;

  constructor(url: string) {
    super();
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      this.ws = new WebSocket(this.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('WebSocket connection error:', error);
      this.scheduleReconnect();
    }
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.emit('connected');
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.emit('error', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.emit('disconnected');
      this.stopHeartbeat();
      this.scheduleReconnect();
    };
  }

  private handleMessage(message: WebSocketMessage): void {
    // Handle heartbeat
    if (message.type === 'pong') {
      return;
    }

    // Emit typed events
    this.emit(message.type, message.payload);

    // Emit generic message event
    this.emit('message', message);
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send('ping', {});
    }, 30000); // 30 seconds
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('reconnectFailed');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  send(type: string, payload: any): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.error('WebSocket is not connected');
      return;
    }

    const message: WebSocketMessage = {
      type,
      payload,
      timestamp: Date.now(),
    };

    this.ws.send(JSON.stringify(message));
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
```

### WebSocket React Hook
```typescript
// src/hooks/useWebSocket.ts
import { useEffect, useRef, useState } from 'react';
import { WebSocketManager } from '@/services/websocket/WebSocketManager';

interface UseWebSocketOptions {
  onMessage?: (type: string, payload: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: any) => void;
  autoConnect?: boolean;
}

export const useWebSocket = (url: string, options: UseWebSocketOptions = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocketManager | null>(null);

  useEffect(() => {
    const ws = new WebSocketManager(url);
    wsRef.current = ws;

    // Setup event handlers
    ws.on('connected', () => {
      setIsConnected(true);
      options.onConnect?.();
    });

    ws.on('disconnected', () => {
      setIsConnected(false);
      options.onDisconnect?.();
    });

    ws.on('error', (error) => {
      options.onError?.(error);
    });

    ws.on('message', (message) => {
      options.onMessage?.(message.type, message.payload);
    });

    // Auto-connect if enabled
    if (options.autoConnect !== false) {
      ws.connect();
    }

    return () => {
      ws.disconnect();
      ws.removeAllListeners();
    };
  }, [url]);

  const send = (type: string, payload: any) => {
    wsRef.current?.send(type, payload);
  };

  const connect = () => {
    wsRef.current?.connect();
  };

  const disconnect = () => {
    wsRef.current?.disconnect();
  };

  return {
    isConnected,
    send,
    connect,
    disconnect,
  };
};

// Usage example
export const useWorkflowUpdates = (workflowId: string) => {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string>('idle');

  const { isConnected } = useWebSocket(
    `ws://localhost:8000/ws/workflow/${workflowId}`,
    {
      onMessage: (type, payload) => {
        switch (type) {
          case 'execution.started':
            setStatus('running');
            break;

          case 'node.completed':
            // Update specific node status
            queryClient.setQueryData(
              ['workflow', workflowId],
              (old: any) => {
                // Update node status in workflow
                return updateNodeStatus(old, payload.nodeId, 'completed');
              }
            );
            break;

          case 'execution.completed':
            setStatus('completed');
            // Invalidate to fetch final results
            queryClient.invalidateQueries(['workflow', workflowId]);
            break;

          case 'execution.failed':
            setStatus('failed');
            toast.error(`Execution failed: ${payload.error}`);
            break;
        }
      },
    }
  );

  return { isConnected, status };
};
```

## 🔐 Authentication & Authorization

### Auth Context
```typescript
// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '@/services/api/auth.service';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  updateProfile: (data: UpdateProfileData) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check for existing session
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setIsLoading(false);
        return;
      }

      const user = await authService.getCurrentUser();
      setUser(user);
    } catch (error) {
      console.error('Auth check failed:', error);
      localStorage.removeItem('access_token');
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (credentials: LoginCredentials) => {
    const { user, tokens } = await authService.login(credentials);

    localStorage.setItem('access_token', tokens.access);
    localStorage.setItem('refresh_token', tokens.refresh);

    setUser(user);
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
    }
  };

  const register = async (data: RegisterData) => {
    const { user, tokens } = await authService.register(data);

    localStorage.setItem('access_token', tokens.access);
    localStorage.setItem('refresh_token', tokens.refresh);

    setUser(user);
  };

  const updateProfile = async (data: UpdateProfileData) => {
    const updatedUser = await authService.updateProfile(data);
    setUser(updatedUser);
  };

  const value: AuthContextValue = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    register,
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
```

### Protected API Calls
```typescript
// src/hooks/useProtectedQuery.ts
export const useProtectedQuery = <TData>(
  queryKey: any[],
  queryFn: () => Promise<TData>,
  options?: UseQueryOptions<TData>
) => {
  const { isAuthenticated } = useAuth();

  return useQuery({
    queryKey,
    queryFn,
    enabled: isAuthenticated && (options?.enabled ?? true),
    ...options,
  });
};
```

## 📊 Data Fetching Patterns

### Pagination
```typescript
// src/hooks/usePagination.ts
interface PaginationParams {
  page: number;
  limit: number;
  sort?: string;
  order?: 'asc' | 'desc';
}

export const usePaginatedWorkflows = (initialParams?: Partial<PaginationParams>) => {
  const [params, setParams] = useState<PaginationParams>({
    page: 1,
    limit: 20,
    sort: 'createdAt',
    order: 'desc',
    ...initialParams,
  });

  const query = useQuery({
    queryKey: ['workflows', 'paginated', params],
    queryFn: () => workflowService.listWorkflows(params),
    keepPreviousData: true,
  });

  const goToPage = (page: number) => {
    setParams((prev) => ({ ...prev, page }));
  };

  const setPageSize = (limit: number) => {
    setParams((prev) => ({ ...prev, limit, page: 1 }));
  };

  const setSorting = (sort: string, order?: 'asc' | 'desc') => {
    setParams((prev) => ({
      ...prev,
      sort,
      order: order || prev.order,
      page: 1,
    }));
  };

  return {
    ...query,
    params,
    goToPage,
    setPageSize,
    setSorting,
    hasNextPage: query.data ? params.page * params.limit < query.data.total : false,
    hasPreviousPage: params.page > 1,
  };
};
```

### Infinite Scroll
```typescript
// src/hooks/useInfiniteWorkflows.ts
export const useInfiniteWorkflows = (search?: string) => {
  return useInfiniteQuery({
    queryKey: ['workflows', 'infinite', search],
    queryFn: ({ pageParam = 1 }) =>
      workflowService.listWorkflows({
        page: pageParam,
        limit: 20,
        search,
      }),
    getNextPageParam: (lastPage, pages) => {
      const totalLoaded = pages.length * 20;
      if (totalLoaded < lastPage.total) {
        return pages.length + 1;
      }
      return undefined;
    },
  });
};

// Usage in component
export const WorkflowInfiniteList: React.FC = () => {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteWorkflows();

  const { ref, inView } = useInView();

  useEffect(() => {
    if (inView && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [inView, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div>
      {data?.pages.map((page, pageIndex) => (
        <React.Fragment key={pageIndex}>
          {page.data.map((workflow) => (
            <WorkflowCard key={workflow.id} workflow={workflow} />
          ))}
        </React.Fragment>
      ))}

      <div ref={ref} className="h-10">
        {isFetchingNextPage && <Spinner />}
      </div>
    </div>
  );
};
```

## 🔄 Optimistic Updates

### Optimistic Workflow Updates
```typescript
// src/hooks/useOptimisticWorkflowUpdate.ts
export const useOptimisticWorkflowUpdate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<Workflow> }) =>
      workflowService.updateWorkflow(id, updates),

    onMutate: async ({ id, updates }) => {
      // Cancel in-flight queries
      await queryClient.cancelQueries(['workflow', id]);

      // Snapshot previous value
      const previousWorkflow = queryClient.getQueryData<Workflow>(['workflow', id]);

      // Optimistically update
      if (previousWorkflow) {
        queryClient.setQueryData(['workflow', id], {
          ...previousWorkflow,
          ...updates,
          updatedAt: new Date().toISOString(),
        });
      }

      // Also update in list view if present
      queryClient.setQueriesData(
        { queryKey: ['workflows'], exact: false },
        (old: any) => {
          if (!old?.data) return old;

          return {
            ...old,
            data: old.data.map((w: Workflow) =>
              w.id === id ? { ...w, ...updates } : w
            ),
          };
        }
      );

      return { previousWorkflow };
    },

    onError: (err, variables, context) => {
      // Rollback on error
      if (context?.previousWorkflow) {
        queryClient.setQueryData(['workflow', variables.id], context.previousWorkflow);
      }

      // Also rollback list views
      queryClient.invalidateQueries(['workflows']);
    },

    onSettled: () => {
      // Always refetch after mutation
      queryClient.invalidateQueries(['workflows']);
    },
  });
};
```

## 🚨 Error Handling

### Global Error Handler
```typescript
// src/components/ErrorBoundary/ApiErrorBoundary.tsx
interface ApiErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ApiErrorBoundary extends Component<
  { children: ReactNode; fallback?: ComponentType<{ error: Error; reset: () => void }> },
  ApiErrorBoundaryState
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<ApiErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('API Error caught by boundary:', error, errorInfo);

    // Log to error tracking service
    if (process.env.NODE_ENV === 'production') {
      // Sentry.captureException(error);
    }

    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      const Fallback = this.props.fallback || DefaultApiErrorFallback;
      return <Fallback error={this.state.error} reset={this.handleReset} />;
    }

    return this.props.children;
  }
}

const DefaultApiErrorFallback: React.FC<{ error: Error; reset: () => void }> = ({
  error,
  reset,
}) => {
  const isApiError = error.message.includes('API') || error.message.includes('Network');

  return (
    <div className="min-h-screen flex items-center justify-center">
      <Card className="max-w-md w-full">
        <Card.Body>
          <div className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">
              {isApiError ? 'Connection Error' : 'Something went wrong'}
            </h2>
            <p className="text-gray-600 mb-6">
              {isApiError
                ? 'Unable to connect to the server. Please check your connection and try again.'
                : error.message}
            </p>
            <div className="space-x-4">
              <Button onClick={reset}>Try Again</Button>
              <Button variant="outline" onClick={() => window.location.href = '/'}>
                Go Home
              </Button>
            </div>
          </div>
        </Card.Body>
      </Card>
    </div>
  );
};
```

## 🎯 Best Practices

### 1. API Client Patterns
- Use a centralized API client with interceptors
- Implement automatic token refresh
- Add request/response logging in development
- Handle errors consistently

### 2. Data Fetching
- Use React Query for server state management
- Implement proper caching strategies
- Use optimistic updates for better UX
- Handle loading and error states

### 3. WebSocket Management
- Implement automatic reconnection
- Use heartbeat for connection monitoring
- Handle connection state in UI
- Clean up connections on unmount

### 4. Type Safety
- Generate types from API schemas
- Use strict typing for all API calls
- Validate responses at runtime
- Document expected API contracts

### 5. Performance
- Implement request debouncing
- Use pagination for large datasets
- Cache frequently accessed data
- Minimize unnecessary API calls

### 6. Security
- Store tokens securely
- Implement CSRF protection
- Validate all inputs
- Use HTTPS in production
