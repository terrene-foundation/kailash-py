# Code Review Agent

## Overview

Automated code review agent that analyzes Python codebases using file tools with intelligent permission policies. The agent reads multiple files, checks for common issues, and generates comprehensive review reports with actionable suggestions.

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen
```

## Usage

```bash
python code_review_agent.py /path/to/codebase
```

Example:
```bash
python code_review_agent.py ~/projects/my-python-app
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              CODE REVIEW AGENT                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐        ┌───────────────────┐   │
│  │ Control Protocol │◄──────►│  Permission       │   │
│  │ (Memory)         │        │  System           │   │
│  └──────────────────┘        └───────────────────┘   │
│          │                            │               │
│          │                            │               │
│          ▼                            ▼               │
│  ┌──────────────────────────────────────────────┐   │
│  │         BaseAutonomousAgent                  │   │
│  │  - Read files with permission checks         │   │
│  │  - Analyze code quality                      │   │
│  │  - Report findings with line numbers         │   │
│  │  - Progress updates via Control Protocol     │   │
│  └──────────────────────────────────────────────┘   │
│          │                                           │
│          ▼                                           │
│  ┌──────────────────────────────────────────────┐   │
│  │         MCP Tools (12 Builtin)               │   │
│  │  - read_file (ALLOWED)                       │   │
│  │  - list_directory (ALLOWED)                  │   │
│  │  - file_exists (ALLOWED)                     │   │
│  │  - write_file (ASK for approval)             │   │
│  │  - bash_command (DENIED)                     │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Permission Policies

The agent enforces strict permission policies for security:

| Tool Pattern | Permission | Reason |
|--------------|------------|--------|
| `read_file`, `list_directory`, `file_exists` | **ALLOW** | Read operations are safe |
| `write_file`, `delete_file` | **ASK** | Write operations require approval |
| `bash_command` | **DENY** | Bash commands not allowed during review |

## Expected Output

```
============================================================
🤖 CODE REVIEW AGENT
============================================================
📂 Codebase: /Users/user/projects/my-app
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
🔒 Permissions: Read (ALLOW), Write (ASK), Bash (DENY)
============================================================

🔍 Starting code review of: /Users/user/projects/my-app

📂 Found 15 Python files

============================================================
📊 CODE REVIEW REPORT
============================================================

📄 src/main.py:
  - Line 23: Line too long (112 chars)
  - Line 45: Function missing docstring
  - Line 67: Bare except clause (use specific exceptions)

📄 src/utils.py:
  - Line 10: Function missing docstring
  - Line 34: Line too long (105 chars)

📄 tests/test_main.py:
  - Line 15: Function missing docstring

📈 Issues Found: 6

💡 Suggestions:
  - Follow PEP 8 style guide (line length < 100 chars)
  - Add docstrings to all functions and classes
  - Use specific exception types instead of bare except
  - Add type hints for better code clarity
  - Run pylint or flake8 for comprehensive analysis
============================================================

💰 Cost: $0.00 (using Ollama local inference)
📊 Budget Used: $0.000
📊 Budget Remaining: $10.000
```

## Features

### 1. File Tool Integration
- **read_file**: Read file contents with permission checks
- **list_directory**: List files in directory
- **file_exists**: Check file existence before reading

### 2. Permission System
- **ExecutionContext**: Budget tracking and tool restrictions
- **PermissionRules**: Pattern-based access control with priorities
- **Permission Types**: ALLOW (auto-approve), ASK (user approval), DENY (block)

### 3. Error Handling
- Graceful fallback when files can't be read
- Budget enforcement ($10 limit)
- Permission denial handling
- Encoding error handling

### 4. Progress Reporting
- Real-time progress updates via Control Protocol
- File-by-file progress tracking
- Percentage completion reporting

## Code Quality Checks

The agent performs the following checks:

1. **Line Length**: Lines > 100 characters
2. **Missing Docstrings**: Functions without docstrings
3. **Bare Except Clauses**: Use of `except:` without specific exception types
4. **PEP 8 Compliance**: Basic style guide checks

## Troubleshooting

### Issue: "Ollama connection refused"
**Solution**: Make sure Ollama is running:
```bash
ollama serve
```

### Issue: "Model not found"
**Solution**: Pull the model first:
```bash
ollama pull llama3.1:8b-instruct-q8_0
```

### Issue: "Permission denied to read files"
**Solution**: Check that the codebase path exists and is readable:
```bash
ls -la /path/to/codebase
```

### Issue: "No Python files found"
**Solution**: Verify the path contains Python files:
```bash
find /path/to/codebase -name "*.py"
```

## Production Notes

### Deployment Considerations

1. **Scalability**:
   - Limit file count for large codebases (currently limited to 10 files)
   - Use parallel processing for faster reviews
   - Implement file caching to avoid re-reading

2. **Security**:
   - Permission policies prevent unauthorized file modifications
   - Budget limits prevent runaway costs
   - Read-only operations are safe and fast

3. **Monitoring**:
   - Track budget usage for cost control
   - Monitor permission denials for security auditing
   - Log all file access for compliance

4. **Scaling Up**:
   - Use GPT-4 for more sophisticated analysis
   - Integrate with static analysis tools (pylint, flake8)
   - Add custom rule sets for project-specific checks
   - Generate actionable diffs with fix suggestions

### Cost Analysis

**Ollama (FREE):**
- $0.00 per review
- Unlimited reviews
- Local inference (no network required)
- Good for development and testing

**GPT-4 (Paid):**
- ~$0.10 per review (100 files)
- Better accuracy and suggestions
- Cloud API (requires network)
- Good for production

## Next Steps

1. **Extend Analysis**: Add more code quality checks (complexity, security, performance)
2. **Integration**: Connect with CI/CD pipelines for automated reviews
3. **Custom Rules**: Define project-specific linting rules
4. **Fix Generation**: Generate automated fixes for common issues
5. **Report Export**: Export reports to JSON/HTML/PDF formats

## Related Examples

- [Data Analysis Agent](../data-analysis-agent/) - HTTP tools with statistical analysis
- [DevOps Agent](../devops-agent/) - Bash commands with danger-level approval
- [Tool Calling Basics](../../tools/) - Basic MCP tool integration patterns
