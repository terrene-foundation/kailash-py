/**
 * Node Registry - Maps backend Kailash nodes to frontend representation
 * Synced with Kailash Python SDK node catalog
 */

export interface NodeDefinition {
  id: string;
  label: string;
  category: string;
  description: string;
  icon?: string;
  inputs: number; // Number of input handles
  outputs: number; // Number of output handles
  parameters?: ParameterDefinition[];
  pythonClass: string;
  module: string;
}

export interface ParameterDefinition {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'any';
  required: boolean;
  default?: any;
  description?: string;
  options?: string[]; // For enum-like parameters
}

export interface NodeCategory {
  id: string;
  label: string;
  description: string;
  color: string; // For UI theming
  icon?: string;
}

// Node Categories (matching Kailash SDK structure)
export const NODE_CATEGORIES: Record<string, NodeCategory> = {
  ai: {
    id: 'ai',
    label: 'AI Nodes',
    description: 'AI and LLM interaction nodes',
    color: '#9333ea', // Purple
    icon: '🤖',
  },
  api: {
    id: 'api',
    label: 'API Nodes',
    description: 'API integration and HTTP nodes',
    color: '#ec4899', // Pink
    icon: '🔌',
  },
  code: {
    id: 'code',
    label: 'Code Nodes',
    description: 'Code execution nodes',
    color: '#06b6d4', // Cyan
    icon: '💻',
  },
  data: {
    id: 'data',
    label: 'Data Nodes',
    description: 'Data I/O and processing nodes',
    color: '#3b82f6', // Blue
    icon: '📊',
  },
  logic: {
    id: 'logic',
    label: 'Logic Nodes',
    description: 'Control flow and logic nodes',
    color: '#f59e0b', // Amber
    icon: '🔀',
  },
  mcp: {
    id: 'mcp',
    label: 'MCP Nodes',
    description: 'Model Context Protocol nodes',
    color: '#10b981', // Emerald
    icon: '🔗',
  },
  transform: {
    id: 'transform',
    label: 'Transform Nodes',
    description: 'Data transformation nodes',
    color: '#8b5cf6', // Violet
    icon: '🔄',
  },
};

