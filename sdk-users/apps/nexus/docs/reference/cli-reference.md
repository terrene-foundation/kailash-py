# CLI Reference

Complete command-line interface reference for Nexus's workflow-native platform, covering all commands, options, flags, and interactive modes.

## Overview

Nexus automatically generates a comprehensive CLI interface for every registered workflow, providing command-line access to the full platform capabilities. This reference covers all built-in commands, workflow operations, and advanced CLI features.

## Core CLI Commands

### Application Management

```bash
#!/bin/bash

# Nexus Core CLI Commands Reference

# 1. Application Lifecycle
nexus start                          # Start Nexus platform
nexus start --port 8080             # Start on specific port
nexus start --host 0.0.0.0         # Start on all interfaces
nexus start --workers 8            # Start with specific worker count
nexus start --config production.yaml # Start with config file
nexus start --daemon               # Start as daemon process

nexus stop                          # Stop Nexus platform
nexus stop --force                 # Force stop platform
nexus stop --timeout 30            # Stop with timeout

nexus restart                       # Restart platform
nexus restart --graceful           # Graceful restart with zero downtime

nexus status                        # Get platform status
nexus status --json               # Status in JSON format
nexus status --detailed           # Detailed status information

# 2. Health and Monitoring
nexus health                        # Basic health check
nexus health --verbose             # Detailed health information
nexus health --json               # Health status in JSON

nexus metrics                       # Display system metrics
nexus metrics --prometheus        # Prometheus format metrics
nexus metrics --export metrics.json # Export metrics to file

nexus logs                          # Show recent logs
nexus logs --follow               # Follow logs in real-time
nexus logs --level ERROR          # Filter by log level
nexus logs --lines 100            # Show last 100 lines
nexus logs --since "1 hour ago"   # Show logs since time

# 3. Configuration Management
nexus config show                   # Show current configuration
nexus config validate             # Validate configuration
nexus config export config.yaml   # Export configuration
nexus config import config.yaml   # Import configuration
nexus config set app.debug true   # Set configuration value
nexus config get database.url     # Get configuration value

# 4. Workflow Management
nexus workflows list               # List all registered workflows
nexus workflows list --json       # List in JSON format
nexus workflows list --verbose    # Detailed workflow information

nexus workflows info <workflow>   # Get workflow details
nexus workflows info data-processor --json

nexus workflows register          # Register new workflow
nexus workflows register --file workflow.yaml
nexus workflows register --name "my-workflow" --version "1.0.0"

nexus workflows unregister <workflow> # Unregister workflow
nexus workflows unregister data-processor

# 5. Workflow Execution
nexus execute <workflow>           # Execute workflow
nexus execute data-processor      # Execute specific workflow
nexus execute data-processor --input '{"file": "data.csv"}'
nexus execute data-processor --input-file input.json
nexus execute data-processor --session-id session_123
nexus execute data-processor --async  # Asynchronous execution
nexus execute data-processor --timeout 300 # Set timeout
nexus execute data-processor --retry 3     # Set retry count

# 6. Execution Management
nexus executions list             # List recent executions
nexus executions list --limit 50 # Limit results
nexus executions list --status running # Filter by status
nexus executions list --workflow data-processor # Filter by workflow

nexus executions show <execution-id> # Show execution details
nexus executions show exec_12345 --logs # Include logs
nexus executions show exec_12345 --json # JSON format

nexus executions cancel <execution-id> # Cancel execution
nexus executions retry <execution-id>  # Retry failed execution

nexus executions cleanup           # Clean up old executions
nexus executions cleanup --older-than "7 days"

# 7. Session Management
nexus sessions list               # List active sessions
nexus sessions show <session-id> # Show session details
nexus sessions end <session-id>  # End session
nexus sessions cleanup           # Clean up expired sessions

# 8. User and Authentication
nexus auth login                  # Login to platform
nexus auth login --username admin --password secret
nexus auth logout                # Logout from platform
nexus auth whoami                # Show current user
nexus auth token                 # Show authentication token
nexus auth refresh               # Refresh authentication token

# 9. Development and Debugging
nexus dev                        # Enter development mode
nexus dev --watch               # Watch for changes
nexus dev --reload              # Auto-reload on changes
nexus dev --debug               # Enable debug mode

nexus debug                      # Debug utilities
nexus debug --workflow data-processor # Debug specific workflow
nexus debug --execution exec_123      # Debug execution
nexus debug --trace               # Enable detailed tracing

# 10. Data and File Operations
nexus data list                  # List available data
nexus data upload file.csv      # Upload data file
nexus data download output.json # Download result file
nexus data clean                # Clean temporary data

# 11. Plugin and Extension Management
nexus plugins list              # List installed plugins
nexus plugins install <plugin> # Install plugin
nexus plugins uninstall <plugin> # Uninstall plugin
nexus plugins update <plugin>   # Update plugin

# 12. Export and Import
nexus export                    # Export platform state
nexus export --workflows       # Export only workflows
nexus export --data           # Export data
nexus export --config         # Export configuration

nexus import backup.tar.gz     # Import platform state
nexus import --workflows workflows.yaml
nexus import --validate       # Validate before import

# 13. Performance and Optimization
nexus optimize                  # Optimize platform
nexus optimize --workflows     # Optimize workflow performance
nexus optimize --database     # Optimize database
nexus optimize --cache        # Optimize cache

nexus benchmark                # Run performance benchmarks
nexus benchmark --workflow data-processor
nexus benchmark --concurrent 10

# 14. Help and Documentation
nexus help                     # Show general help
nexus help <command>          # Show command-specific help
nexus help execute            # Help for execute command

nexus version                  # Show version information
nexus version --verbose       # Detailed version info

# 15. Advanced Operations
nexus admin                    # Admin utilities
nexus admin --backup          # Create backup
nexus admin --restore backup.tar.gz # Restore from backup
nexus admin --maintenance     # Enter maintenance mode
nexus admin --users           # User management

nexus cluster                  # Cluster operations (enterprise)
nexus cluster status         # Cluster status
nexus cluster join <node>    # Join cluster
nexus cluster leave          # Leave cluster
```

