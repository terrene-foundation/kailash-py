# React Integration Patterns

*Comprehensive React patterns for Kailash workflow integration*

## 🎯 Component Patterns

### Workflow Executor Component
```javascript
import React, { useState, useCallback } from 'react';
import { useKailash } from '../hooks/useKailash';

const WorkflowExecutor = ({ workflowName, defaultParams = {} }) => {
  const { execute, loading, error } = useKailash();
  const [result, setResult] = useState(null);
  const [params, setParams] = useState(defaultParams);

  const handleExecute = useCallback(async () => {
    try {
      const response = await execute(workflowName, params);
      setResult(response);
    } catch (err) {
      console.error('Execution failed:', err);
    }
  }, [execute, workflowName, params]);

  const handleParamChange = (key, value) => {
    setParams(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div className="workflow-executor">
      <h3>Execute: {workflowName}</h3>

      {/* Parameter inputs */}
      <div className="parameters">
        {Object.entries(params).map(([key, value]) => (
          <div key={key} className="param-input">
            <label>{key}:</label>
            <input
              type="text"
              value={value}
              onChange={(e) => handleParamChange(key, e.target.value)}
            />
          </div>
        ))}
      </div>

      {/* Execute button */}
      <button
        onClick={handleExecute}
        disabled={loading}
        className="execute-btn"
      >
        {loading ? 'Executing...' : 'Execute Workflow'}
      </button>

      {/* Error display */}
      {error && (
        <div className="error">
          <strong>Error:</strong> {error.message}
        </div>
      )}

      {/* Result display */}
      {result && (
        <div className="result">
          <h4>Result:</h4>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default WorkflowExecutor;
```

