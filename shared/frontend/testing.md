# Frontend Testing Guidelines

This guide covers comprehensive testing strategies for Kailash frontend applications, including unit tests, integration tests, and end-to-end tests.

## 🧪 Testing Overview

### Testing Pyramid
```
         /\
        /E2E\      <- End-to-End Tests (Few)
       /______\
      /        \
     /Integration\  <- Integration Tests (Some)
    /______________\
   /                \
  /   Unit Tests     \ <- Unit Tests (Many)
 /____________________\
```

### Testing Stack
```json
{
  "unit": "Jest + React Testing Library",
  "integration": "Jest + MSW (Mock Service Worker)",
  "e2e": "Playwright or Cypress",
  "visual": "Storybook + Chromatic",
  "performance": "Lighthouse CI",
  "accessibility": "jest-axe + Pa11y"
}
```

## 🔬 Unit Testing

### Test Setup
```typescript
// jest.config.js
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/src/test/setup.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
    '\\.(jpg|jpeg|png|gif|svg)$': '<rootDir>/src/test/__mocks__/fileMock.js',
  },
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.{ts,tsx}',
    '!src/test/**',
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
};

// src/test/setup.ts
import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { server } from './mocks/server';

// Establish API mocking before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset any request handlers that we may add during the tests
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// Clean up after the tests are finished
afterAll(() => server.close());

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
} as any;

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});
```

### Component Testing
```typescript
// src/components/Button/Button.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>);

    const button = screen.getByRole('button', { name: /click me/i });
    expect(button).toBeInTheDocument();
  });

  it('handles click events', async () => {
    const handleClick = jest.fn();
    const user = userEvent.setup();

    render(<Button onClick={handleClick}>Click me</Button>);

    const button = screen.getByRole('button', { name: /click me/i });
    await user.click(button);

    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('shows loading state', () => {
    render(<Button loading>Loading</Button>);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  it('applies variant styles', () => {
    const { rerender } = render(<Button variant="primary">Primary</Button>);

    let button = screen.getByRole('button');
    expect(button).toHaveClass('btn-primary');

    rerender(<Button variant="danger">Danger</Button>);

    button = screen.getByRole('button');
    expect(button).toHaveClass('btn-danger');
  });

  it('forwards ref', () => {
    const ref = React.createRef<HTMLButtonElement>();
    render(<Button ref={ref}>Button</Button>);

    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });

  describe('accessibility', () => {
    it('has proper ARIA attributes when disabled', () => {
      render(<Button disabled>Disabled</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-disabled', 'true');
    });

    it('supports keyboard navigation', async () => {
      const handleClick = jest.fn();
      const user = userEvent.setup();

      render(<Button onClick={handleClick}>Keyboard</Button>);

      const button = screen.getByRole('button');
      button.focus();

      await user.keyboard('{Enter}');
      expect(handleClick).toHaveBeenCalledTimes(1);

      await user.keyboard(' ');
      expect(handleClick).toHaveBeenCalledTimes(2);
    });
  });
});
```

