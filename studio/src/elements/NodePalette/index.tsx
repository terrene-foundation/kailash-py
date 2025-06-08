import React, { useState } from "react";
import { NODE_CATEGORIES } from "../../store/workflowStore";
import NodeCard from "./NodeCard";

export function NodePalette() {
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(Object.keys(NODE_CATEGORIES))
  );

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const filteredCategories = Object.entries(NODE_CATEGORIES).reduce(
    (acc, [category, data]) => {
      const filteredNodes = data.nodes.filter((node) =>
        node.toLowerCase().includes(searchTerm.toLowerCase())
      );
      if (filteredNodes.length > 0) {
        acc[category] = { ...data, nodes: filteredNodes };
      }
      return acc;
    },
    {} as typeof NODE_CATEGORIES
  );

  return (
    <aside className="node-palette">
      <div className="palette-header">
        <h3>Node Library</h3>
        <div className="search-container">
          <input
            type="text"
            placeholder="Search nodes..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="node-search"
          />
        </div>
      </div>

      <div className="node-categories">
        {Object.entries(filteredCategories).map(([category, data]) => (
          <div key={category} className="node-category">
            <div
              className="category-header"
              onClick={() => toggleCategory(category)}
              style={{ cursor: "pointer" }}
            >
              <span className="category-icon">{data.icon}</span>
              <span className="category-name">{category}</span>
              <span className="category-count">({data.nodes.length})</span>
              <span className="category-toggle">
                {expandedCategories.has(category) ? "▼" : "▶"}
              </span>
            </div>

            {expandedCategories.has(category) && (
              <div className="category-nodes">
                {data.nodes.map((nodeType) => (
                  <NodeCard
                    key={nodeType}
                    nodeType={nodeType}
                    category={category}
                    icon={data.icon}
                    color={data.color}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
