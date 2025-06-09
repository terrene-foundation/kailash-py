## Setup
1. Analyze and consolidate the learning from mistakes, patterns, and cheatsheet 
2. Reference all the examples
3. Identify end to end workflows (no mock, as real-world as possible)
4. Streamline our mistakes, patterns, and cheatsheet by combining and re-organizing them. 
5. Document a full library of workflows (reference/workflow-library) that any users (and Claude Code) can use to create solutions:
   - quickly and accurately
   - using as little tokens as possible 
6. This library should be comprehensive:
   - covering all the common patterns regardless of domains.
   - covering all the common use-cases that enterprises would encounter.
   - covering all the specific use-cases for each domain.
7. Also use the AI Registry MCP Server as a reference for real AI use cases and integration patterns for each of the domains. 
8. Break this plan down into detailed steps, I need deep introspection. 
9. Record it in todos master list, and todos/active. The plan in active should be detailed enough for Claude to follow.

## Execution
1. Create common use-cases and patterns that all enterprise would encounter.
2. Use the AI Registry MCP Server as a reference for each available domain.
3. Create a comprehensive library of workflows in `guide/reference/workflow-library/`:
   - Categorize them (by-pattern/ for common patterns, by-enterprise/ for common enterprise use-cases, by-domain/ for specific domain use-cases).
   - Within each category, the workflows should have a corresponding `.md` file documenting the pattern, purpose, and usage.
   - Include a Python script for each workflow in a sub directory scripts/ that can be executed to demonstrate the pattern.
     - Ensure that all your codes are using existing nodes as far as possible.
     - Do not use PythonCodeNode unless absolutely necessary.
     - If certain PythonCodeNodes are repeated across different workflows, document this new node in the `guide/reference/workflow-library/shared_nodes` directory.
   - Ensure that the `.md` file references the script with sufficient information to guide users and Claude Code.
   - Create a sub directory training/ that contains training .md files. Do not use mock data, processes, or responses.
     - Ensure that all workflows are validated and tested with real data and processes.
     - For all the errors that you encounter until you get the script running correctly, record them into the corresponding training scripts. 
     - I need the correct/wrong code examples for the purpose of training a Mistral Devstral LLM via SFT and GRPO to be able to create solutions using the Kailash SDK accurately. 