### Hook Testing
```typescript
// src/hooks/useDebounce.test.ts
import { renderHook, act } from '@testing-library/react';
import { useDebounce } from './useDebounce';

describe('useDebounce', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('initial', 500));

    expect(result.current).toBe('initial');
  });

  it('debounces value changes', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'initial', delay: 500 } }
    );

    expect(result.current).toBe('initial');

    // Change value
    rerender({ value: 'updated', delay: 500 });

    // Value shouldn't change immediately
    expect(result.current).toBe('initial');

    // Fast-forward time
    act(() => {
      jest.advanceTimersByTime(500);
    });

    // Now value should be updated
    expect(result.current).toBe('updated');
  });

  it('cancels previous timeout on rapid changes', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 500),
      { initialProps: { value: 'first' } }
    );

    rerender({ value: 'second' });

    act(() => {
      jest.advanceTimersByTime(300);
    });

    rerender({ value: 'third' });

    act(() => {
      jest.advanceTimersByTime(300);
    });

    // Only 600ms passed, but last change was 300ms ago
    expect(result.current).toBe('first');

    act(() => {
      jest.advanceTimersByTime(200);
    });

    // Now 500ms passed since last change
    expect(result.current).toBe('third');
  });
});

// src/hooks/useLocalStorage.test.ts
import { renderHook, act } from '@testing-library/react';
import { useLocalStorage } from './useLocalStorage';

describe('useLocalStorage', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it('initializes with default value', () => {
    const { result } = renderHook(() =>
      useLocalStorage('testKey', 'defaultValue')
    );

    const [value] = result.current;
    expect(value).toBe('defaultValue');
  });

  it('initializes with stored value', () => {
    localStorage.setItem('testKey', JSON.stringify('storedValue'));

    const { result } = renderHook(() =>
      useLocalStorage('testKey', 'defaultValue')
    );

    const [value] = result.current;
    expect(value).toBe('storedValue');
  });

  it('updates localStorage when value changes', () => {
    const { result } = renderHook(() =>
      useLocalStorage('testKey', 'initial')
    );

    const [, setValue] = result.current;

    act(() => {
      setValue('updated');
    });

    expect(localStorage.getItem('testKey')).toBe('"updated"');
    expect(result.current[0]).toBe('updated');
  });

  it('handles function updates', () => {
    const { result } = renderHook(() =>
      useLocalStorage('counter', 0)
    );

    const [, setValue] = result.current;

    act(() => {
      setValue((prev) => prev + 1);
    });

    expect(result.current[0]).toBe(1);
  });

  it('handles errors gracefully', () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

    // Mock localStorage to throw error
    const mockSetItem = jest.fn(() => {
      throw new Error('Storage full');
    });
    Object.defineProperty(window, 'localStorage', {
      value: {
        setItem: mockSetItem,
        getItem: jest.fn(() => null),
      },
      writable: true,
    });

    const { result } = renderHook(() =>
      useLocalStorage('testKey', 'value')
    );

    const [, setValue] = result.current;

    act(() => {
      setValue('newValue');
    });

    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});
```

