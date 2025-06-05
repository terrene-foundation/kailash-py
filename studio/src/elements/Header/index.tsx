import React from "react";
import { Save, Play, Download, Upload, Settings } from "lucide-react";
import { useWorkflowStore } from "@/store/workflowStore";
import { useWorkflowApi } from "@/hooks/useWorkflowApi";
import { Button } from "@/components/Button";

export function Header() {
  const { currentWorkflow, isExecuting, setShowExecutionPanel } = useWorkflowStore();
  const { saveWorkflow, executeWorkflow, exportWorkflow } = useWorkflowApi();

  const handleSave = async () => {
    if (!currentWorkflow) return;
    await saveWorkflow(currentWorkflow);
  };

  const handleExecute = async () => {
    if (!currentWorkflow || isExecuting) return;
    setShowExecutionPanel(true);
    await executeWorkflow(currentWorkflow.id);
  };

  const handleExport = async (format: "python" | "yaml") => {
    if (!currentWorkflow) return;
    await exportWorkflow(currentWorkflow.id, format);
  };

  return (
    <header className="h-16 bg-card border-b border-border px-4 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold">Kailash Workflow Studio</h1>
        {currentWorkflow && (
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">|</span>
            <span className="font-medium">{currentWorkflow.name}</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleSave}
          disabled={!currentWorkflow}
        >
          <Save className="h-4 w-4 mr-2" />
          Save
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={handleExecute}
          disabled={!currentWorkflow || isExecuting}
        >
          <Play className="h-4 w-4 mr-2" />
          {isExecuting ? "Running..." : "Run"}
        </Button>

        <div className="relative group">
          <Button
            variant="ghost"
            size="sm"
            disabled={!currentWorkflow}
          >
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <div className="absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-popover border border-border opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
            <div className="py-1">
              <button
                className="block w-full text-left px-4 py-2 text-sm hover:bg-accent"
                onClick={() => handleExport("python")}
              >
                Export as Python
              </button>
              <button
                className="block w-full text-left px-4 py-2 text-sm hover:bg-accent"
                onClick={() => handleExport("yaml")}
              >
                Export as YAML
              </button>
            </div>
          </div>
        </div>

        <Button variant="ghost" size="sm">
          <Upload className="h-4 w-4 mr-2" />
          Import
        </Button>

        <Button variant="ghost" size="sm">
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}