### Interactive CLI Mode

```python
# nexus_cli_interactive.py - Interactive CLI implementation
import sys
import os
import json
import argparse
import cmd
import readline
import atexit
from typing import Dict, Any, List, Optional
from pathlib import Path
import time
from datetime import datetime

class NexusInteractiveCLI(cmd.Cmd):
    """Interactive CLI for Nexus platform"""

    intro = """
╔══════════════════════════════════════════════════════════════╗
║                    Nexus Interactive CLI                     ║
║              Workflow-Native Platform Console               ║
╚══════════════════════════════════════════════════════════════╝

Type 'help' for available commands or 'help <command>' for specific help.
Type 'exit' or 'quit' to leave the interactive session.
    """

    prompt = "(nexus) "

    def __init__(self):
        super().__init__()
        self.nexus_connected = False
        self.current_session = None
        self.command_history = []
        self.aliases = {
            'ls': 'workflows list',
            'ps': 'executions list',
            'top': 'status',
            'q': 'quit',
            'exit': 'quit'
        }

        # Setup command completion
        self._setup_completion()

        # Load history
        self._load_history()
        atexit.register(self._save_history)

    def _setup_completion(self):
        """Setup command completion"""

        # Enable tab completion
        if hasattr(readline, 'parse_and_bind'):
            readline.parse_and_bind('tab: complete')

        # Set history file
        self.histfile = os.path.expanduser("~/.nexus_history")

    def _load_history(self):
        """Load command history"""
        try:
            if os.path.exists(self.histfile):
                readline.read_history_file(self.histfile)
        except:
            pass

    def _save_history(self):
        """Save command history"""
        try:
            readline.write_history_file(self.histfile)
        except:
            pass

    def precmd(self, line):
        """Process command before execution"""

        # Handle aliases
        parts = line.strip().split()
        if parts and parts[0] in self.aliases:
            line = self.aliases[parts[0]] + ' ' + ' '.join(parts[1:])

        # Record command
        if line.strip():
            self.command_history.append({
                'command': line,
                'timestamp': datetime.now().isoformat()
            })

        return line

    def emptyline(self):
        """Handle empty line"""
        pass

    def do_connect(self, args):
        """Connect to Nexus platform
        Usage: connect [host:port]
        """

        if not args:
            host_port = "localhost:8000"
        else:
            host_port = args

        try:
            # Simulate connection
            print(f"Connecting to Nexus at {host_port}...")
            time.sleep(0.5)

            self.nexus_connected = True
            self.prompt = f"(nexus@{host_port}) "

            print(f"✅ Connected to Nexus platform at {host_port}")

            # Show platform info
            self._show_platform_info()

        except Exception as e:
            print(f"❌ Failed to connect: {e}")

    def do_disconnect(self, args):
        """Disconnect from Nexus platform"""

        if self.nexus_connected:
            self.nexus_connected = False
            self.prompt = "(nexus) "
            print("Disconnected from Nexus platform")
        else:
            print("Not connected to any platform")

    def do_status(self, args):
        """Show platform status
        Usage: status [--json] [--detailed]
        """

        if not self.nexus_connected:
            print("Not connected to Nexus platform. Use 'connect' first.")
            return

        show_json = '--json' in args
        show_detailed = '--detailed' in args

        # Simulate status check
        status_data = {
            "status": "healthy",
            "uptime": "2 hours 15 minutes",
            "version": "1.0.0",
            "workflows": 5,
            "active_executions": 3,
            "total_executions": 142,
            "success_rate": 98.5
        }

        if show_json:
            print(json.dumps(status_data, indent=2))
        else:
            print("📊 Platform Status")
            print(f"   Status: {status_data['status']}")
            print(f"   Uptime: {status_data['uptime']}")
            print(f"   Version: {status_data['version']}")
            print(f"   Workflows: {status_data['workflows']}")
            print(f"   Active Executions: {status_data['active_executions']}")
            print(f"   Total Executions: {status_data['total_executions']}")
            print(f"   Success Rate: {status_data['success_rate']}%")

            if show_detailed:
                print("\n🔧 Detailed Information")
                print("   Database: Connected")
                print("   Redis: Connected")
                print("   API Server: Running")
                print("   WebSocket: Active")
                print("   Monitoring: Enabled")

    def do_workflows(self, args):
        """Workflow management commands
        Usage: workflows <subcommand> [options]
        Subcommands: list, info, register, unregister
        """

        if not self.nexus_connected:
            print("Not connected to Nexus platform. Use 'connect' first.")
            return

        parts = args.split()
        if not parts:
            print("Usage: workflows <subcommand> [options]")
            print("Subcommands: list, info, register, unregister")
            return

        subcommand = parts[0]

        if subcommand == 'list':
            self._workflows_list(parts[1:])
        elif subcommand == 'info':
            self._workflows_info(parts[1:])
        elif subcommand == 'register':
            self._workflows_register(parts[1:])
        elif subcommand == 'unregister':
            self._workflows_unregister(parts[1:])
        else:
            print(f"Unknown workflows subcommand: {subcommand}")

    def _workflows_list(self, args):
        """List workflows"""

        show_json = '--json' in args
        show_verbose = '--verbose' in args

        # Simulate workflow list
        workflows = [
            {
                "name": "data-processor",
                "version": "1.0.0",
                "status": "active",
                "executions": 45,
                "last_execution": "2024-01-15T10:30:00Z"
            },
            {
                "name": "api-handler",
                "version": "2.1.0",
                "status": "active",
                "executions": 89,
                "last_execution": "2024-01-15T11:45:00Z"
            },
            {
                "name": "analytics-engine",
                "version": "1.5.0",
                "status": "paused",
                "executions": 23,
                "last_execution": "2024-01-14T16:20:00Z"
            }
        ]

        if show_json:
            print(json.dumps(workflows, indent=2))
        else:
            print("📋 Registered Workflows")
            print("-" * 80)
            print(f"{'Name':<20} {'Version':<10} {'Status':<10} {'Executions':<12} {'Last Execution'}")
            print("-" * 80)

            for workflow in workflows:
                print(f"{workflow['name']:<20} {workflow['version']:<10} {workflow['status']:<10} {workflow['executions']:<12} {workflow['last_execution']}")

            if show_verbose:
                print(f"\nTotal workflows: {len(workflows)}")
                active_count = sum(1 for w in workflows if w['status'] == 'active')
                print(f"Active workflows: {active_count}")

    def _workflows_info(self, args):
        """Show workflow information"""

        if not args:
            print("Usage: workflows info <workflow-name>")
            return

        workflow_name = args[0]
        show_json = '--json' in args

        # Simulate workflow info
        workflow_info = {
            "name": workflow_name,
            "version": "1.0.0",
            "description": f"Information for {workflow_name}",
            "status": "active",
            "endpoints": {
                "api": f"/workflows/{workflow_name}/execute",
                "cli": f"nexus execute {workflow_name}",
                "mcp": f"execute_{workflow_name.replace('-', '_')}"
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "input_file": {"type": "string"},
                    "options": {"type": "object"}
                }
            },
            "statistics": {
                "total_executions": 45,
                "successful_executions": 44,
                "failed_executions": 1,
                "avg_execution_time_ms": 2500
            }
        }

        if show_json:
            print(json.dumps(workflow_info, indent=2))
        else:
            print(f"🔍 Workflow Information: {workflow_name}")
            print(f"   Version: {workflow_info['version']}")
            print(f"   Description: {workflow_info['description']}")
            print(f"   Status: {workflow_info['status']}")
            print("\n🌐 Endpoints:")
            for endpoint_type, endpoint in workflow_info['endpoints'].items():
                print(f"   {endpoint_type.upper()}: {endpoint}")
            print("\n📊 Statistics:")
            stats = workflow_info['statistics']
            print(f"   Total Executions: {stats['total_executions']}")
            print(f"   Success Rate: {(stats['successful_executions'] / stats['total_executions'] * 100):.1f}%")
            print(f"   Avg Execution Time: {stats['avg_execution_time_ms']}ms")

    def _workflows_register(self, args):
        """Register new workflow"""

        print("Workflow registration requires additional parameters")
        print("Use: nexus workflows register --file workflow.yaml")
        print("Or:  nexus workflows register --name 'my-workflow' --version '1.0.0'")

    def _workflows_unregister(self, args):
        """Unregister workflow"""

        if not args:
            print("Usage: workflows unregister <workflow-name>")
            return

        workflow_name = args[0]
        print(f"⚠️  Are you sure you want to unregister '{workflow_name}'? (y/N)")
        # In real implementation, would wait for user confirmation
        print(f"Workflow '{workflow_name}' would be unregistered")

    def do_execute(self, args):
        """Execute a workflow
        Usage: execute <workflow> [options]
        Options: --input <json>, --input-file <file>, --async, --timeout <seconds>
        """

        if not self.nexus_connected:
            print("Not connected to Nexus platform. Use 'connect' first.")
            return

        if not args:
            print("Usage: execute <workflow> [options]")
            return

        parts = args.split()
        workflow_name = parts[0]

        # Parse options
        options = {
            'input': None,
            'input_file': None,
            'async': '--async' in args,
            'timeout': None
        }

        # Extract input if provided
        if '--input' in args:
            input_index = parts.index('--input')
            if input_index + 1 < len(parts):
                options['input'] = parts[input_index + 1]

        print(f"🚀 Executing workflow: {workflow_name}")

        if options['async']:
            print("   Mode: Asynchronous")
        else:
            print("   Mode: Synchronous")

        # Simulate execution
        execution_id = f"exec_{int(time.time())}"

        if options['async']:
            print(f"   Execution ID: {execution_id}")
            print("   Status: Started")
            print(f"   Use 'executions show {execution_id}' to check progress")
        else:
            print("   Executing...")
            time.sleep(1)  # Simulate execution time
            print("   ✅ Execution completed successfully")
            print(f"   Execution ID: {execution_id}")
            print("   Result: Processing completed")

    def do_executions(self, args):
        """Execution management commands
        Usage: executions <subcommand> [options]
        Subcommands: list, show, cancel, retry, cleanup
        """

        if not self.nexus_connected:
            print("Not connected to Nexus platform. Use 'connect' first.")
            return

        parts = args.split()
        if not parts:
            print("Usage: executions <subcommand> [options]")
            print("Subcommands: list, show, cancel, retry, cleanup")
            return

        subcommand = parts[0]

        if subcommand == 'list':
            self._executions_list(parts[1:])
        elif subcommand == 'show':
            self._executions_show(parts[1:])
        elif subcommand == 'cancel':
            self._executions_cancel(parts[1:])
        elif subcommand == 'retry':
            self._executions_retry(parts[1:])
        elif subcommand == 'cleanup':
            self._executions_cleanup(parts[1:])
        else:
            print(f"Unknown executions subcommand: {subcommand}")

    def _executions_list(self, args):
        """List executions"""

        # Simulate execution list
        executions = [
            {
                "id": "exec_12345",
                "workflow": "data-processor",
                "status": "completed",
                "started": "2024-01-15T10:30:00Z",
                "duration": "2.5s"
            },
            {
                "id": "exec_12346",
                "workflow": "api-handler",
                "status": "running",
                "started": "2024-01-15T11:45:00Z",
                "duration": "1.2s"
            },
            {
                "id": "exec_12344",
                "workflow": "analytics-engine",
                "status": "failed",
                "started": "2024-01-15T09:15:00Z",
                "duration": "0.8s"
            }
        ]

        print("📋 Recent Executions")
        print("-" * 80)
        print(f"{'ID':<12} {'Workflow':<20} {'Status':<12} {'Started':<20} {'Duration'}")
        print("-" * 80)

        for execution in executions:
            print(f"{execution['id']:<12} {execution['workflow']:<20} {execution['status']:<12} {execution['started']:<20} {execution['duration']}")

    def _executions_show(self, args):
        """Show execution details"""

        if not args:
            print("Usage: executions show <execution-id>")
            return

        execution_id = args[0]

        # Simulate execution details
        execution_details = {
            "id": execution_id,
            "workflow": "data-processor",
            "status": "completed",
            "started": "2024-01-15T10:30:00Z",
            "completed": "2024-01-15T10:32:30Z",
            "duration": "2.5s",
            "input": {"file": "data.csv", "format": "csv"},
            "output": {"processed_file": "output.json", "records": 1500},
            "logs": [
                "[10:30:00] Starting data processing",
                "[10:30:15] Reading input file: data.csv",
                "[10:31:30] Processing 1500 records",
                "[10:32:25] Writing output: output.json",
                "[10:32:30] Processing completed successfully"
            ]
        }

        print(f"🔍 Execution Details: {execution_id}")
        print(f"   Workflow: {execution_details['workflow']}")
        print(f"   Status: {execution_details['status']}")
        print(f"   Started: {execution_details['started']}")
        print(f"   Completed: {execution_details['completed']}")
        print(f"   Duration: {execution_details['duration']}")

        if '--logs' in args:
            print("\n📝 Execution Logs:")
            for log_entry in execution_details['logs']:
                print(f"   {log_entry}")

    def _executions_cancel(self, args):
        """Cancel execution"""

        if not args:
            print("Usage: executions cancel <execution-id>")
            return

        execution_id = args[0]
        print(f"Cancelling execution: {execution_id}")
        print("✅ Execution cancelled successfully")

    def _executions_retry(self, args):
        """Retry execution"""

        if not args:
            print("Usage: executions retry <execution-id>")
            return

        execution_id = args[0]
        new_execution_id = f"exec_{int(time.time())}"

        print(f"Retrying execution: {execution_id}")
        print(f"New execution ID: {new_execution_id}")
        print("✅ Retry initiated successfully")

    def _executions_cleanup(self, args):
        """Cleanup old executions"""

        print("Cleaning up old executions...")
        print("✅ Cleaned up 25 old execution records")

    def do_history(self, args):
        """Show command history"""

        print("📋 Command History")
        print("-" * 50)

        for i, entry in enumerate(self.command_history[-20:], 1):  # Show last 20
            print(f"{i:2d}. {entry['command']}")

    def do_alias(self, args):
        """Manage command aliases
        Usage: alias [name] [command]
        """

        if not args:
            print("Current aliases:")
            for alias, command in self.aliases.items():
                print(f"   {alias} -> {command}")
        else:
            parts = args.split(' ', 1)
            if len(parts) == 2:
                alias_name, command = parts
                self.aliases[alias_name] = command
                print(f"Alias created: {alias_name} -> {command}")
            else:
                print("Usage: alias <name> <command>")

    def do_clear(self, args):
        """Clear screen"""
        os.system('clear' if os.name == 'posix' else 'cls')

    def do_quit(self, args):
        """Exit the interactive CLI"""

        if self.nexus_connected:
            print("Disconnecting from Nexus platform...")
            self.do_disconnect('')

        print("Goodbye! 👋")
        return True

    def do_exit(self, args):
        """Exit the interactive CLI"""
        return self.do_quit(args)

    def _show_platform_info(self):
        """Show platform information after connection"""

        print("\n📊 Platform Information")
        print("   Version: 1.0.0")
        print("   Workflows: 5 registered")
        print("   Status: Healthy")
        print("   Uptime: 2h 15m")
        print("\nType 'help' for available commands")

    def default(self, line):
        """Handle unknown commands"""
        command = line.split()[0]
        print(f"Unknown command: {command}")
        print("Type 'help' for available commands")

    def completedefault(self, text, line, begidx, endidx):
        """Default completion for commands"""

        # Basic completion for workflow names
        workflow_names = ['data-processor', 'api-handler', 'analytics-engine']

        if 'execute' in line or 'workflows info' in line:
            return [name for name in workflow_names if name.startswith(text)]

        return []

# CLI argument parser
def create_cli_parser():
    """Create CLI argument parser"""

    parser = argparse.ArgumentParser(
        description="Nexus Workflow-Native Platform CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus start                          # Start platform
  nexus execute data-processor         # Execute workflow
  nexus workflows list                 # List workflows
  nexus status --json                  # Get status in JSON
  nexus interactive                    # Enter interactive mode
        """
    )

    # Global options
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--json', action='store_true', help='JSON output format')
    parser.add_argument('--host', default='localhost', help='Nexus host')
    parser.add_argument('--port', type=int, default=8000, help='Nexus port')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Interactive mode
    interactive_parser = subparsers.add_parser('interactive', help='Enter interactive mode')

    # Start command
    start_parser = subparsers.add_parser('start', help='Start Nexus platform')
    start_parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    start_parser.add_argument('--workers', type=int, default=4, help='Number of workers')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show platform status')
    status_parser.add_argument('--detailed', action='store_true', help='Detailed status')

    # Execute command
    execute_parser = subparsers.add_parser('execute', help='Execute workflow')
    execute_parser.add_argument('workflow', help='Workflow name')
    execute_parser.add_argument('--input', help='Input data (JSON)')
    execute_parser.add_argument('--input-file', help='Input file path')
    execute_parser.add_argument('--async', action='store_true', help='Async execution')
    execute_parser.add_argument('--timeout', type=int, help='Timeout in seconds')

    # Workflows command
    workflows_parser = subparsers.add_parser('workflows', help='Workflow management')
    workflows_subparsers = workflows_parser.add_subparsers(dest='workflows_command')

    workflows_list_parser = workflows_subparsers.add_parser('list', help='List workflows')
    workflows_list_parser.add_argument('--verbose', action='store_true', help='Verbose output')

    workflows_info_parser = workflows_subparsers.add_parser('info', help='Workflow info')
    workflows_info_parser.add_argument('workflow', help='Workflow name')

    return parser

def main():
    """Main CLI entry point"""

    parser = create_cli_parser()
    args = parser.parse_args()

    if args.command == 'interactive':
        # Enter interactive mode
        try:
            cli = NexusInteractiveCLI()
            cli.cmdloop()
        except KeyboardInterrupt:
            print("\nGoodbye! 👋")
    else:
        # Handle direct commands
        print(f"Nexus CLI - Command: {args.command}")
        print(f"Arguments: {vars(args)}")

        # In real implementation, would execute the actual command
        if args.command == 'start':
            print("Starting Nexus platform...")
        elif args.command == 'status':
            print("Platform status: Healthy")
        elif args.command == 'execute':
            print(f"Executing workflow: {args.workflow}")
        else:
            print("Command execution would happen here")

if __name__ == '__main__':
    main()
```

