import React from "react";
import { useWorkflowStore } from "../../store/workflowStore";

export function ExecutionPanel() {
  const { isExecuting, executeWorkflow, executionResults, clearExecution } = useWorkflowStore();

  const handleExecute = async () => {
    await executeWorkflow();
  };

  const handleClear = () => {
    clearExecution();
  };

  return (
    <section className="execution-panel">
      <div className="execution-header">
        <h3 className="execution-title">Execution</h3>
        <div className="execution-controls">
          <button
            className={`btn btn-primary ${isExecuting ? "disabled" : ""}`}
            onClick={handleExecute}
            disabled={isExecuting}
          >
            {isExecuting ? "Running..." : "Execute Workflow"}
          </button>
          {executionResults.size > 0 && (
            <button className="btn" onClick={handleClear}>
              Clear Results
            </button>
          )}
        </div>
      </div>

      <div className="execution-content">
        {isExecuting && (
          <div className="execution-status">
            <div className="loading-spinner">⚡</div>
            <p>Executing workflow...</p>
          </div>
        )}

        {!isExecuting && executionResults.size === 0 && (
          <div className="empty-state">
            <p>Click "Execute Workflow" to run your workflow</p>
          </div>
        )}

        {!isExecuting && executionResults.size > 0 && (
          <div className="execution-results">
            <h4>Results</h4>
            {Array.from(executionResults.entries()).map(([nodeId, result]) => (
              <div key={nodeId} className="result-item">
                <div className="result-header">
                  <strong>{nodeId}</strong>
                  {result.error && <span className="status-error">❌ Error</span>}
                  {!result.error && <span className="status-success">✅ Success</span>}
                </div>
                <pre className="result-data">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