### Redux Testing
```typescript
// src/store/slices/workflowSlice.test.ts
import { configureStore } from '@reduxjs/toolkit';
import workflowReducer, {
  addNode,
  updateNode,
  removeNode,
  fetchWorkflow,
} from './workflowSlice';
import { workflowAPI } from '@/services/api';

// Mock API
jest.mock('@/services/api');

describe('workflowSlice', () => {
  let store: ReturnType<typeof configureStore>;

  beforeEach(() => {
    store = configureStore({
      reducer: {
        workflow: workflowReducer,
      },
    });
  });

  describe('synchronous actions', () => {
    it('adds a node', () => {
      const node = {
        id: 'node-1',
        type: 'DataReader',
        name: 'CSV Reader',
        config: {},
      };

      store.dispatch(addNode({ workflowId: 'wf-1', node }));

      const state = store.getState().workflow;
      expect(state.workflows['wf-1'].nodes).toContainEqual(node);
    });

    it('updates a node', () => {
      // First add a workflow with a node
      const initialState = {
        workflows: {
          'wf-1': {
            id: 'wf-1',
            name: 'Test Workflow',
            nodes: [
              { id: 'node-1', type: 'DataReader', name: 'Old Name', config: {} },
            ],
            connections: [],
          },
        },
      };

      store = configureStore({
        reducer: {
          workflow: workflowReducer,
        },
        preloadedState: { workflow: initialState },
      });

      store.dispatch(updateNode({
        workflowId: 'wf-1',
        nodeId: 'node-1',
        updates: { name: 'New Name' },
      }));

      const state = store.getState().workflow;
      const updatedNode = state.workflows['wf-1'].nodes.find(n => n.id === 'node-1');
      expect(updatedNode?.name).toBe('New Name');
    });

    it('removes a node and its connections', () => {
      const initialState = {
        workflows: {
          'wf-1': {
            id: 'wf-1',
            name: 'Test Workflow',
            nodes: [
              { id: 'node-1', type: 'DataReader', name: 'Node 1', config: {} },
              { id: 'node-2', type: 'Transform', name: 'Node 2', config: {} },
            ],
            connections: [
              { from: 'node-1', to: 'node-2' },
            ],
          },
        },
      };

      store = configureStore({
        reducer: {
          workflow: workflowReducer,
        },
        preloadedState: { workflow: initialState },
      });

      store.dispatch(removeNode({ workflowId: 'wf-1', nodeId: 'node-1' }));

      const state = store.getState().workflow;
      expect(state.workflows['wf-1'].nodes).toHaveLength(1);
      expect(state.workflows['wf-1'].connections).toHaveLength(0);
    });
  });

  describe('async actions', () => {
    it('handles fetchWorkflow.pending', () => {
      store.dispatch(fetchWorkflow.pending('', 'wf-1'));

      const state = store.getState().workflow;
      expect(state.isLoading).toBe(true);
      expect(state.error).toBe(null);
    });

    it('handles fetchWorkflow.fulfilled', () => {
      const workflow = {
        id: 'wf-1',
        name: 'Fetched Workflow',
        nodes: [],
        connections: [],
      };

      store.dispatch(fetchWorkflow.fulfilled(workflow, '', 'wf-1'));

      const state = store.getState().workflow;
      expect(state.isLoading).toBe(false);
      expect(state.workflows['wf-1']).toEqual(workflow);
    });

    it('handles fetchWorkflow.rejected', () => {
      const error = new Error('Network error');

      store.dispatch(fetchWorkflow.rejected(error, '', 'wf-1'));

      const state = store.getState().workflow;
      expect(state.isLoading).toBe(false);
      expect(state.error).toBe('Network error');
    });
  });
});
```

## 🔗 Integration Testing

### API Mocking with MSW
```typescript
// src/test/mocks/handlers.ts
import { rest } from 'msw';
import { mockWorkflows, mockNodes } from './data';

export const handlers = [
  // Workflows
  rest.get('/api/workflows', (req, res, ctx) => {
    const page = Number(req.url.searchParams.get('page') || 1);
    const limit = Number(req.url.searchParams.get('limit') || 20);
    const search = req.url.searchParams.get('search') || '';

    const filtered = mockWorkflows.filter(w =>
      w.name.toLowerCase().includes(search.toLowerCase())
    );

    const start = (page - 1) * limit;
    const end = start + limit;

    return res(
      ctx.json({
        data: filtered.slice(start, end),
        total: filtered.length,
        page,
        limit,
      })
    );
  }),

  rest.get('/api/workflows/:id', (req, res, ctx) => {
    const { id } = req.params;
    const workflow = mockWorkflows.find(w => w.id === id);

    if (!workflow) {
      return res(ctx.status(404), ctx.json({ message: 'Workflow not found' }));
    }

    return res(ctx.json(workflow));
  }),

  rest.post('/api/workflows', async (req, res, ctx) => {
    const body = await req.json();
    const newWorkflow = {
      id: `wf-${Date.now()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      ...body,
    };

    mockWorkflows.push(newWorkflow);
    return res(ctx.status(201), ctx.json(newWorkflow));
  }),

  rest.post('/api/workflows/:id/execute', async (req, res, ctx) => {
    const { id } = req.params;
    const { parameters } = await req.json();

    return res(
      ctx.json({
        id: `exec-${Date.now()}`,
        workflowId: id,
        status: 'running',
        parameters,
        startedAt: new Date().toISOString(),
      })
    );
  }),

  // WebSocket mock
  rest.get('/ws/workflow/:id', (req, res, ctx) => {
    return res(
      ctx.status(101),
      ctx.set('Upgrade', 'websocket'),
      ctx.set('Connection', 'Upgrade'),
    );
  }),
];

