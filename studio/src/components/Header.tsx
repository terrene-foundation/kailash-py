import { useWorkflowStore } from "../store/workflowStore";

export function Header() {
  const { setShowToolModal } = useWorkflowStore();

  return (
    <header className="header">
      <div className="logo">Kailash Workflow Studio</div>
      <div className="header-controls">
        <button className="btn">New Workflow</button>
        <button className="btn">Import</button>
        <button className="btn">Export</button>
        <button className="btn" onClick={() => setShowToolModal(true)}>
          🔌 Tools
        </button>
        <button className="btn btn-primary">Deploy</button>
      </div>
    </header>
  );
}