// Complete Node Registry
export const NODE_REGISTRY: Record<string, NodeDefinition> = {
  // AI Nodes
  'llm-agent': {
    id: 'llm-agent',
    label: 'LLM Agent',
    category: 'ai',
    description: 'Interact with Large Language Models',
    inputs: 1,
    outputs: 1,
    pythonClass: 'LLMAgentNode',
    module: 'kailash.nodes.ai.llm_agent',
    parameters: [
      {
        name: 'provider',
        type: 'string',
        required: true,
        options: ['openai', 'anthropic', 'ollama', 'mock'],
        description: 'LLM provider',
      },
      {
        name: 'model',
        type: 'string',
        required: true,
        description: 'Model name',
      },
      {
        name: 'prompt',
        type: 'string',
        required: false,
        description: 'Input prompt',
      },
      {
        name: 'temperature',
        type: 'number',
        required: false,
        default: 0.7,
        description: 'Sampling temperature',
      },
    ],
  },
  'embedding-generator': {
    id: 'embedding-generator',
    label: 'Embedding Generator',
    category: 'ai',
    description: 'Generate text embeddings',
    inputs: 1,
    outputs: 1,
    pythonClass: 'EmbeddingGeneratorNode',
    module: 'kailash.nodes.ai.embedding_generator',
  },
  'chat-agent': {
    id: 'chat-agent',
    label: 'Chat Agent',
    category: 'ai',
    description: 'Conversational AI agent',
    inputs: 1,
    outputs: 1,
    pythonClass: 'ChatAgent',
    module: 'kailash.nodes.ai.agents',
  },
  'a2a-communicator': {
    id: 'a2a-communicator',
    label: 'A2A Communicator',
    category: 'ai',
    description: 'Agent-to-agent communication',
    inputs: 1,
    outputs: 1,
    pythonClass: 'A2ACommunicatorNode',
    module: 'kailash.nodes.ai.a2a',
  },

  // API Nodes
  'http-request': {
    id: 'http-request',
    label: 'HTTP Request',
    category: 'api',
    description: 'Make HTTP API requests',
    inputs: 1,
    outputs: 1,
    pythonClass: 'HTTPRequestNode',
    module: 'kailash.nodes.api.http',
  },
  'rest-client': {
    id: 'rest-client',
    label: 'REST Client',
    category: 'api',
    description: 'RESTful API client',
    inputs: 1,
    outputs: 1,
    pythonClass: 'RESTClientNode',
    module: 'kailash.nodes.api.rest',
  },
  'graphql-client': {
    id: 'graphql-client',
    label: 'GraphQL Client',
    category: 'api',
    description: 'GraphQL API client',
    inputs: 1,
    outputs: 1,
    pythonClass: 'GraphQLClientNode',
    module: 'kailash.nodes.api.graphql',
  },

  // Code Nodes
  'python-code': {
    id: 'python-code',
    label: 'Python Code',
    category: 'code',
    description: 'Execute Python code',
    inputs: 1,
    outputs: 1,
    pythonClass: 'PythonCodeNode',
    module: 'kailash.nodes.code.python',
    parameters: [
      {
        name: 'code',
        type: 'string',
        required: true,
        description: 'Python code to execute',
      },
    ],
  },

  // Data Nodes
  'csv-reader': {
    id: 'csv-reader',
    label: 'CSV Reader',
    category: 'data',
    description: 'Read CSV files',
    inputs: 0,
    outputs: 1,
    pythonClass: 'CSVReaderNode',
    module: 'kailash.nodes.data.readers',
    parameters: [
      {
        name: 'file_path',
        type: 'string',
        required: true,
        description: 'Path to CSV file',
      },
    ],
  },
  'csv-writer': {
    id: 'csv-writer',
    label: 'CSV Writer',
    category: 'data',
    description: 'Write CSV files',
    inputs: 1,
    outputs: 1,
    pythonClass: 'CSVWriterNode',
    module: 'kailash.nodes.data.writers',
  },
  'json-reader': {
    id: 'json-reader',
    label: 'JSON Reader',
    category: 'data',
    description: 'Read JSON files',
    inputs: 0,
    outputs: 1,
    pythonClass: 'JSONReaderNode',
    module: 'kailash.nodes.data.readers',
  },
  'json-writer': {
    id: 'json-writer',
    label: 'JSON Writer',
    category: 'data',
    description: 'Write JSON files',
    inputs: 1,
    outputs: 1,
    pythonClass: 'JSONWriterNode',
    module: 'kailash.nodes.data.writers',
  },
  'sql-query': {
    id: 'sql-query',
    label: 'SQL Query',
    category: 'data',
    description: 'Execute SQL queries',
    inputs: 1,
    outputs: 1,
    pythonClass: 'SQLQueryNode',
    module: 'kailash.nodes.data.sql',
  },

  // Logic Nodes
  'switch': {
    id: 'switch',
    label: 'Switch',
    category: 'logic',
    description: 'Conditional routing',
    inputs: 1,
    outputs: 2, // Multiple outputs for different conditions
    pythonClass: 'SwitchNode',
    module: 'kailash.nodes.logic.operations',
  },
  'merge': {
    id: 'merge',
    label: 'Merge',
    category: 'logic',
    description: 'Merge multiple inputs',
    inputs: 2, // Multiple inputs
    outputs: 1,
    pythonClass: 'MergeNode',
    module: 'kailash.nodes.logic.operations',
  },
  'loop': {
    id: 'loop',
    label: 'Loop',
    category: 'logic',
    description: 'Loop control for workflows',
    inputs: 1,
    outputs: 2, // Continue and exit outputs
    pythonClass: 'LoopNode',
    module: 'kailash.nodes.logic.loop',
  },
  'workflow': {
    id: 'workflow',
    label: 'Sub-Workflow',
    category: 'logic',
    description: 'Execute nested workflow',
    inputs: 1,
    outputs: 1,
    pythonClass: 'WorkflowNode',
    module: 'kailash.nodes.logic.workflow',
  },

  // MCP Nodes
  'mcp-client': {
    id: 'mcp-client',
    label: 'MCP Client',
    category: 'mcp',
    description: 'Model Context Protocol client',
    inputs: 1,
    outputs: 1,
    pythonClass: 'MCPClientNode',
    module: 'kailash.nodes.mcp.client',
  },
  'mcp-server': {
    id: 'mcp-server',
    label: 'MCP Server',
    category: 'mcp',
    description: 'Model Context Protocol server',
    inputs: 1,
    outputs: 1,
    pythonClass: 'MCPServerNode',
    module: 'kailash.nodes.mcp.server',
  },

  // Transform Nodes
  'json-transform': {
    id: 'json-transform',
    label: 'JSON Transform',
    category: 'transform',
    description: 'Transform JSON data',
    inputs: 1,
    outputs: 1,
    pythonClass: 'JSONTransformNode',
    module: 'kailash.nodes.transform.processors',
  },
  'text-chunker': {
    id: 'text-chunker',
    label: 'Text Chunker',
    category: 'transform',
    description: 'Split text into chunks',
    inputs: 1,
    outputs: 1,
    pythonClass: 'TextChunkerNode',
    module: 'kailash.nodes.transform.chunkers',
  },
  'template-formatter': {
    id: 'template-formatter',
    label: 'Template Formatter',
    category: 'transform',
    description: 'Format data using templates',
    inputs: 1,
    outputs: 1,
    pythonClass: 'TemplateFormatterNode',
    module: 'kailash.nodes.transform.formatters',
  },
};

// Helper functions
export function getNodesByCategory(category: string): NodeDefinition[] {
  return Object.values(NODE_REGISTRY).filter(node => node.category === category);
}

export function getNodeDefinition(nodeId: string): NodeDefinition | undefined {
  return NODE_REGISTRY[nodeId];
}

export function getCategoryDefinition(categoryId: string): NodeCategory | undefined {
  return NODE_CATEGORIES[categoryId];
}
