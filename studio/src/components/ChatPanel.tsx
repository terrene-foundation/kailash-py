import { useState, KeyboardEvent } from "react";

interface Message {
  id: string;
  type: "user" | "assistant";
  content: string;
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      type: "assistant",
      content: `Hi! I can help you build workflows using natural language. Try saying something like "Create a workflow that reads customer data from CSV, filters active customers, and sends them to our API."`,
    },
  ]);
  const [input, setInput] = useState("");

  const sendMessage = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: input,
    };

    setMessages([...messages, userMessage]);
    setInput("");

    // Simulate AI response
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: "assistant",
        content: `I'll help you create an intelligent workflow for that! I can build this using proven orchestration patterns:

🔗 **Prompt Chain Pattern:**
Input → Data Analysis Agent → Customer Segmentation Agent → Action Recommendation Agent → Output

⚡ **Parallel Pattern:**
Split data analysis across multiple specialized agents for faster processing

🚦 **Router Pattern:**
Let an intelligent router decide which analysis path to take based on data characteristics

Which pattern interests you? I can auto-generate the workflow with proper LLM decision nodes and tool integrations.`,
      };
      setMessages((prev) => [...prev, aiMessage]);
    }, 1000);
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const quickActions = [
    "Generate workflow",
    "Optimize pipeline",
    "Debug issues",
    "Add monitoring",
  ];

  return (
    <section className="chat-panel">
      <div className="chat-header">
        <div className="chat-title">AI Workflow Assistant</div>
        <div className="chat-subtitle">Get help building and optimizing workflows</div>
      </div>

      <div className="chat-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.type}`}>
            {message.type === "assistant" && <strong>Kailash AI: </strong>}
            <span dangerouslySetInnerHTML={{ __html: message.content.replace(/\n/g, "<br>") }} />
          </div>
        ))}
      </div>

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          placeholder="Ask me anything about building workflows..."
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
        />
        <div className="chat-actions">
          {quickActions.map((action) => (
            <div
              key={action}
              className="quick-action"
              onClick={() => {
                setInput(action);
                sendMessage();
              }}
            >
              {action}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