### Workflow-Specific CLI Generation

```python
# workflow_cli_generator.py - Automatic CLI generation for workflows
from typing import Dict, Any, List, Optional
import argparse
import json
import yaml
from pathlib import Path

class WorkflowCLIGenerator:
    """Generate CLI interfaces for registered workflows"""

    def __init__(self, nexus_app):
        self.nexus_app = nexus_app
        self.generated_commands = {}

    def generate_workflow_cli(self, workflow_name: str, workflow_definition: Dict[str, Any]) -> argparse.ArgumentParser:
        """Generate CLI parser for specific workflow"""

        # Create workflow-specific parser
        parser = argparse.ArgumentParser(
            prog=f"nexus execute {workflow_name}",
            description=f"Execute {workflow_name} workflow",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )

        # Add common workflow options
        parser.add_argument('--session-id', help='Session identifier')
        parser.add_argument('--async', action='store_true', help='Execute asynchronously')
        parser.add_argument('--timeout', type=int, help='Execution timeout (seconds)')
        parser.add_argument('--retry', type=int, default=3, help='Retry attempts')
        parser.add_argument('--output-format', choices=['json', 'yaml', 'table'], default='json', help='Output format')

        # Extract input schema from workflow
        input_schema = workflow_definition.get('input_schema', {})

        # Generate arguments from schema
        if input_schema.get('type') == 'object':
            properties = input_schema.get('properties', {})
            required_fields = input_schema.get('required', [])

            for field_name, field_schema in properties.items():
                self._add_schema_argument(parser, field_name, field_schema, field_name in required_fields)

        # Add file input options
        parser.add_argument('--input-file', help='Input data from file (JSON/YAML)')
        parser.add_argument('--input-json', help='Input data as JSON string')

        return parser

    def _add_schema_argument(self, parser: argparse.ArgumentParser, field_name: str,
                           field_schema: Dict[str, Any], required: bool = False):
        """Add argument based on schema field"""

        field_type = field_schema.get('type', 'string')
        description = field_schema.get('description', f'{field_name} parameter')
        default_value = field_schema.get('default')

        arg_kwargs = {
            'help': description,
            'required': required and default_value is None
        }

        if default_value is not None:
            arg_kwargs['default'] = default_value

        # Map schema types to Python types
        if field_type == 'integer':
            arg_kwargs['type'] = int
        elif field_type == 'number':
            arg_kwargs['type'] = float
        elif field_type == 'boolean':
            arg_kwargs['action'] = 'store_true'
        elif field_type == 'array':
            arg_kwargs['nargs'] = '*'
            arg_kwargs['type'] = str

        # Handle enum values
        enum_values = field_schema.get('enum')
        if enum_values:
            arg_kwargs['choices'] = enum_values

        # Add argument
        arg_name = f"--{field_name.replace('_', '-')}"
        parser.add_argument(arg_name, **arg_kwargs)

    def generate_cli_help(self, workflow_name: str) -> str:
        """Generate help text for workflow CLI"""

        help_text = f"""
Workflow: {workflow_name}
Usage: nexus execute {workflow_name} [options]

This workflow can be executed via multiple channels:
  CLI:       nexus execute {workflow_name} --param value
  API:       POST /workflows/{workflow_name}/execute
  WebSocket: ws://host:port/workflows/{workflow_name}/stream
  MCP:       execute_{workflow_name.replace('-', '_')}

Examples:
  # Execute with parameters
  nexus execute {workflow_name} --input-file data.json

  # Execute asynchronously
  nexus execute {workflow_name} --async --session-id session_123

  # Execute with inline JSON
  nexus execute {workflow_name} --input-json '{{"key": "value"}}'

  # Execute with timeout
  nexus execute {workflow_name} --timeout 300

Options:
"""
        return help_text

    def register_workflow_commands(self, workflows: Dict[str, Dict[str, Any]]) -> None:
        """Register CLI commands for all workflows"""

        for workflow_name, workflow_def in workflows.items():
            cli_parser = self.generate_workflow_cli(workflow_name, workflow_def)
            help_text = self.generate_cli_help(workflow_name)

            self.generated_commands[workflow_name] = {
                'parser': cli_parser,
                'help': help_text,
                'definition': workflow_def
            }

            print(f"Generated CLI for workflow: {workflow_name}")

    def execute_workflow_cli(self, workflow_name: str, args: List[str]) -> Dict[str, Any]:
        """Execute workflow via generated CLI"""

        if workflow_name not in self.generated_commands:
            raise ValueError(f"Workflow '{workflow_name}' not found")

        parser = self.generated_commands[workflow_name]['parser']

        try:
            parsed_args = parser.parse_args(args)

            # Convert parsed arguments to workflow input
            workflow_input = self._args_to_workflow_input(parsed_args)

            # Execute workflow
            execution_result = self._execute_workflow(workflow_name, workflow_input, parsed_args)

            return execution_result

        except SystemExit:
            # Handle argparse help/error
            raise

    def _args_to_workflow_input(self, args: argparse.Namespace) -> Dict[str, Any]:
        """Convert CLI arguments to workflow input"""

        workflow_input = {}

        # Handle file input
        if hasattr(args, 'input_file') and args.input_file:
            with open(args.input_file, 'r') as f:
                if args.input_file.endswith('.yaml') or args.input_file.endswith('.yml'):
                    file_data = yaml.safe_load(f)
                else:
                    file_data = json.load(f)
                workflow_input.update(file_data)

        # Handle JSON input
        if hasattr(args, 'input_json') and args.input_json:
            json_data = json.loads(args.input_json)
            workflow_input.update(json_data)

        # Handle individual arguments
        for key, value in vars(args).items():
            if not key.startswith('_') and value is not None:
                # Skip special arguments
                if key in ['input_file', 'input_json', 'session_id', 'async', 'timeout', 'retry', 'output_format']:
                    continue

                # Convert CLI argument name back to workflow parameter
                param_name = key.replace('-', '_')
                workflow_input[param_name] = value

        return workflow_input

    def _execute_workflow(self, workflow_name: str, workflow_input: Dict[str, Any],
                         args: argparse.Namespace) -> Dict[str, Any]:
        """Execute workflow with CLI arguments"""

        execution_config = {
            'workflow_name': workflow_name,
            'input_data': workflow_input,
            'session_id': getattr(args, 'session_id', None),
            'async_execution': getattr(args, 'async', False),
            'timeout': getattr(args, 'timeout', None),
            'retry_attempts': getattr(args, 'retry', 3),
            'output_format': getattr(args, 'output_format', 'json')
        }

        # Simulate workflow execution
        execution_result = {
            'execution_id': f"exec_{workflow_name}_{int(time.time())}",
            'workflow_name': workflow_name,
            'status': 'completed',
            'input_data': workflow_input,
            'output_data': {
                'message': f"Workflow {workflow_name} executed successfully",
                'processed_at': time.time()
            },
            'execution_time_ms': 1500,
            'metadata': execution_config
        }

        return execution_result

# Example usage
def demo_workflow_cli_generation():
    """Demonstrate workflow CLI generation"""

    # Example workflow definitions
    workflows = {
        'data-processor': {
            'description': 'Process data files with various transformations',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'input_file': {
                        'type': 'string',
                        'description': 'Path to input data file'
                    },
                    'output_format': {
                        'type': 'string',
                        'enum': ['json', 'csv', 'parquet'],
                        'default': 'json',
                        'description': 'Output file format'
                    },
                    'batch_size': {
                        'type': 'integer',
                        'default': 1000,
                        'description': 'Processing batch size'
                    },
                    'validate_data': {
                        'type': 'boolean',
                        'default': False,
                        'description': 'Enable data validation'
                    },
                    'filters': {
                        'type': 'array',
                        'description': 'Data filtering rules'
                    }
                },
                'required': ['input_file']
            }
        },
        'api-handler': {
            'description': 'Handle API requests with custom processing',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'endpoint': {
                        'type': 'string',
                        'description': 'API endpoint to handle'
                    },
                    'method': {
                        'type': 'string',
                        'enum': ['GET', 'POST', 'PUT', 'DELETE'],
                        'default': 'POST',
                        'description': 'HTTP method'
                    },
                    'timeout_seconds': {
                        'type': 'integer',
                        'default': 30,
                        'description': 'Request timeout'
                    }
                },
                'required': ['endpoint']
            }
        }
    }

    # Generate CLI for workflows
    cli_generator = WorkflowCLIGenerator(None)  # nexus_app would be passed here
    cli_generator.register_workflow_commands(workflows)

    print("Generated CLI commands for workflows:")
    for workflow_name in workflows.keys():
        print(f"  nexus execute {workflow_name} [options]")

    # Example CLI execution
    try:
        result = cli_generator.execute_workflow_cli('data-processor', [
            '--input-file', 'data.csv',
            '--output-format', 'json',
            '--batch-size', '2000',
            '--validate-data',
            '--session-id', 'session_123'
        ])

        print(f"\nExecution result: {result['execution_id']}")
        print(f"Status: {result['status']}")

    except Exception as e:
        print(f"Execution error: {e}")

if __name__ == '__main__':
    demo_workflow_cli_generation()
```

