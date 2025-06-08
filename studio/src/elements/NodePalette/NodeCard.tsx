import React from "react";

interface NodeCardProps {
  nodeType: string;
  category: string;
  icon: string;
  color: string;
}

const NodeCard: React.FC<NodeCardProps> = ({ nodeType, category, icon, color }) => {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData("application/reactflow", nodeType);
    event.dataTransfer.effectAllowed = "move";
  };

  const displayName = nodeType.replace("Node", "");

  return (
    <div
      className="node-card"
      draggable
      onDragStart={onDragStart}
      style={{
        borderLeft: `3px solid ${color}`,
      }}
    >
      <span className="node-card-icon">{icon}</span>
      <span className="node-card-name">{displayName}</span>
    </div>
  );
};

export default NodeCard;
