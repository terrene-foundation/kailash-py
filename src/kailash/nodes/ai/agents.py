"""AI agent nodes for the Kailash SDK."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class ChatAgent(Node):
    """Chat-based AI agent node."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "messages": NodeParameter(
                name="messages",
                type=list,
                required=True,
                description="List of chat messages",
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                required=False,
                default="default",
                description="Model to use for chat",
            ),
            "temperature": NodeParameter(
                name="temperature",
                type=float,
                required=False,
                default=0.7,
                description="Sampling temperature (0-1)",
            ),
            "max_tokens": NodeParameter(
                name="max_tokens",
                type=int,
                required=False,
                default=500,
                description="Maximum tokens in response",
            ),
            "system_prompt": NodeParameter(
                name="system_prompt",
                type=str,
                required=False,
                default="You are a helpful assistant.",
                description="System prompt for the agent",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        messages = kwargs["messages"]
        model = kwargs.get("model", "default")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 500)
        system_prompt = kwargs.get("system_prompt", "You are a helpful assistant.")

        # Mock chat responses
        responses = []

        # Add system prompt as first message
        full_conversation = [{"role": "system", "content": system_prompt}]
        full_conversation.extend(messages)

        # Generate mock response
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, dict) and last_message.get("role") == "user":
                user_content = last_message.get("content", "")

                # Simple mock responses based on input
                if "hello" in user_content.lower():
                    response = "Hello! How can I help you today?"
                elif "weather" in user_content.lower():
                    response = "I don't have access to real-time weather data, but I can help you with other questions!"
                elif "?" in user_content:
                    response = f"That's an interesting question about '{user_content[:50]}...'. Based on the context, I would say..."
                else:
                    response = f"I understand you're saying '{user_content[:50]}...'. Let me help you with that."

                responses.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "model": model,
                        "temperature": temperature,
                    }
                )

        return {
            "responses": responses,
            "full_conversation": full_conversation + responses,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }


@register_node()
class RetrievalAgent(Node):
    """Retrieval-augmented generation agent."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query", type=str, required=True, description="Query for retrieval"
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to search through",
            ),
            "top_k": NodeParameter(
                name="top_k",
                type=int,
                required=False,
                default=5,
                description="Number of top documents to retrieve",
            ),
            "similarity_threshold": NodeParameter(
                name="similarity_threshold",
                type=float,
                required=False,
                default=0.7,
                description="Minimum similarity threshold",
            ),
            "generate_answer": NodeParameter(
                name="generate_answer",
                type=bool,
                required=False,
                default=True,
                description="Whether to generate an answer based on retrieved documents",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        query = kwargs["query"]
        documents = kwargs["documents"]
        top_k = kwargs.get("top_k", 5)
        similarity_threshold = kwargs.get("similarity_threshold", 0.7)
        generate_answer = kwargs.get("generate_answer", True)

        # Mock retrieval
        retrieved_docs = []

        # Simple keyword-based retrieval
        query_words = set(query.lower().split())

        for doc in documents:
            if isinstance(doc, dict):
                content = doc.get("content", "")
            else:
                content = str(doc)

            # Calculate mock similarity
            doc_words = set(content.lower().split())
            overlap = len(query_words.intersection(doc_words))
            similarity = overlap / max(len(query_words), 1)

            if similarity >= similarity_threshold:
                retrieved_docs.append(
                    {"document": doc, "content": content, "similarity": similarity}
                )

        # Sort by similarity and take top_k
        retrieved_docs.sort(key=lambda x: x["similarity"], reverse=True)
        retrieved_docs = retrieved_docs[:top_k]

        # Generate answer if requested
        answer = None
        if generate_answer and retrieved_docs:
            # Mock answer generation
            context = " ".join([doc["content"][:200] for doc in retrieved_docs])
            answer = f"Based on the retrieved documents about '{query}', the relevant information is: {context[:300]}..."

        return {
            "query": query,
            "retrieved_documents": retrieved_docs,
            "answer": answer,
            "num_retrieved": len(retrieved_docs),
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
        }


@register_node()
class FunctionCallingAgent(Node):
    """Agent that can call functions based on input."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query", type=str, required=True, description="User query"
            ),
            "available_functions": NodeParameter(
                name="available_functions",
                type=list,
                required=True,
                description="List of available function definitions",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for the agent",
            ),
            "max_calls": NodeParameter(
                name="max_calls",
                type=int,
                required=False,
                default=3,
                description="Maximum number of function calls",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        query = kwargs["query"]
        available_functions = kwargs["available_functions"]
        context = kwargs.get("context", {})
        max_calls = kwargs.get("max_calls", 3)

        # Mock function calling
        function_calls = []

        # Simple pattern matching for function selection
        query_lower = query.lower()

        for func in available_functions:
            if isinstance(func, dict):
                func_name = func.get("name", "")
                func_description = func.get("description", "")

                # Check if query matches function purpose
                if func_name.lower() in query_lower or any(
                    word in query_lower for word in func_description.lower().split()
                ):
                    # Mock function call
                    mock_args = {}

                    # Generate mock arguments based on function parameters
                    if "parameters" in func:
                        for param_name, param_info in func["parameters"].items():
                            param_type = param_info.get("type", "string")
                            if param_type == "string":
                                mock_args[param_name] = f"mock_{param_name}_value"
                            elif param_type == "number":
                                mock_args[param_name] = 42
                            elif param_type == "boolean":
                                mock_args[param_name] = True
                            elif param_type == "array":
                                mock_args[param_name] = ["item1", "item2"]
                            else:
                                mock_args[param_name] = {"key": "value"}

                    function_calls.append(
                        {
                            "function": func_name,
                            "arguments": mock_args,
                            "result": f"Mock result from {func_name}",
                        }
                    )

                    if len(function_calls) >= max_calls:
                        break

        # Generate final response
        if function_calls:
            response = f"Based on your query '{query}', I executed {len(function_calls)} function(s). "
            response += "Here are the results: " + ", ".join(
                [
                    f"{call['function']}() returned {call['result']}"
                    for call in function_calls
                ]
            )
        else:
            response = f"I couldn't find any relevant functions to help with '{query}'."

        return {
            "query": query,
            "function_calls": function_calls,
            "response": response,
            "context": context,
            "num_calls": len(function_calls),
        }


@register_node()
class PlanningAgent(Node):
    """Agent that creates execution plans."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "goal": NodeParameter(
                name="goal", type=str, required=True, description="Goal to achieve"
            ),
            "available_tools": NodeParameter(
                name="available_tools",
                type=list,
                required=True,
                description="List of available tools/nodes",
            ),
            "constraints": NodeParameter(
                name="constraints",
                type=dict,
                required=False,
                default={},
                description="Constraints for the plan",
            ),
            "max_steps": NodeParameter(
                name="max_steps",
                type=int,
                required=False,
                default=10,
                description="Maximum number of steps in the plan",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        goal = kwargs["goal"]
        available_tools = kwargs["available_tools"]
        constraints = kwargs.get("constraints", {})
        max_steps = kwargs.get("max_steps", 10)

        # Mock plan generation
        plan_steps = []

        # Simple heuristic-based planning
        goal_lower = goal.lower()

        # Analyze goal and create steps
        if "process" in goal_lower and "data" in goal_lower:
            # Data processing workflow
            potential_steps = [
                {
                    "tool": "CSVReader",
                    "description": "Read input data",
                    "parameters": {"file_path": "input.csv"},
                },
                {
                    "tool": "Filter",
                    "description": "Filter data based on criteria",
                    "parameters": {"field": "value", "operator": ">", "value": 100},
                },
                {
                    "tool": "Aggregator",
                    "description": "Aggregate filtered data",
                    "parameters": {"group_by": "category", "operation": "sum"},
                },
                {
                    "tool": "CSVWriter",
                    "description": "Write results",
                    "parameters": {"file_path": "output.csv"},
                },
            ]
        elif "analyze" in goal_lower and "text" in goal_lower:
            # Text analysis workflow
            potential_steps = [
                {
                    "tool": "TextReader",
                    "description": "Read text data",
                    "parameters": {"file_path": "text.txt"},
                },
                {
                    "tool": "SentimentAnalyzer",
                    "description": "Analyze sentiment",
                    "parameters": {"language": "en"},
                },
                {
                    "tool": "TextSummarizer",
                    "description": "Summarize key points",
                    "parameters": {"max_length": 200},
                },
                {
                    "tool": "JSONWriter",
                    "description": "Save analysis results",
                    "parameters": {"file_path": "analysis.json"},
                },
            ]
        else:
            # Generic workflow
            potential_steps = [
                {
                    "tool": "DataReader",
                    "description": "Read input data",
                    "parameters": {},
                },
                {
                    "tool": "Transform",
                    "description": "Transform data",
                    "parameters": {},
                },
                {"tool": "Analyze", "description": "Analyze results", "parameters": {}},
                {"tool": "Export", "description": "Export results", "parameters": {}},
            ]

        # Filter steps based on available tools
        for step in potential_steps[:max_steps]:
            tool_name = step["tool"]
            if any(tool_name in str(tool) for tool in available_tools):
                plan_steps.append(step)

        # Apply constraints
        if "time_limit" in constraints:
            # Mock time estimation
            estimated_time = len(plan_steps) * 10  # 10 seconds per step
            if estimated_time > constraints["time_limit"]:
                plan_steps = plan_steps[: constraints["time_limit"] // 10]

        return {
            "goal": goal,
            "plan": plan_steps,
            "estimated_steps": len(plan_steps),
            "constraints": constraints,
            "feasibility": "high" if plan_steps else "low",
            "reasoning": f"Created a {len(plan_steps)}-step plan to achieve: {goal}",
        }