## Advanced CLI Features

### CLI Configuration and Customization

```bash
#!/bin/bash

# Advanced CLI Configuration Examples

# 1. CLI Configuration File (~/.nexus/config.yaml)
cat > ~/.nexus/config.yaml << 'EOF'
cli:
  default_host: "localhost"
  default_port: 8000
  output_format: "json"
  timeout: 300
  auto_connect: true

  # Command aliases
  aliases:
    ls: "workflows list"
    ps: "executions list"
    top: "status --detailed"
    logs: "logs --follow"

  # Default parameters for commands
  defaults:
    execute:
      timeout: 600
      retry: 3
    workflows:
      list:
        verbose: true

  # Output formatting
  formatting:
    table_style: "grid"
    date_format: "%Y-%m-%d %H:%M:%S"
    timezone: "UTC"

  # Interactive mode settings
  interactive:
    prompt: "(nexus) "
    history_size: 1000
    completion: true
    color: true

# Authentication settings
auth:
  method: "token"  # token, oauth, basic
  token_file: "~/.nexus/token"
  auto_refresh: true

# Logging settings
logging:
  level: "INFO"
  file: "~/.nexus/cli.log"
  max_size: "10MB"
  backup_count: 5
EOF

# 2. Environment-specific configurations
cat > ~/.nexus/environments/production.yaml << 'EOF'
cli:
  default_host: "nexus.production.com"
  default_port: 443
  ssl: true

auth:
  method: "oauth"
  oauth_provider: "company-sso"
EOF

cat > ~/.nexus/environments/development.yaml << 'EOF'
cli:
  default_host: "localhost"
  default_port: 8000
  ssl: false

auth:
  method: "basic"
  username: "dev-user"
EOF

# 3. Advanced CLI usage examples

# Use specific environment
nexus --env production status
nexus --env development execute data-processor

# Custom output formatting
nexus workflows list --format table --style fancy_grid
nexus status --format yaml
nexus executions list --format csv > executions.csv

# Batch operations
nexus batch << 'EOF'
workflows list
execute data-processor --input '{"file": "data1.csv"}'
execute data-processor --input '{"file": "data2.csv"}'
executions list --status running
EOF

# Scripting support
nexus execute data-processor \
  --input-file batch_data.json \
  --async \
  --output-file results.json \
  --wait-for-completion \
  --notify-on-completion "slack:#ops-team"

# Pipeline operations
cat input_files.txt | xargs -I {} nexus execute data-processor --input-file {}

# Monitoring and watching
nexus watch executions --status running  # Watch running executions
nexus tail logs --filter "ERROR"         # Tail error logs
nexus monitor workflows --alert-on-failure

# Advanced queries
nexus executions list \
  --workflow data-processor \
  --status completed \
  --since "2024-01-01" \
  --until "2024-01-31" \
  --format json | jq '.[] | select(.duration > "5s")'

# Workflow composition
nexus compose << 'EOF'
workflows:
  - name: data-ingestion
    input:
      source: "s3://bucket/data/"
  - name: data-processing
    input:
      source: "@data-ingestion.output.processed_data"
  - name: data-export
    input:
      data: "@data-processing.output.results"
      destination: "warehouse.table"
EOF

# 4. Plugin and extension management
nexus plugins install nexus-aws-plugin
nexus plugins install nexus-slack-notifications
nexus plugins list --enabled
nexus plugins configure slack-notifications --webhook-url https://hooks.slack.com/...

# 5. Advanced authentication
nexus auth login --provider google-oauth
nexus auth login --certificate client.pem --key client.key
nexus auth refresh --force
nexus auth rotate-token --auto-update-config

# 6. Performance and debugging
nexus --debug execute data-processor --input-file large_data.json
nexus --profile execute data-processor  # Profile execution time
nexus --trace execute data-processor    # Detailed execution trace

# Memory and resource monitoring
nexus system memory
nexus system cpu
nexus system disk
nexus system network

# 7. Backup and restore operations
nexus backup create --include-workflows --include-data --output backup.tar.gz
nexus backup restore backup.tar.gz --selective workflows
nexus backup list --remote s3://backup-bucket/
nexus backup schedule --daily --time "02:00" --retention 30

# 8. Cluster operations (Enterprise)
nexus cluster init --name production-cluster
nexus cluster join --token cluster-token --node worker-01
nexus cluster status --detailed
nexus cluster rebalance --workflow data-processor
nexus cluster failover --from node-01 --to node-02

# 9. Advanced workflow operations
nexus workflows validate schema.yaml
nexus workflows test data-processor --dry-run --input test_data.json
nexus workflows benchmark data-processor --iterations 100 --concurrent 10
nexus workflows optimize data-processor --suggest-improvements

# 10. Integration commands
nexus integrate --source kubernetes --sync-secrets
nexus integrate --destination datadog --metrics all
nexus integrate --webhook slack --on-failure --on-success
nexus integrate --git-hooks --on-push deploy --on-merge test

# 11. Custom commands via plugins
nexus aws s3 sync s3://bucket/data/ ./local_data/
nexus docker deploy --image nexus-worker:latest --replicas 5
nexus terraform apply --workspace production
nexus vault rotate-secrets --service nexus-prod

# 12. Workflow scheduling
nexus schedule create \
  --name "daily-processing" \
  --workflow data-processor \
  --cron "0 2 * * *" \
  --input-file daily_config.json

nexus schedule list --active
nexus schedule pause daily-processing
nexus schedule resume daily-processing
nexus schedule delete daily-processing

echo "Nexus CLI Advanced Examples Complete"
```

This CLI reference provides comprehensive coverage of all Nexus command-line capabilities, from basic operations to advanced enterprise features. The interactive mode and automatic workflow CLI generation demonstrate the platform's workflow-native approach to command-line interfaces.
