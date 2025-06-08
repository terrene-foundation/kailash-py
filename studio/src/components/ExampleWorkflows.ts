// Example workflow configurations that can be loaded into the canvas

export const EXAMPLE_WORKFLOWS = {
  loopValidation: {
    name: "Agent Loop Validation",
    description: "Agent A analyzes a report, Agent B validates, loops until quality threshold is met",
    nodes: {
      "input_1": {
        type: "DataProcessorNode",
        position: { x: 100, y: 200 },
        config: {
          operation: "format",
          template: {
            report: "Initial report text",
            iteration: 0,
            feedback_history: []
          }
        }
      },
      "agent_a_1": {
        type: "LLMAgentNode",
        position: { x: 300, y: 200 },
        config: {
          provider: "ollama",
          model: "llama2",
          prompt: "Analyze report with feedback: {feedback_history}"
        }
      },
      "agent_b_1": {
        type: "LLMAgentNode",
        position: { x: 500, y: 200 },
        config: {
          provider: "ollama",
          model: "llama2",
          prompt: "Validate analysis and provide quality score"
        }
      },
      "loop_1": {
        type: "LoopNode",
        position: { x: 700, y: 200 },
        config: {
          condition: "expression",
          expression: "data.quality_score >= 85 or iteration >= 3",
          max_iterations: 3
        }
      },
      "switch_1": {
        type: "SwitchNode",
        position: { x: 900, y: 200 },
        config: {
          condition: "data.should_exit == true"
        }
      },
      "merge_1": {
        type: "MergeNode",
        position: { x: 500, y: 400 },
        config: {}
      },
      "output_1": {
        type: "DataProcessorNode",
        position: { x: 1100, y: 200 },
        config: {
          operation: "select",
          fields: ["final_analysis", "quality_score", "iterations"]
        }
      }
    },
    connections: [
      {
        source_node: "input_1",
        source_output: "output",
        target_node: "agent_a_1",
        target_input: "input"
      },
      {
        source_node: "agent_a_1",
        source_output: "output",
        target_node: "agent_b_1",
        target_input: "input"
      },
      {
        source_node: "agent_b_1",
        source_output: "output",
        target_node: "loop_1",
        target_input: "input"
      },
      {
        source_node: "loop_1",
        source_output: "output",
        target_node: "switch_1",
        target_input: "input"
      },
      {
        source_node: "switch_1",
        source_output: "true",
        target_node: "output_1",
        target_input: "input"
      },
      {
        source_node: "switch_1",
        source_output: "false",
        target_node: "merge_1",
        target_input: "input-1"
      },
      {
        source_node: "merge_1",
        source_output: "output",
        target_node: "agent_a_1",
        target_input: "input"
      }
    ]
  },

  simpleLoop: {
    name: "Simple Counter Loop",
    description: "A basic loop that increments a counter until it reaches a threshold",
    nodes: {
      "start_1": {
        type: "DataProcessorNode",
        position: { x: 100, y: 200 },
        config: {
          operation: "format",
          template: { counter: 0, data: "Hello" }
        }
      },
      "process_1": {
        type: "PythonCodeNode",
        position: { x: 300, y: 200 },
        config: {
          code: `# Increment counter and process data
output = {
    "counter": input_data["counter"] + 1,
    "data": input_data["data"] + " World",
    "timestamp": datetime.now().isoformat()
}`
        }
      },
      "loop_control_1": {
        type: "LoopNode",
        position: { x: 500, y: 200 },
        config: {
          condition: "expression",
          expression: "data.counter >= 5",
          exit_on: true
        }
      },
      "router_1": {
        type: "SwitchNode",
        position: { x: 700, y: 200 },
        config: {
          condition: "data.should_exit == true"
        }
      },
      "final_1": {
        type: "DataProcessorNode",
        position: { x: 900, y: 100 },
        config: {
          operation: "select",
          fields: ["data", "counter"]
        }
      }
    },
    connections: [
      {
        source_node: "start_1",
        source_output: "output",
        target_node: "process_1",
        target_input: "input"
      },
      {
        source_node: "process_1",
        source_output: "output",
        target_node: "loop_control_1",
        target_input: "input"
      },
      {
        source_node: "loop_control_1",
        source_output: "output",
        target_node: "router_1",
        target_input: "input"
      },
      {
        source_node: "router_1",
        source_output: "true",
        target_node: "final_1",
        target_input: "input"
      },
      {
        source_node: "router_1",
        source_output: "false",
        target_node: "process_1",
        target_input: "input"
      }
    ]
  }
};


/**
 * Loop Pattern Best Practices:
 *
 * 1. LoopNode outputs a single data stream with control information:
 *    - should_exit: boolean
 *    - continue_loop: boolean
 *    - iteration: number
 *    - data: passthrough data
 *    - loop_state: maintained state
 *
 * 2. Use a SwitchNode after LoopNode to route based on should_exit
 *
 * 3. For complex loops with multiple agents:
 *    - Use MergeNode to combine feedback with original data
 *    - Maintain iteration count and history in the data
 *    - Set reasonable max_iterations to prevent infinite loops
 *
 * 4. Visual representation in the canvas:
 *    - Loop connections (going backwards) are shown with dashed purple lines
 *    - Use clear node labels to indicate the flow
 *    - Position nodes to minimize crossing connections
 */
