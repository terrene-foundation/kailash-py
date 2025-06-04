# MCP Ecosystem Demo - What You'll See

When you run `python mcp_ecosystem_demo.py`, you'll get a fully interactive web interface at http://localhost:8000 with these features:

## 🌐 Web Interface Features

### 1. **Live Statistics Dashboard**
Real-time metrics showing:
- Total Workflows deployed
- Currently Running workflows
- Completed workflows

### 2. **MCP Server Status Panel**
Shows connected MCP servers with their available tools:
- **github-mcp**: 3 tools (list_issues, create_pr, list_repos)
- **slack-mcp**: 2 tools (send_message, list_channels)  
- **filesystem-mcp**: 3 tools (read_file, write_file, list_files)

### 3. **Workflow Templates**
Pre-built workflows you can deploy with one click:

#### GitHub → Slack Notifier
- Monitors GitHub issues
- Sends notifications to Slack
- Click "Deploy Workflow" to activate

#### Data Processing Pipeline  
- Reads CSV files
- Transforms data with Python
- Saves as JSON
- Click "Deploy Workflow" to activate

#### AI Research Assistant
- Searches the web
- Summarizes findings
- Saves results to file
- Click "Deploy Workflow" to activate

### 4. **Visual Workflow Builder** 🎨
A fully functional drag-and-drop interface:
- **Node Palette**: Drag nodes from the left panel
  - 📄 CSV Reader
  - 🐍 Python Code
  - 💾 JSON Writer
  - 🐙 GitHub Issues
  - 💬 Slack Message
- **Canvas**: Drop nodes to build your workflow
- **Deploy Button**: Deploy your custom workflow instantly

### 5. **Live Execution Logs**
Real-time log viewer showing:
- Node additions
- Deployment status
- Execution updates
- Error messages

## 🚀 How to Run

1. **Start the server:**
   ```bash
   python mcp_ecosystem_demo.py
   ```

2. **Open your browser to:**
   ```
   http://localhost:8000
   ```

3. **Click any "Deploy Workflow" button** to instantly deploy that workflow

4. **Check the API docs at:**
   ```
   http://localhost:8000/docs
   ```

## 📡 API Endpoints

- `GET /` - Web UI
- `GET /api/servers` - List MCP servers
- `POST /api/deploy/{workflow_id}` - Deploy a workflow
- `GET /api/workflows` - List deployed workflows

## 💡 Key Features Demonstrated

1. **Zero-Code Deployment**: Deploy complex workflows without writing any code
2. **MCP Integration**: Seamless integration with MCP servers
3. **Visual Interface**: User-friendly web UI
4. **One-Click Deploy**: Instant workflow deployment
5. **Real-Time Status**: Live server and workflow status updates

## 🔧 Under the Hood

The ecosystem uses:
- **Kailash SDK** for workflow execution
- **FastAPI** for the web interface and API
- **MCP Protocol** for tool integration
- **HTML/JavaScript** for the interactive UI

This demo shows how the Kailash SDK can be used to build a complete zero-code workflow platform that makes advanced automation accessible to everyone!