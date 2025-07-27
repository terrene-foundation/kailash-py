# Frontend Integration Guide

*Complete guide for integrating React, Vue, and other frontends with Kailash middleware*

## 🚀 Quick Start - React Integration

```javascript
// React component with real-time Kailash integration
import React, { useState, useEffect } from 'react';
import { KailashClient } from '@kailash/client';

const KailashWorkflowComponent = () => {
  const [client] = useState(() => new KailashClient({
    baseURL: 'http://localhost:8000',
    enableRealtime: true,
    enableAIChat: true
  }));

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // Execute workflow
  const executeWorkflow = async (workflowName, parameters) => {
    setLoading(true);
    try {
      const response = await client.executeWorkflow(workflowName, parameters);
      setResult(response);
    } catch (error) {
      console.error('Workflow execution failed:', error);
    } finally {
      setLoading(false);
    }
  };

  // Real-time updates
  useEffect(() => {
    const subscription = client.subscribe('workflow_updates', (update) => {
      setResult(prev => ({ ...prev, ...update }));
    });

    return () => subscription.unsubscribe();
  }, [client]);

  return (
    <div className="kailash-workflow">
      <button
        onClick={() => executeWorkflow('data-processor', { input: 'test' })}
        disabled={loading}
      >
        {loading ? 'Processing...' : 'Execute Workflow'}
      </button>

      {result && (
        <div className="result">
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default KailashWorkflowComponent;
```

## 🔧 Backend Setup - Kailash Gateway

```python
from kailash.api.gateway import create_gateway
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data.csv"
})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'count': len(input_data), 'summary': input_data[:5]}"
})
workflow.add_connection("reader", "data", "processor", "input_data")

# Create gateway with frontend features
gateway = create_gateway(
    workflows={"data-processor": workflow},
    config={
        # Authentication
        "enable_auth": True,
        "cors_origins": ["http://localhost:3000"],  # React dev server

        # Real-time features
        "enable_realtime": True,
        "enable_ai_chat": True,

        # API features
        "enable_monitoring": True,
        "rate_limiting": {"requests_per_minute": 1000}
    }
)

# Run with WebSocket support
gateway.run(host="0.0.0.0", port=8000)

```

## 🌐 Frontend Client Libraries

### React Hook
```javascript
// useKailash.js - Custom React hook
import { useState, useEffect, useCallback } from 'react';
import { KailashClient } from '@kailash/client';

export const useKailash = (config = {}) => {
  const [client] = useState(() => new KailashClient(config));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(async (workflowName, parameters) => {
    setLoading(true);
    setError(null);

    try {
      const result = await client.executeWorkflow(workflowName, parameters);
      return result;
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [client]);

  const subscribe = useCallback((event, callback) => {
    return client.subscribe(event, callback);
  }, [client]);

  return { execute, subscribe, loading, error, client };
};

// Usage in component
const MyComponent = () => {
  const { execute, loading, error } = useKailash({
    baseURL: process.env.REACT_APP_KAILASH_URL
  });

  const handleSubmit = async (data) => {
    try {
      const result = await execute('my-workflow', data);
      console.log('Success:', result);
    } catch (err) {
      console.error('Failed:', err);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form content */}
      {loading && <div>Processing...</div>}
      {error && <div>Error: {error.message}</div>}
    </form>
  );
};
```

### Vue.js Integration
```javascript
// KailashPlugin.js - Vue plugin
import { KailashClient } from '@kailash/client';

export default {
  install(app, options) {
    const client = new KailashClient(options);

    app.config.globalProperties.$kailash = client;
    app.provide('kailash', client);
  }
};

// main.js
import { createApp } from 'vue';
import KailashPlugin from './plugins/KailashPlugin';
import App from './App.vue';

const app = createApp(App);
app.use(KailashPlugin, {
  baseURL: 'http://localhost:8000',
  enableRealtime: true
});
app.mount('#app');

// Component usage
<template>
  <div>
    <button @click="executeWorkflow" :disabled="loading">
      {{ loading ? 'Processing...' : 'Execute' }}
    </button>
    <div v-if="result">{{ result }}</div>
  </div>
</template>

<script>
import { inject, ref } from 'vue';

export default {
  setup() {
    const kailash = inject('kailash');
    const loading = ref(false);
    const result = ref(null);

    const executeWorkflow = async () => {
      loading.value = true;
      try {
        result.value = await kailash.executeWorkflow('data-processor', {
          input: 'test data'
        });
      } finally {
        loading.value = false;
      }
    };

    return { executeWorkflow, loading, result };
  }
};
</script>
```

## 📡 Real-time Communication

### WebSocket Integration
```javascript
// Real-time workflow updates
class KailashRealtime {
  constructor(baseURL) {
    this.ws = new WebSocket(`ws://${baseURL}/ws`);
    this.subscriptions = new Map();

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };
  }

  subscribe(channel, callback) {
    if (!this.subscriptions.has(channel)) {
      this.subscriptions.set(channel, new Set());
      // Subscribe to channel
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        channel: channel
      }));
    }

    this.subscriptions.get(channel).add(callback);

    return {
      unsubscribe: () => {
        this.subscriptions.get(channel)?.delete(callback);
      }
    };
  }

  handleMessage(message) {
    const callbacks = this.subscriptions.get(message.channel);
    if (callbacks) {
      callbacks.forEach(callback => callback(message.data));
    }
  }
}

