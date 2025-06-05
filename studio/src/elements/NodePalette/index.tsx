import React, { useEffect, useState } from "react";
import { Search, ChevronRight, ChevronDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useWorkflowStore, NodeDefinition } from "@/store/workflowStore";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { NodeCard } from "./NodeCard";

export function NodePalette() {
  const { nodeCategories, setNodeCategories } = useWorkflowStore();
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set()
  );

  // Fetch node definitions from API
  const { isPending, error, data } = useQuery({
    queryKey: ["nodes"],
    queryFn: () =>
      fetch("/api/nodes").then((res) => {
        if (!res.ok) throw new Error("Failed to fetch nodes");
        return res.json();
      }),
  });

  useEffect(() => {
    if (data) {
      setNodeCategories(data);
      // Expand all categories by default
      setExpandedCategories(new Set(Object.keys(data)));
    }
  }, [data, setNodeCategories]);

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const filteredCategories = React.useMemo(() => {
    if (!searchTerm) return nodeCategories;

    const filtered: Record<string, NodeDefinition[]> = {};
    
    Object.entries(nodeCategories).forEach(([category, nodes]) => {
      const matchingNodes = nodes.filter(
        (node) =>
          node.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          node.description.toLowerCase().includes(searchTerm.toLowerCase())
      );
      
      if (matchingNodes.length > 0) {
        filtered[category] = matchingNodes;
      }
    });

    return filtered;
  }, [nodeCategories, searchTerm]);

  if (isPending) return <LoadingSkeleton />;

  if (error) {
    return (
      <div className="w-64 bg-card border-r border-border p-4">
        <div className="text-destructive">
          Failed to load nodes: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 bg-card border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <h2 className="text-lg font-semibold mb-3">Node Palette</h2>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search nodes..."
            className="w-full pl-10 pr-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {Object.entries(filteredCategories).map(([category, nodes]) => (
          <div key={category} className="border-b border-border">
            <button
              className="w-full px-4 py-2 flex items-center justify-between hover:bg-accent transition-colors"
              onClick={() => toggleCategory(category)}
            >
              <span className="font-medium capitalize">{category}</span>
              {expandedCategories.has(category) ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>

            {expandedCategories.has(category) && (
              <div className="px-2 py-2 space-y-1">
                {nodes.map((node) => (
                  <NodeCard key={node.id} node={node} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}