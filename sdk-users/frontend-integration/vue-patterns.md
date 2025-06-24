# Vue.js Integration Patterns

*Vue 3 Composition API patterns for Kailash workflow integration*

## 🎯 Composables

### useKailash Composable
```javascript
// composables/useKailash.js
import { ref, reactive, computed } from 'vue';
import { KailashClient } from '@kailash/client';

const globalState = reactive({
  client: null,
  isConnected: false,
  error: null
});

export const useKailash = (config = {}) => {
  const loading = ref(false);
  const error = ref(null);

  // Initialize client if not already done
  if (!globalState.client) {
    globalState.client = new KailashClient({
      baseURL: config.baseURL || 'http://localhost:8000',
      ...config
    });

    globalState.client.on('connect', () => {
      globalState.isConnected = true;
    });

    globalState.client.on('disconnect', () => {
      globalState.isConnected = false;
    });
  }

  const execute = async (workflowName, parameters = {}) => {
    loading.value = true;
    error.value = null;

    try {
      const result = await globalState.client.executeWorkflow(workflowName, parameters);
      return result;
    } catch (err) {
      error.value = err;
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const subscribe = (channel, callback) => {
    return globalState.client.subscribe(channel, callback);
  };

  return {
    execute,
    subscribe,
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    isConnected: computed(() => globalState.isConnected),
    client: globalState.client
  };
};
```

### useWorkflowState Composable
```javascript
// composables/useWorkflowState.js
import { ref, reactive, computed, watch } from 'vue';
import { useKailash } from './useKailash';

export const useWorkflowState = (workflowName, options = {}) => {
  const { execute } = useKailash();

  const state = reactive({
    data: null,
    loading: false,
    error: null,
    executionId: null,
    history: []
  });

  const executeWorkflow = async (params = {}) => {
    state.loading = true;
    state.error = null;

    try {
      const result = await execute(workflowName, params);

      state.data = result.data;
      state.executionId = result.execution_id;
      state.history.push({
        timestamp: new Date().toISOString(),
        params,
        result: result.data
      });

      if (options.onSuccess) {
        options.onSuccess(result);
      }

      return result;
    } catch (error) {
      state.error = error;

      if (options.onError) {
        options.onError(error);
      }

      throw error;
    } finally {
      state.loading = false;
    }
  };

  const retry = () => {
    const lastExecution = state.history[state.history.length - 1];
    if (lastExecution) {
      return executeWorkflow(lastExecution.params);
    }
  };

  const reset = () => {
    Object.assign(state, {
      data: null,
      loading: false,
      error: null,
      executionId: null,
      history: []
    });
  };

  // Auto-execute if specified
  if (options.autoExecute) {
    executeWorkflow(options.defaultParams || {});
  }

  return {
    state: readonly(state),
    execute: executeWorkflow,
    retry,
    reset,
    isLoading: computed(() => state.loading),
    hasError: computed(() => !!state.error),
    hasData: computed(() => !!state.data)
  };
};
```

### useRealtime Composable
```javascript
// composables/useRealtime.js
import { ref, onMounted, onUnmounted } from 'vue';
import { useKailash } from './useKailash';

export const useRealtime = (channels = []) => {
  const { subscribe } = useKailash();
  const subscriptions = ref([]);
  const messages = ref([]);
  const connected = ref(false);

  const addSubscription = (channel, callback) => {
    const subscription = subscribe(channel, (data) => {
      messages.value.push({
        channel,
        data,
        timestamp: new Date().toISOString()
      });

      if (callback) {
        callback(data);
      }
    });

    subscriptions.value.push(subscription);
    return subscription;
  };

  const removeSubscription = (subscription) => {
    subscription.unsubscribe();
    const index = subscriptions.value.indexOf(subscription);
    if (index > -1) {
      subscriptions.value.splice(index, 1);
    }
  };

  const clearMessages = () => {
    messages.value = [];
  };

  onMounted(() => {
    // Subscribe to initial channels
    channels.forEach(channel => {
      addSubscription(channel);
    });
    connected.value = true;
  });

  onUnmounted(() => {
    // Cleanup subscriptions
    subscriptions.value.forEach(sub => sub.unsubscribe());
    subscriptions.value = [];
    connected.value = false;
  });

  return {
    messages,
    connected,
    addSubscription,
    removeSubscription,
    clearMessages
  };
};
```

## 🧩 Vue Components

