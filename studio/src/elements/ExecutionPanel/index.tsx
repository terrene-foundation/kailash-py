import React, { useEffect, useState } from "react";
import { X, Play, CheckCircle, XCircle, Clock } from "lucide-react";
import { useWorkflowStore } from "@/store/workflowStore";

interface Execution {
  id: string;
  workflow_id: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at?: string;
  result?: any;
  error?: string;
}

export function ExecutionPanel() {
  const { setShowExecutionPanel, currentWorkflow } = useWorkflowStore();
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);

  // Mock execution for now
  useEffect(() => {
    if (currentWorkflow) {
      const mockExecution: Execution = {
        id: `exec_${Date.now()}`,
        workflow_id: currentWorkflow.id,
        status: "running",
        started_at: new Date().toISOString(),
      };
      setExecutions([mockExecution]);
      setSelectedExecution(mockExecution);

      // Simulate completion
      setTimeout(() => {
        setExecutions((prev) =>
          prev.map((e) =>
            e.id === mockExecution.id
              ? {
                  ...e,
                  status: "completed",
                  completed_at: new Date().toISOString(),
                  result: { output: "Workflow completed successfully" },
                }
              : e
          )
        );
      }, 3000);
    }
  }, [currentWorkflow]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "running":
        return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return null;
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 h-80 bg-card border-t border-border shadow-lg">
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Execution History</h3>
          <button
            onClick={() => setShowExecutionPanel(false)}
            className="p-1 hover:bg-accent rounded"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 flex">
          {/* Execution list */}
          <div className="w-80 border-r border-border overflow-y-auto">
            {executions.map((execution) => (
              <div
                key={execution.id}
                className={`p-4 border-b border-border cursor-pointer hover:bg-accent ${
                  selectedExecution?.id === execution.id ? "bg-accent" : ""
                }`}
                onClick={() => setSelectedExecution(execution)}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">
                    {new Date(execution.started_at).toLocaleTimeString()}
                  </span>
                  {getStatusIcon(execution.status)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {execution.workflow_id}
                </div>
              </div>
            ))}
          </div>

          {/* Execution details */}
          <div className="flex-1 p-4 overflow-y-auto">
            {selectedExecution ? (
              <div>
                <h4 className="font-medium mb-4">Execution Details</h4>
                
                <div className="space-y-3">
                  <div>
                    <span className="text-sm font-medium">Status:</span>
                    <span className="ml-2 text-sm capitalize">
                      {selectedExecution.status}
                    </span>
                  </div>
                  
                  <div>
                    <span className="text-sm font-medium">Started:</span>
                    <span className="ml-2 text-sm">
                      {new Date(selectedExecution.started_at).toLocaleString()}
                    </span>
                  </div>
                  
                  {selectedExecution.completed_at && (
                    <div>
                      <span className="text-sm font-medium">Completed:</span>
                      <span className="ml-2 text-sm">
                        {new Date(selectedExecution.completed_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                  
                  {selectedExecution.result && (
                    <div>
                      <span className="text-sm font-medium">Result:</span>
                      <pre className="mt-2 p-3 bg-muted rounded text-xs overflow-x-auto">
                        {JSON.stringify(selectedExecution.result, null, 2)}
                      </pre>
                    </div>
                  )}
                  
                  {selectedExecution.error && (
                    <div>
                      <span className="text-sm font-medium text-destructive">
                        Error:
                      </span>
                      <pre className="mt-2 p-3 bg-destructive/10 rounded text-xs text-destructive">
                        {selectedExecution.error}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground text-center mt-8">
                Select an execution to view details
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}