// src/test/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

### Integration Test Examples
```typescript
// src/features/workflow-builder/WorkflowBuilder.integration.test.tsx
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WorkflowBuilder } from './WorkflowBuilder';
import { store } from '@/store';
import { server } from '@/test/mocks/server';
import { rest } from 'msw';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

const renderWithProviders = (component: React.ReactElement) => {
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        {component}
      </QueryClientProvider>
    </Provider>
  );
};

describe('WorkflowBuilder Integration', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it('creates a new workflow with nodes and connections', async () => {
    const user = userEvent.setup();

    renderWithProviders(<WorkflowBuilder />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText('Create New Workflow')).toBeInTheDocument();
    });

    // Open create dialog
    await user.click(screen.getByText('Create New Workflow'));

    // Fill workflow details
    const dialog = screen.getByRole('dialog');
    const nameInput = within(dialog).getByLabelText('Workflow Name');
    await user.type(nameInput, 'Test Integration Workflow');

    await user.click(within(dialog).getByText('Create'));

    // Wait for workflow to be created
    await waitFor(() => {
      expect(screen.getByText('Test Integration Workflow')).toBeInTheDocument();
    });

    // Add a node
    const nodePanel = screen.getByTestId('node-panel');
    const csvReaderNode = within(nodePanel).getByText('CSV Reader');

    // Drag and drop simulation
    await user.click(csvReaderNode);

    // Configure node
    await waitFor(() => {
      const nodeConfig = screen.getByTestId('node-config');
      expect(nodeConfig).toBeInTheDocument();
    });

    const filePathInput = screen.getByLabelText('File Path');
    await user.type(filePathInput, '/data/test.csv');

    // Save configuration
    await user.click(screen.getByText('Save'));

    // Verify node appears on canvas
    await waitFor(() => {
      const canvas = screen.getByTestId('workflow-canvas');
      expect(within(canvas).getByText('CSV Reader')).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully', async () => {
    // Override handler to return error
    server.use(
      rest.post('/api/workflows', (req, res, ctx) => {
        return res(
          ctx.status(500),
          ctx.json({ message: 'Internal server error' })
        );
      })
    );

    const user = userEvent.setup();

    renderWithProviders(<WorkflowBuilder />);

    await user.click(screen.getByText('Create New Workflow'));

    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText('Workflow Name'), 'Test');
    await user.click(within(dialog).getByText('Create'));

    // Verify error message
    await waitFor(() => {
      expect(screen.getByText('Internal server error')).toBeInTheDocument();
    });
  });

  it('updates workflow in real-time via WebSocket', async () => {
    // Mock WebSocket behavior
    const mockWebSocket = {
      send: jest.fn(),
      close: jest.fn(),
      addEventListener: jest.fn((event, handler) => {
        if (event === 'message') {
          // Simulate execution update
          setTimeout(() => {
            handler({
              data: JSON.stringify({
                type: 'node.completed',
                payload: { nodeId: 'node-1', status: 'success' },
              }),
            });
          }, 100);
        }
      }),
      removeEventListener: jest.fn(),
    };

    global.WebSocket = jest.fn(() => mockWebSocket) as any;

    renderWithProviders(<WorkflowBuilder workflowId="wf-1" />);

    // Wait for workflow to load
    await waitFor(() => {
      expect(screen.getByTestId('workflow-canvas')).toBeInTheDocument();
    });

    // Execute workflow
    await userEvent.click(screen.getByText('Execute'));

    // Verify real-time update
    await waitFor(() => {
      const node = screen.getByTestId('node-node-1');
      expect(node).toHaveClass('node-success');
    });
  });
});
```

## 🎭 End-to-End Testing