### Workflow Executor Component
```vue
<!-- components/WorkflowExecutor.vue -->
<template>
  <div class="workflow-executor">
    <div class="executor-header">
      <h3>{{ workflowLabel || workflowName }}</h3>
      <div class="status-indicator" :class="{ connected: isConnected }">
        {{ isConnected ? 'Connected' : 'Disconnected' }}
      </div>
    </div>

    <!-- Parameters Form -->
    <form @submit.prevent="handleExecute" class="parameters-form">
      <div
        v-for="param in parameters"
        :key="param.name"
        class="param-group"
      >
        <label :for="param.name">{{ param.label }}</label>

        <input
          v-if="param.type === 'text'"
          :id="param.name"
          v-model="formData[param.name]"
          type="text"
          :placeholder="param.placeholder"
          :required="param.required"
        />

        <textarea
          v-else-if="param.type === 'textarea'"
          :id="param.name"
          v-model="formData[param.name]"
          :placeholder="param.placeholder"
          :required="param.required"
          rows="3"
        />

        <select
          v-else-if="param.type === 'select'"
          :id="param.name"
          v-model="formData[param.name]"
          :required="param.required"
        >
          <option value="">Select...</option>
          <option
            v-for="option in param.options"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </div>

      <div class="form-actions">
        <button
          type="submit"
          :disabled="isLoading"
          class="execute-btn"
        >
          {{ isLoading ? 'Executing...' : 'Execute' }}
        </button>

        <button
          type="button"
          @click="resetForm"
          class="reset-btn"
        >
          Reset
        </button>
      </div>
    </form>

    <!-- Error Display -->
    <div v-if="hasError" class="error-message">
      <strong>Error:</strong> {{ state.error.message }}
    </div>

    <!-- Result Display -->
    <div v-if="hasData" class="result-container">
      <h4>Result:</h4>
      <pre class="result-data">{{ JSON.stringify(state.data, null, 2) }}</pre>
    </div>

    <!-- Execution History -->
    <div v-if="state.history.length > 0" class="history-container">
      <h4>Execution History:</h4>
      <div
        v-for="(execution, index) in state.history"
        :key="index"
        class="history-item"
      >
        <div class="history-timestamp">
          {{ new Date(execution.timestamp).toLocaleString() }}
        </div>
        <div class="history-params">
          Params: {{ JSON.stringify(execution.params) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue';
import { useWorkflowState } from '../composables/useWorkflowState';
import { useKailash } from '../composables/useKailash';

const props = defineProps({
  workflowName: {
    type: String,
    required: true
  },
  workflowLabel: String,
  parameters: {
    type: Array,
    default: () => []
  },
  defaultParams: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(['success', 'error']);

const { isConnected } = useKailash();
const { state, execute, reset, isLoading, hasError, hasData } = useWorkflowState(
  props.workflowName,
  {
    onSuccess: (result) => emit('success', result),
    onError: (error) => emit('error', error)
  }
);

// Form data
const formData = reactive({ ...props.defaultParams });

// Initialize form data from parameters
props.parameters.forEach(param => {
  if (!(param.name in formData)) {
    formData[param.name] = param.default || '';
  }
});

const handleExecute = async () => {
  try {
    await execute(formData);
  } catch (error) {
    console.error('Execution failed:', error);
  }
};

const resetForm = () => {
  Object.keys(formData).forEach(key => {
    formData[key] = props.defaultParams[key] || '';
  });
  reset();
};
</script>

<style scoped>
.workflow-executor {
  max-width: 600px;
  margin: 0 auto;
  padding: 1rem;
  border: 1px solid #ddd;
  border-radius: 8px;
}

.executor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-indicator {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  background-color: #f87171;
  color: white;
}

.status-indicator.connected {
  background-color: #10b981;
}

.parameters-form {
  margin-bottom: 1rem;
}

.param-group {
  margin-bottom: 1rem;
}

.param-group label {
  display: block;
  margin-bottom: 0.25rem;
  font-weight: 500;
}

.param-group input,
.param-group textarea,
.param-group select {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
}

.form-actions {
  display: flex;
  gap: 1rem;
}

.execute-btn,
.reset-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.execute-btn {
  background-color: #3b82f6;
  color: white;
}

.execute-btn:disabled {
  background-color: #9ca3af;
  cursor: not-allowed;
}

.reset-btn {
  background-color: #6b7280;
  color: white;
}

.error-message {
  padding: 1rem;
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  color: #dc2626;
  margin-bottom: 1rem;
}

.result-container,
.history-container {
  margin-top: 1rem;
}

.result-data {
  background-color: #f9fafb;
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
}

.history-item {
  padding: 0.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.history-timestamp {
  font-size: 0.875rem;
  color: #6b7280;
}

.history-params {
  font-size: 0.875rem;
  font-family: monospace;
}
</style>
```

