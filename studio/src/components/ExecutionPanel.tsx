import { useState, useEffect } from "react";

interface LogEntry {
  timestamp: string;
  level: "info" | "warn" | "error";
  message: string;
}

export function ExecutionPanel() {
  const [status, setStatus] = useState<"ready" | "running" | "success" | "error">("ready");
  const [executionTime, setExecutionTime] = useState("2.4s");
  const [nodesProcessed, setNodesProcessed] = useState("3/3");
  const [recordsProcessed, setRecordsProcessed] = useState("15,420");
  const [memoryUsage, setMemoryUsage] = useState("124 MB");
  const [logs, setLogs] = useState<LogEntry[]>([
    { timestamp: "14:23:45", level: "info", message: "Workflow execution started" },
    { timestamp: "14:23:46", level: "info", message: "CSV Reader: Loaded 15,420 records" },
    { timestamp: "14:23:47", level: "info", message: "Data Filter: Filtered to 12,336 active records" },
    { timestamp: "14:23:48", level: "info", message: "API Call: Successfully sent data to endpoint" },
    { timestamp: "14:23:49", level: "info", message: "Workflow execution completed successfully" },
  ]);

  // Simulate execution after component mounts
  useEffect(() => {
    const timer = setTimeout(() => {
      simulateExecution();
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  const simulateExecution = () => {
    setStatus("running");
    setTimeout(() => {
      setStatus("success");
    }, 3000);
  };

  return (
    <section className="execution-panel">
      <div className="execution-header">
        <div className="execution-title">Workflow Execution</div>
        <div className={`execution-status status-${status}`}>
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </div>
      </div>

      <div className="execution-content">
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-label">Execution Time</div>
            <div className="metric-value">{executionTime}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Nodes Processed</div>
            <div className="metric-value">{nodesProcessed}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Records Processed</div>
            <div className="metric-value">{recordsProcessed}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Memory Usage</div>
            <div className="metric-value">{memoryUsage}</div>
          </div>
        </div>

        <div style={{ marginBottom: "10px", fontSize: "12px", fontWeight: 600 }}>
          Execution Log
        </div>
        <div className="log-output">
          {logs.map((log, index) => (
            <div key={index} className="log-entry">
              <span className="log-timestamp">{log.timestamp}</span>{" "}
              <span className={`log-level-${log.level}`}>[{log.level.toUpperCase()}]</span>{" "}
              {log.message}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
