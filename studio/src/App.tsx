import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./styles/globals.css";

// Import components
import { Header } from "./elements/Header";
import { NodePalette } from "./elements/NodePalette";
import { WorkflowCanvas } from "./components/WorkflowCanvas";
import { PropertiesPanel } from "./components/PropertiesPanel";
import { ExecutionPanel } from "./elements/ExecutionPanel";

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute
      retry: 3,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="app-container">
        <Header />
        <NodePalette />
        <WorkflowCanvas />
        <PropertiesPanel />
        <ExecutionPanel />
      </div>
    </QueryClientProvider>
  );
}

export default App;