### Real-time Progress Component
```vue
<!-- components/WorkflowProgress.vue -->
<template>
  <div class="workflow-progress">
    <div class="progress-header">
      <h4>Workflow Progress</h4>
      <span :class="['status-badge', status]">{{ status }}</span>
    </div>

    <!-- Progress Bar -->
    <div class="progress-bar-container">
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: `${percentage}%` }"
        />
      </div>
      <span class="progress-text">{{ percentage }}%</span>
    </div>

    <!-- Current Node -->
    <div v-if="currentNode" class="current-node">
      <strong>Processing:</strong> {{ currentNode }}
    </div>

    <!-- Node Progress -->
    <div v-if="nodeProgress.length > 0" class="node-progress">
      <h5>Node Status:</h5>
      <div
        v-for="node in nodeProgress"
        :key="node.id"
        :class="['node-item', node.status]"
      >
        <span class="node-name">{{ node.name }}</span>
        <span class="node-status">{{ node.status }}</span>
        <span v-if="node.duration" class="node-duration">
          {{ node.duration }}ms
        </span>
      </div>
    </div>

    <!-- Live Logs -->
    <div v-if="showLogs && logs.length > 0" class="logs-container">
      <div class="logs-header">
        <h5>Live Logs</h5>
        <button @click="clearLogs" class="clear-logs-btn">Clear</button>
      </div>
      <div class="logs-content" ref="logsContainer">
        <div
          v-for="log in logs"
          :key="log.id"
          :class="['log-entry', log.level]"
        >
          <span class="log-timestamp">{{ formatTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level.toUpperCase() }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue';
import { useRealtime } from '../composables/useRealtime';

const props = defineProps({
  executionId: {
    type: String,
    required: true
  },
  showLogs: {
    type: Boolean,
    default: true
  }
});

const emit = defineEmits(['complete', 'error']);

// Progress state
const percentage = ref(0);
const status = ref('pending');
const currentNode = ref(null);
const nodeProgress = reactive([]);
const logs = reactive([]);
const logsContainer = ref(null);

// Set up real-time subscriptions
const { addSubscription } = useRealtime();

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString();
};

const clearLogs = () => {
  logs.splice(0);
};

const scrollLogsToBottom = () => {
  nextTick(() => {
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight;
    }
  });
};

// Watch for execution ID changes
watch(() => props.executionId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    // Reset state
    percentage.value = 0;
    status.value = 'pending';
    currentNode.value = null;
    nodeProgress.splice(0);
    logs.splice(0);

    // Subscribe to progress updates
    addSubscription(`execution:${newId}:progress`, (data) => {
      percentage.value = data.percentage || 0;
      status.value = data.status || 'running';
      currentNode.value = data.currentNode;

      if (data.status === 'completed') {
        emit('complete', data);
      } else if (data.status === 'failed') {
        emit('error', data.error);
      }
    });

    // Subscribe to node updates
    addSubscription(`execution:${newId}:nodes`, (data) => {
      const existingIndex = nodeProgress.findIndex(n => n.id === data.id);
      if (existingIndex >= 0) {
        Object.assign(nodeProgress[existingIndex], data);
      } else {
        nodeProgress.push(data);
      }
    });

    // Subscribe to logs
    addSubscription(`execution:${newId}:logs`, (logData) => {
      logs.push({
        id: Date.now() + Math.random(),
        ...logData
      });
      scrollLogsToBottom();
    });
  }
}, { immediate: true });
</script>

<style scoped>
.workflow-progress {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
}

.status-badge.pending {
  background-color: #fbbf24;
  color: #92400e;
}

.status-badge.running {
  background-color: #3b82f6;
  color: white;
}

.status-badge.completed {
  background-color: #10b981;
  color: white;
}

.status-badge.failed {
  background-color: #ef4444;
  color: white;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.progress-bar {
  flex: 1;
  height: 1rem;
  background-color: #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #3b82f6;
  transition: width 0.3s ease;
}

.progress-text {
  font-weight: 500;
  min-width: 3rem;
}

.current-node {
  margin-bottom: 1rem;
  padding: 0.5rem;
  background-color: #f3f4f6;
  border-radius: 4px;
}

.node-progress {
  margin-bottom: 1rem;
}

.node-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.node-item.completed {
  color: #10b981;
}

.node-item.failed {
  color: #ef4444;
}

.node-item.running {
  color: #3b82f6;
}

.logs-container {
  margin-top: 1rem;
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.clear-logs-btn {
  padding: 0.25rem 0.5rem;
  background-color: #6b7280;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
}

.logs-content {
  height: 200px;
  overflow-y: auto;
  background-color: #1f2937;
  border-radius: 4px;
  padding: 0.5rem;
}

.log-entry {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
  font-family: monospace;
  font-size: 0.875rem;
}

.log-entry.info {
  color: #e5e7eb;
}

.log-entry.warning {
  color: #fbbf24;
}

.log-entry.error {
  color: #ef4444;
}

.log-timestamp {
  color: #9ca3af;
  min-width: 4rem;
}

.log-level {
  min-width: 3rem;
  font-weight: 500;
}

.log-message {
  flex: 1;
}
</style>
```

## 🔗 Next Steps

- [React Patterns](react-patterns.md) - React integration
- [Mobile Patterns](mobile-patterns.md) - Mobile development
- [Middleware Setup](../middleware/) - Backend configuration