### Playwright Setup
```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

### E2E Test Examples
```typescript
// e2e/workflow-creation.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Workflow Creation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Login if needed
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'password');
    await page.click('[data-testid="login-button"]');

    await page.waitForURL('/dashboard');
  });

  test('creates a complete workflow end-to-end', async ({ page }) => {
    // Navigate to workflow builder
    await page.click('text=Workflows');
    await page.click('text=Create New Workflow');

    // Fill workflow details
    await page.fill('[placeholder="Enter workflow name"]', 'E2E Test Workflow');
    await page.fill('[placeholder="Description"]', 'Testing workflow creation');
    await page.click('button:has-text("Create")');

    // Wait for redirect to builder
    await page.waitForURL(/\/workflows\/.*\/edit/);

    // Add CSV Reader node
    const canvas = page.locator('[data-testid="workflow-canvas"]');
    const nodePanel = page.locator('[data-testid="node-panel"]');

    await nodePanel.locator('text=CSV Reader').dragTo(canvas);

    // Configure node
    await canvas.locator('[data-node-type="CSVReader"]').dblclick();
    await page.fill('[name="file_path"]', '/data/customers.csv');
    await page.click('button:has-text("Save")');

    // Add Transform node
    await nodePanel.locator('text=Transform').dragTo(canvas, {
      targetPosition: { x: 300, y: 200 },
    });

    // Connect nodes
    const sourceHandle = canvas.locator('[data-node-id="node-1"] .source-handle');
    const targetHandle = canvas.locator('[data-node-id="node-2"] .target-handle');

    await sourceHandle.dragTo(targetHandle);

    // Save workflow
    await page.click('button:has-text("Save Workflow")');

    // Verify success
    await expect(page.locator('.toast-success')).toContainText('Workflow saved');

    // Execute workflow
    await page.click('button:has-text("Execute")');

    // Fill parameters
    await page.fill('[name="output_path"]', '/tmp/output.csv');
    await page.click('button:has-text("Run")');

    // Wait for execution
    await expect(page.locator('[data-testid="execution-status"]')).toContainText('Running');

    // Wait for completion (with timeout)
    await expect(page.locator('[data-testid="execution-status"]')).toContainText('Completed', {
      timeout: 30000,
    });

    // Verify results
    await page.click('text=View Results');
    await expect(page.locator('[data-testid="result-preview"]')).toBeVisible();
  });

  test('handles errors during workflow creation', async ({ page }) => {
    // Simulate API error by intercepting request
    await page.route('**/api/workflows', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ message: 'Invalid workflow configuration' }),
        });
      } else {
        route.continue();
      }
    });

    await page.click('text=Create New Workflow');
    await page.fill('[placeholder="Enter workflow name"]', 'Test');
    await page.click('button:has-text("Create")');

    // Verify error message
    await expect(page.locator('.toast-error')).toContainText('Invalid workflow configuration');
  });
});

// e2e/workflow-execution.spec.ts
test.describe('Workflow Execution', () => {
  test('monitors real-time execution progress', async ({ page }) => {
    await page.goto('/workflows/test-workflow');

    // Start execution
    await page.click('button:has-text("Execute")');

    // Monitor progress
    const progressBar = page.locator('[data-testid="execution-progress"]');

    // Initial state
    await expect(progressBar).toHaveAttribute('aria-valuenow', '0');

    // Progress updates
    await expect(progressBar).toHaveAttribute('aria-valuenow', '50', {
      timeout: 10000,
    });

    // Completion
    await expect(progressBar).toHaveAttribute('aria-valuenow', '100', {
      timeout: 20000,
    });

    // Verify node states
    const nodes = page.locator('[data-testid^="node-"]');
    const nodeCount = await nodes.count();

    for (let i = 0; i < nodeCount; i++) {
      await expect(nodes.nth(i)).toHaveClass(/node-success/);
    }
  });
});
```

## 🎨 Visual Testing

### Storybook Setup
```typescript
// .storybook/main.js
module.exports = {
  stories: ['../src/**/*.stories.@(js|jsx|ts|tsx|mdx)'],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-interactions',
    '@storybook/addon-a11y',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
};

