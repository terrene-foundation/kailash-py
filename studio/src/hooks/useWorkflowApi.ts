import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Workflow } from "@/store/workflowStore";

export function useWorkflowApi() {
  const queryClient = useQueryClient();

  const saveWorkflow = useMutation({
    mutationFn: async (workflow: Workflow) => {
      const response = await fetch(`/api/workflows/${workflow.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: workflow.name,
          description: workflow.description,
          definition: {
            nodes: workflow.nodes,
            edges: workflow.edges,
          },
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to save workflow");
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });

  const executeWorkflow = useMutation({
    mutationFn: async (workflowId: string) => {
      const response = await fetch(`/api/workflows/${workflowId}/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          parameters: {},
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to execute workflow");
      }

      return response.json();
    },
  });

  const exportWorkflow = useMutation({
    mutationFn: async ({
      workflowId,
      format,
    }: {
      workflowId: string;
      format: "python" | "yaml";
    }) => {
      const response = await fetch(
        `/api/workflows/${workflowId}/export?format=${format}`
      );

      if (!response.ok) {
        throw new Error("Failed to export workflow");
      }

      const data = await response.json();

      // Create download
      const blob = new Blob([data.content], { type: "text/plain" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `workflow.${format === "python" ? "py" : "yaml"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      return data;
    },
  });

  return {
    saveWorkflow: saveWorkflow.mutate,
    executeWorkflow: executeWorkflow.mutate,
    exportWorkflow: (workflowId: string, format: "python" | "yaml") =>
      exportWorkflow.mutate({ workflowId, format }),
    isSaving: saveWorkflow.isPending,
    isExecuting: executeWorkflow.isPending,
    isExporting: exportWorkflow.isPending,
  };
}
