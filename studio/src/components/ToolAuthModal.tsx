import { useState } from "react";
import { useWorkflowStore } from "../store/workflowStore";

interface Tool {
  id: string;
  name: string;
  category: string;
  description: string;
  icon: string;
  bgColor: string;
  isConnected: boolean;
  authType?: "oauth" | "apikey" | "token";
}

const tools: Tool[] = [
  {
    id: "slack",
    name: "Slack",
    category: "Communication",
    description: "Send messages, create channels, manage workspace",
    icon: "💬",
    bgColor: "#4A154B",
    isConnected: true,
  },
  {
    id: "gmail",
    name: "Gmail",
    category: "Email",
    description: "Send emails, read inbox, manage labels",
    icon: "📧",
    bgColor: "#EA4335",
    isConnected: false,
    authType: "oauth",
  },
  {
    id: "notion",
    name: "Notion",
    category: "Productivity",
    description: "Create pages, update databases, manage content",
    icon: "📝",
    bgColor: "#000",
    isConnected: false,
    authType: "apikey",
  },
  {
    id: "github",
    name: "GitHub",
    category: "Development",
    description: "Manage repositories, create issues, review PRs",
    icon: "🐙",
    bgColor: "#181717",
    isConnected: false,
    authType: "token",
  },
  {
    id: "airtable",
    name: "Airtable",
    category: "Database",
    description: "Create records, query bases, manage data",
    icon: "📊",
    bgColor: "#18BFFF",
    isConnected: false,
    authType: "apikey",
  },
  {
    id: "discord",
    name: "Discord",
    category: "Communication",
    description: "Send messages, manage servers, create channels",
    icon: "🎮",
    bgColor: "#5865F2",
    isConnected: false,
    authType: "token",
  },
];

export function ToolAuthModal() {
  const { setShowToolModal } = useWorkflowStore();
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedTool, setExpandedTool] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});

  const filteredTools = tools.filter(
    (tool) =>
      tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tool.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleConnect = (toolId: string, authType?: string) => {
    if (authType === "oauth") {
      // Simulate OAuth flow
      window.open(`/auth/${toolId}`, "auth", "width=500,height=600");
      setTimeout(() => {
        // Update connection status
        console.log(`Connected to ${toolId}`);
      }, 2000);
    } else {
      // Handle API key/token auth
      const key = apiKeys[toolId];
      if (key) {
        console.log(`Connecting to ${toolId} with key: ${key}`);
        setExpandedTool(null);
      }
    }
  };

  return (
    <div className="modal-overlay" onClick={() => setShowToolModal(false)}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">🔌 Tool Integrations</div>
          <button className="close-btn" onClick={() => setShowToolModal(false)}>
            ×
          </button>
        </div>

        <div style={{ padding: "20px", borderBottom: "1px solid #333" }}>
          <input
            type="text"
            className="property-input"
            placeholder="Search tools..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: "100%" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "15px", padding: "20px" }}>
          {filteredTools.map((tool) => (
            <div
              key={tool.id}
              className={`tool-card ${tool.isConnected ? "connected" : ""}`}
              onClick={() => !tool.isConnected && setExpandedTool(tool.id === expandedTool ? null : tool.id)}
              style={{
                background: "#252525",
                border: tool.isConnected ? "1px solid #28a745" : "1px solid #333",
                borderRadius: "8px",
                padding: "15px",
                cursor: tool.isConnected ? "default" : "pointer",
                transition: "all 0.2s ease",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
                <div
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "6px",
                    background: tool.bgColor,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {tool.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "14px", fontWeight: 600, marginBottom: "2px" }}>
                    {tool.name}
                  </div>
                  <div style={{ fontSize: "11px", color: "#888", textTransform: "uppercase" }}>
                    {tool.category}
                  </div>
                </div>
                <div
                  style={{
                    padding: "4px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 500,
                    textTransform: "uppercase",
                    background: tool.isConnected ? "#28a745" : "#6c757d",
                    color: "white",
                  }}
                >
                  {tool.isConnected ? "Connected" : "Disconnected"}
                </div>
              </div>
              <div style={{ fontSize: "12px", color: "#ccc", lineHeight: 1.4, marginBottom: "10px" }}>
                {tool.description}
              </div>

              {expandedTool === tool.id && !tool.isConnected && (
                <div style={{ marginTop: "15px", paddingTop: "15px", borderTop: "1px solid #333" }}>
                  <div style={{ fontSize: "12px", color: "#888", marginBottom: "10px" }}>
                    {tool.authType === "oauth" && "OAuth2 Authentication"}
                    {tool.authType === "apikey" && "API Key Authentication"}
                    {tool.authType === "token" && "Personal Access Token"}
                  </div>
                  {tool.authType === "oauth" ? (
                    <button
                      className="btn btn-primary"
                      style={{ width: "100%" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleConnect(tool.id, tool.authType);
                      }}
                    >
                      Connect with {tool.name}
                    </button>
                  ) : (
                    <>
                      <input
                        type="password"
                        className="property-input"
                        placeholder={`Enter ${tool.name} ${tool.authType === "apikey" ? "API Key" : "Token"}`}
                        value={apiKeys[tool.id] || ""}
                        onChange={(e) => setApiKeys({ ...apiKeys, [tool.id]: e.target.value })}
                        onClick={(e) => e.stopPropagation()}
                        style={{ marginBottom: "10px" }}
                      />
                      <button
                        className="btn btn-primary"
                        style={{ width: "100%" }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleConnect(tool.id, tool.authType);
                        }}
                      >
                        Connect
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