// .storybook/preview.tsx
import React from 'react';
import { Preview } from '@storybook/react';
import { ThemeProvider } from '../src/contexts/ThemeContext';
import '../src/styles/global.css';

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: '^on[A-Z].*' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/,
      },
    },
  },
  decorators: [
    (Story) => (
      <ThemeProvider>
        <Story />
      </ThemeProvider>
    ),
  ],
};

export default preview;
```

### Component Stories
```typescript
// src/components/WorkflowCard/WorkflowCard.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { within, userEvent } from '@storybook/testing-library';
import { expect } from '@storybook/jest';
import { WorkflowCard } from './WorkflowCard';

const meta: Meta<typeof WorkflowCard> = {
  title: 'Workflow/WorkflowCard',
  component: WorkflowCard,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    workflow: {
      id: '1',
      name: 'Data Processing Pipeline',
      description: 'Processes customer data and generates reports',
      nodeCount: 5,
      lastRun: '2024-01-15T10:30:00Z',
      status: 'idle',
    },
  },
};

export const Running: Story = {
  args: {
    workflow: {
      ...Default.args.workflow,
      status: 'running',
      progress: 65,
    },
  },
};

export const Interactive: Story = {
  args: Default.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    // Hover over card
    await userEvent.hover(canvas.getByRole('article'));

    // Click execute button
    const executeButton = canvas.getByRole('button', { name: /execute/i });
    await userEvent.click(executeButton);

    // Verify state change
    await expect(canvas.getByText(/running/i)).toBeInTheDocument();
  },
};

export const AllStates: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4">
      <WorkflowCard
        workflow={{
          id: '1',
          name: 'Idle Workflow',
          status: 'idle',
          nodeCount: 3,
        }}
      />
      <WorkflowCard
        workflow={{
          id: '2',
          name: 'Running Workflow',
          status: 'running',
          progress: 45,
          nodeCount: 5,
        }}
      />
      <WorkflowCard
        workflow={{
          id: '3',
          name: 'Successful Workflow',
          status: 'success',
          nodeCount: 4,
          lastRun: '2024-01-15T10:30:00Z',
        }}
      />
      <WorkflowCard
        workflow={{
          id: '4',
          name: 'Failed Workflow',
          status: 'error',
          nodeCount: 6,
          error: 'Connection timeout',
        }}
      />
    </div>
  ),
};
```

## ♿ Accessibility Testing

### Jest-Axe Setup
```typescript
// src/test/a11y.test.tsx
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { Button } from '@/components/Button';
import { WorkflowCard } from '@/components/WorkflowCard';

expect.extend(toHaveNoViolations);