// React component with real-time updates
const RealtimeWorkflow = () => {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('idle');

  useEffect(() => {
    const realtime = new KailashRealtime('localhost:8000');

    const progressSub = realtime.subscribe('workflow_progress', (data) => {
      setProgress(data.percentage);
      setStatus(data.status);
    });

    return () => {
      progressSub.unsubscribe();
    };
  }, []);

  return (
    <div>
      <div>Status: {status}</div>
      <div>Progress: {progress}%</div>
      <progress value={progress} max="100" />
    </div>
  );
};
```

### Server-Sent Events (SSE)
```javascript
// SSE for workflow updates
const useWorkflowSSE = (workflowId) => {
  const [updates, setUpdates] = useState([]);

  useEffect(() => {
    const eventSource = new EventSource(
      `/api/workflows/${workflowId}/events`
    );

    eventSource.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setUpdates(prev => [...prev, update]);
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
    };

    return () => eventSource.close();
  }, [workflowId]);

  return updates;
};
```

## 🤖 AI Chat Integration

### Chat Interface Component
```javascript
// AI Chat with workflow context
const KailashAIChat = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          context: {
            current_workflow: 'data-processor',
            available_workflows: ['data-processor', 'report-generator']
          }
        })
      });

      const data = await response.json();
      const aiMessage = { role: 'assistant', content: data.response };
      setMessages(prev => [...prev, aiMessage]);

      // If AI suggests workflow execution
      if (data.suggested_workflow) {
        await executeWorkflow(data.suggested_workflow, data.parameters);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-chat">
      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <strong>{msg.role}:</strong> {msg.content}
          </div>
        ))}
        {loading && <div className="message loading">AI is thinking...</div>}
      </div>

      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask me about your workflows..."
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
        />
        <button onClick={sendMessage} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  );
};
```

## 📊 Data Visualization

### Chart Integration
```javascript
// Chart.js integration with Kailash data
import { Line, Bar, Pie } from 'react-chartjs-2';

const KailashChart = ({ workflowName, chartType = 'line' }) => {
  const [chartData, setChartData] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      const result = await kailash.executeWorkflow(workflowName, {
        output_format: 'chart_data'
      });

      setChartData({
        labels: result.labels,
        datasets: [{
          label: result.dataset_label,
          data: result.data,
          backgroundColor: 'rgba(75, 192, 192, 0.6)',
          borderColor: 'rgba(75, 192, 192, 1)',
        }]
      });
    };

    fetchData();
  }, [workflowName]);

  if (!chartData) return <div>Loading chart...</div>;

  const ChartComponent = {
    line: Line,
    bar: Bar,
    pie: Pie
  }[chartType];

  return (
    <div className="kailash-chart">
      <ChartComponent
        data={chartData}
        options={{
          responsive: true,
          plugins: {
            title: {
              display: true,
              text: `Workflow: ${workflowName}`
            }
          }
        }}
      />
    </div>
  );
};
```

## 🔐 Authentication & Security

### JWT Authentication
```javascript
// Authentication context
const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('kailash_token'));
  const [user, setUser] = useState(null);

  const login = async (credentials) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials)
    });

    const data = await response.json();
    setToken(data.token);
    setUser(data.user);
    localStorage.setItem('kailash_token', data.token);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('kailash_token');
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

// Authenticated API client
const useAuthenticatedKailash = () => {
  const { token } = useContext(AuthContext);

  return useMemo(() => new KailashClient({
    baseURL: process.env.REACT_APP_KAILASH_URL,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }), [token]);
};
```

## 🚀 Deployment Patterns

### Docker Setup
```dockerfile
# Frontend Dockerfile
FROM node:16-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci --only=production

# Copy source
COPY . .

# Build for production
RUN npm run build

# Serve with nginx
FROM nginx:alpine
COPY --from=0 /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Environment Configuration
```javascript
// config.js - Environment-specific configuration
const config = {
  development: {
    kailashURL: 'http://localhost:8000',
    wsURL: 'ws://localhost:8000/ws',
    enableDebug: true
  },
  staging: {
    kailashURL: 'https://staging-api.company.com',
    wsURL: 'wss://staging-api.company.com/ws',
    enableDebug: false
  },
  production: {
    kailashURL: 'https://api.company.com',
    wsURL: 'wss://api.company.com/ws',
    enableDebug: false
  }
};

export default config[process.env.NODE_ENV || 'development'];
```

## 📱 Mobile Integration

### React Native
```javascript
// React Native Kailash integration
import { useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const useKailashMobile = () => {
  const [client, setClient] = useState(null);

  useEffect(() => {
    const initClient = async () => {
      const token = await AsyncStorage.getItem('auth_token');
      const client = new KailashClient({
        baseURL: 'https://api.company.com',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      setClient(client);
    };

    initClient();
  }, []);

  const executeWorkflow = async (name, params) => {
    if (!client) throw new Error('Client not initialized');
    return await client.executeWorkflow(name, params);
  };

  return { executeWorkflow, ready: !!client };
};
```

## 🔗 Next Steps

- [Middleware Guide](../middleware/) - Backend middleware setup
- [Production Guide](../developer/04-production.md) - Production deployment
- [Security Patterns](../architecture/security-patterns.md) - Security implementation