### Real-time Progress Component
```javascript
import React, { useState, useEffect } from 'react';
import { useKailashRealtime } from '../hooks/useKailashRealtime';

const WorkflowProgress = ({ executionId }) => {
  const { subscribe } = useKailashRealtime();
  const [progress, setProgress] = useState({
    percentage: 0,
    currentNode: null,
    status: 'pending',
    logs: []
  });

  useEffect(() => {
    if (!executionId) return;

    const progressSub = subscribe(`execution:${executionId}:progress`, (data) => {
      setProgress(prev => ({
        ...prev,
        percentage: data.percentage,
        currentNode: data.currentNode,
        status: data.status
      }));
    });

    const logSub = subscribe(`execution:${executionId}:logs`, (log) => {
      setProgress(prev => ({
        ...prev,
        logs: [...prev.logs, log]
      }));
    });

    return () => {
      progressSub.unsubscribe();
      logSub.unsubscribe();
    };
  }, [executionId, subscribe]);

  return (
    <div className="workflow-progress">
      <div className="progress-header">
        <h4>Execution Progress</h4>
        <span className={`status ${progress.status}`}>
          {progress.status}
        </span>
      </div>

      {/* Progress bar */}
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${progress.percentage}%` }}
        />
        <span className="progress-text">
          {progress.percentage}%
        </span>
      </div>

      {/* Current node */}
      {progress.currentNode && (
        <div className="current-node">
          Processing: <strong>{progress.currentNode}</strong>
        </div>
      )}

      {/* Logs */}
      <div className="logs">
        <h5>Execution Logs:</h5>
        <div className="log-container">
          {progress.logs.map((log, idx) => (
            <div key={idx} className={`log-entry ${log.level}`}>
              <span className="timestamp">{log.timestamp}</span>
              <span className="message">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default WorkflowProgress;
```

## 🪝 Custom Hooks

### useWorkflowState Hook
```javascript
import { useState, useEffect, useCallback } from 'react';
import { useKailash } from './useKailash';

export const useWorkflowState = (workflowName, autoExecute = false) => {
  const { execute, client } = useKailash();
  const [state, setState] = useState({
    data: null,
    loading: false,
    error: null,
    executionId: null,
    history: []
  });

  const executeWorkflow = useCallback(async (params) => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      const result = await execute(workflowName, params);

      setState(prev => ({
        ...prev,
        data: result.data,
        loading: false,
        executionId: result.execution_id,
        history: [...prev.history, {
          timestamp: new Date().toISOString(),
          params,
          result: result.data
        }]
      }));

      return result;
    } catch (error) {
      setState(prev => ({
        ...prev,
        loading: false,
        error
      }));
      throw error;
    }
  }, [execute, workflowName]);

  const retry = useCallback((params) => {
    const lastExecution = state.history[state.history.length - 1];
    return executeWorkflow(params || lastExecution?.params);
  }, [executeWorkflow, state.history]);

  const reset = useCallback(() => {
    setState({
      data: null,
      loading: false,
      error: null,
      executionId: null,
      history: []
    });
  }, []);

  useEffect(() => {
    if (autoExecute) {
      executeWorkflow({});
    }
  }, [autoExecute, executeWorkflow]);

  return {
    ...state,
    execute: executeWorkflow,
    retry,
    reset
  };
};
```

### useWorkflowForm Hook
```javascript
import { useState, useCallback } from 'react';
import { useWorkflowState } from './useWorkflowState';

export const useWorkflowForm = (workflowName, schema) => {
  const [formData, setFormData] = useState(
    schema.reduce((acc, field) => ({ ...acc, [field.name]: field.default || '' }), {})
  );
  const [validation, setValidation] = useState({});

  const { execute, loading, error, data } = useWorkflowState(workflowName);

  const validateField = useCallback((name, value) => {
    const field = schema.find(f => f.name === name);
    if (!field) return null;

    const errors = [];

    if (field.required && (!value || value === '')) {
      errors.push(`${field.label} is required`);
    }

    if (field.type === 'email' && value && !value.includes('@')) {
      errors.push(`${field.label} must be a valid email`);
    }

    if (field.min && value && value.length < field.min) {
      errors.push(`${field.label} must be at least ${field.min} characters`);
    }

    return errors.length > 0 ? errors : null;
  }, [schema]);

  const updateField = useCallback((name, value) => {
    setFormData(prev => ({ ...prev, [name]: value }));

    // Validate field
    const fieldErrors = validateField(name, value);
    setValidation(prev => ({
      ...prev,
      [name]: fieldErrors
    }));
  }, [validateField]);

  const validateForm = useCallback(() => {
    const newValidation = {};
    let isValid = true;

    schema.forEach(field => {
      const errors = validateField(field.name, formData[field.name]);
      if (errors) {
        newValidation[field.name] = errors;
        isValid = false;
      }
    });

    setValidation(newValidation);
    return isValid;
  }, [schema, formData, validateField]);

  const submitForm = useCallback(async () => {
    if (!validateForm()) {
      return false;
    }

    try {
      await execute(formData);
      return true;
    } catch (err) {
      return false;
    }
  }, [validateForm, execute, formData]);

  const resetForm = useCallback(() => {
    setFormData(
      schema.reduce((acc, field) => ({ ...acc, [field.name]: field.default || '' }), {})
    );
    setValidation({});
  }, [schema]);

  return {
    formData,
    validation,
    loading,
    error,
    data,
    updateField,
    submitForm,
    resetForm,
    isValid: Object.keys(validation).length === 0
  };
};
```

## 📋 Form Components

### Dynamic Workflow Form
```javascript
import React from 'react';
import { useWorkflowForm } from '../hooks/useWorkflowForm';

const WorkflowForm = ({ workflowName, schema, onSuccess }) => {
  const {
    formData,
    validation,
    loading,
    error,
    data,
    updateField,
    submitForm,
    resetForm,
    isValid
  } = useWorkflowForm(workflowName, schema);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const success = await submitForm();
    if (success && onSuccess) {
      onSuccess(data);
    }
  };

  const renderField = (field) => {
    const hasError = validation[field.name];

    return (
      <div key={field.name} className="form-field">
        <label htmlFor={field.name}>
          {field.label}
          {field.required && <span className="required">*</span>}
        </label>

        {field.type === 'select' ? (
          <select
            id={field.name}
            value={formData[field.name]}
            onChange={(e) => updateField(field.name, e.target.value)}
            className={hasError ? 'error' : ''}
          >
            <option value="">Select...</option>
            {field.options.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : field.type === 'textarea' ? (
          <textarea
            id={field.name}
            value={formData[field.name]}
            onChange={(e) => updateField(field.name, e.target.value)}
            placeholder={field.placeholder}
            className={hasError ? 'error' : ''}
            rows={field.rows || 3}
          />
        ) : (
          <input
            id={field.name}
            type={field.type || 'text'}
            value={formData[field.name]}
            onChange={(e) => updateField(field.name, e.target.value)}
            placeholder={field.placeholder}
            className={hasError ? 'error' : ''}
          />
        )}

        {hasError && (
          <div className="field-errors">
            {hasError.map((error, idx) => (
              <span key={idx} className="error-message">{error}</span>
            ))}
          </div>
        )}

        {field.help && (
          <small className="field-help">{field.help}</small>
        )}
      </div>
    );
  };

  return (
    <form onSubmit={handleSubmit} className="workflow-form">
      <h3>Execute {workflowName}</h3>

      {schema.map(renderField)}

      {error && (
        <div className="form-error">
          <strong>Execution Error:</strong> {error.message}
        </div>
      )}

      <div className="form-actions">
        <button
          type="submit"
          disabled={loading || !isValid}
          className="submit-btn"
        >
          {loading ? 'Executing...' : 'Execute Workflow'}
        </button>

        <button
          type="button"
          onClick={resetForm}
          className="reset-btn"
        >
          Reset
        </button>
      </div>

      {data && (
        <div className="form-result">
          <h4>Execution Result:</h4>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </form>
  );
};

export default WorkflowForm;
```

## 📊 Data Components

### Workflow Results Table
```javascript
import React, { useMemo } from 'react';

const WorkflowResultsTable = ({ data, columns }) => {
  const processedData = useMemo(() => {
    if (!data || !Array.isArray(data)) return [];

    return data.map((row, index) => ({
      id: row.id || index,
      ...row
    }));
  }, [data]);

  const sortedData = useMemo(() => {
    return [...processedData].sort((a, b) => {
      // Add sorting logic here
      return 0;
    });
  }, [processedData]);

  if (!data || processedData.length === 0) {
    return <div className="no-data">No data available</div>;
  }

  return (
    <div className="results-table">
      <table>
        <thead>
          <tr>
            {columns.map(col => (
              <th key={col.key}>
                {col.label}
                {col.sortable && (
                  <button className="sort-btn">⇅</button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedData.map(row => (
            <tr key={row.id}>
              {columns.map(col => (
                <td key={col.key}>
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="table-footer">
        Showing {sortedData.length} results
      </div>
    </div>
  );
};

export default WorkflowResultsTable;
```

## 🎨 UI Patterns

### Workflow Dashboard
```javascript
import React, { useState, useEffect } from 'react';
import WorkflowExecutor from './WorkflowExecutor';
import WorkflowProgress from './WorkflowProgress';
import WorkflowResultsTable from './WorkflowResultsTable';

const WorkflowDashboard = () => {
  const [activeWorkflow, setActiveWorkflow] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [workflows] = useState([
    { name: 'data-processor', label: 'Data Processor' },
    { name: 'report-generator', label: 'Report Generator' },
    { name: 'analytics-pipeline', label: 'Analytics Pipeline' }
  ]);

  const handleWorkflowComplete = (result) => {
    setExecutions(prev => [{
      id: result.execution_id,
      workflow: activeWorkflow,
      timestamp: new Date().toISOString(),
      status: result.status,
      duration: result.duration_ms
    }, ...prev]);
  };

  return (
    <div className="workflow-dashboard">
      <div className="dashboard-header">
        <h1>Workflow Dashboard</h1>

        <div className="workflow-selector">
          <select
            value={activeWorkflow || ''}
            onChange={(e) => setActiveWorkflow(e.target.value)}
          >
            <option value="">Select Workflow...</option>
            {workflows.map(wf => (
              <option key={wf.name} value={wf.name}>
                {wf.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="dashboard-content">
        {activeWorkflow && (
          <div className="workflow-section">
            <WorkflowExecutor
              workflowName={activeWorkflow}
              onComplete={handleWorkflowComplete}
            />
          </div>
        )}

        <div className="executions-section">
          <h3>Recent Executions</h3>
          <WorkflowResultsTable
            data={executions}
            columns={[
              { key: 'workflow', label: 'Workflow' },
              { key: 'timestamp', label: 'Started', render: (val) => new Date(val).toLocaleString() },
              { key: 'status', label: 'Status', render: (val) => <span className={`status ${val}`}>{val}</span> },
              { key: 'duration', label: 'Duration (ms)' }
            ]}
          />
        </div>
      </div>
    </div>
  );
};

export default WorkflowDashboard;
```

## 🔗 Next Steps

- [Vue.js Patterns](vue-patterns.md) - Vue integration
- [Mobile Patterns](mobile-patterns.md) - React Native/mobile
- [Backend Setup](../middleware/) - Kailash gateway configuration