describe('Accessibility Tests', () => {
  it('Button has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Button>Default Button</Button>
        <Button disabled>Disabled Button</Button>
        <Button loading>Loading Button</Button>
      </>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('WorkflowCard has no accessibility violations', async () => {
    const { container } = render(
      <WorkflowCard
        workflow={{
          id: '1',
          name: 'Test Workflow',
          description: 'A test workflow',
          nodeCount: 5,
          status: 'idle',
        }}
      />
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('Form components have proper labels', async () => {
    const { container } = render(
      <form>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" required />

        <label htmlFor="password">Password</label>
        <input id="password" type="password" required />

        <button type="submit">Submit</button>
      </form>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

### Keyboard Navigation Testing
```typescript
// src/components/Navigation/Navigation.test.tsx
describe('Keyboard Navigation', () => {
  it('supports full keyboard navigation', async () => {
    const user = userEvent.setup();

    render(
      <Navigation>
        <NavItem href="/home">Home</NavItem>
        <NavItem href="/workflows">Workflows</NavItem>
        <NavItem href="/settings">Settings</NavItem>
      </Navigation>
    );

    // Tab through items
    await user.tab();
    expect(screen.getByText('Home')).toHaveFocus();

    await user.tab();
    expect(screen.getByText('Workflows')).toHaveFocus();

    await user.tab();
    expect(screen.getByText('Settings')).toHaveFocus();

    // Navigate with arrow keys
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByText('Workflows')).toHaveFocus();

    await user.keyboard('{Home}');
    expect(screen.getByText('Home')).toHaveFocus();

    await user.keyboard('{End}');
    expect(screen.getByText('Settings')).toHaveFocus();
  });
});
```

## 🚀 Performance Testing

### Performance Monitoring
```typescript
// src/test/performance.test.tsx
import { render } from '@testing-library/react';
import { measurePerformance } from '@/test/utils/performance';

describe('Performance Tests', () => {
  it('renders large list efficiently', async () => {
    const items = Array.from({ length: 1000 }, (_, i) => ({
      id: i,
      name: `Item ${i}`,
    }));

    const metrics = await measurePerformance(() => {
      render(<VirtualizedList items={items} />);
    });

    expect(metrics.renderTime).toBeLessThan(100); // ms
    expect(metrics.layoutTime).toBeLessThan(50); // ms
  });

  it('memoizes expensive computations', () => {
    const expensiveComputation = jest.fn((data) => {
      return data.reduce((acc, item) => acc + item.value, 0);
    });

    const { rerender } = render(
      <DataSummary data={testData} compute={expensiveComputation} />
    );

    expect(expensiveComputation).toHaveBeenCalledTimes(1);

    // Re-render with same data
    rerender(<DataSummary data={testData} compute={expensiveComputation} />);

    // Should not recompute
    expect(expensiveComputation).toHaveBeenCalledTimes(1);

    // Re-render with different data
    rerender(<DataSummary data={newTestData} compute={expensiveComputation} />);

    // Should recompute
    expect(expensiveComputation).toHaveBeenCalledTimes(2);
  });
});
```

## 📊 Test Coverage

### Coverage Configuration
```json
// package.json
{
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch",
    "test:coverage": "jest --coverage",
    "test:coverage:report": "jest --coverage && open coverage/lcov-report/index.html",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:visual": "storybook test",
    "test:a11y": "jest --testMatch='**/*.a11y.test.{ts,tsx}'"
  }
}
```

### Coverage Reports
```typescript
// jest.config.js (coverage settings)
module.exports = {
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.{ts,tsx}',
    '!src/test/**',
    '!src/index.tsx',
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    './src/components/': {
      branches: 90,
      functions: 90,
      lines: 90,
      statements: 90,
    },
    './src/hooks/': {
      branches: 85,
      functions: 85,
      lines: 85,
      statements: 85,
    },
  },
  coverageReporters: ['text', 'lcov', 'html', 'json-summary'],
};
```

## 🎯 Testing Best Practices

### 1. Test Organization
- Group related tests with `describe` blocks
- Use clear, descriptive test names
- Follow AAA pattern (Arrange, Act, Assert)
- Keep tests focused and atomic

### 2. Component Testing
- Test user interactions, not implementation
- Use Testing Library queries properly
- Mock external dependencies
- Test error states and edge cases

### 3. Integration Testing
- Use MSW for API mocking
- Test complete user flows
- Verify data persistence
- Test error recovery

### 4. E2E Testing
- Focus on critical user journeys
- Use stable selectors (data-testid)
- Handle async operations properly
- Test across different viewports

### 5. Performance Testing
- Monitor render performance
- Test with realistic data volumes
- Verify memoization works
- Check bundle sizes

### 6. Accessibility Testing
- Run automated accessibility checks
- Test keyboard navigation
- Verify screen reader compatibility
- Test with high contrast modes

### 7. Continuous Integration
- Run tests on every commit
- Fail fast on test failures
- Generate coverage reports
- Run visual regression tests
