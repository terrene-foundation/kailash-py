import React from "react";
import { WorkflowProvider } from "./store/workflowStore";
import { NodePalette } from "./elements/NodePalette";
import { WorkflowCanvas } from "./elements/WorkflowCanvas";
import { PropertyPanel } from "./elements/PropertyPanel";
import { ExecutionPanel } from "./elements/ExecutionPanel";
import { Header } from "./elements/Header";
import { useWorkflowStore } from "./store/workflowStore";

function AppContent() {
  const { showExecutionPanel } = useWorkflowStore();

  return (
    <div className="flex flex-col h-screen bg-background">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <NodePalette />
        <WorkflowCanvas />
        <PropertyPanel />
      </div>
      {showExecutionPanel && <ExecutionPanel />}
    </div>
  );
}

function App() {
  return (
    <WorkflowProvider>
      <AppContent />
    </WorkflowProvider>
  );
}

export default App;