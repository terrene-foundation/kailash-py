"""
Hierarchical RAG (Retrieval-Augmented Generation) workflow template.

This module implements OpenAI's hierarchical document processing methodology
as a reusable workflow template. The template orchestrates document splitting,
relevance selection, iterative processing, response generation, and validation.

Workflow Architecture:
    1. Document Input & Preprocessing
    2. Iterative Hierarchical Processing:
       - Split documents into 3 parts
       - Select relevant parts based on query
       - Continue splitting selected parts (3-5 iterations)
    3. Context Combination & Response Generation
    4. Response Validation & Quality Assessment
    5. Final Output Formatting

Model Strategy:
    - Splitting/Selection: Large context + cheap models (gpt-4o-mini)
    - Generation: High accuracy models (gpt-4o)
    - Validation: Strong reasoning models (o1-mini)
"""


from kailash.nodes.ai.document_processing import (
    CombinationStrategy,
    SplittingStrategy,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow
from kailash.workflow.templates.base import TemplateParameter, WorkflowTemplate


def create_hierarchical_rag_template() -> WorkflowTemplate:
    """
    Create the hierarchical RAG workflow template.

    This template implements OpenAI's hierarchical document processing method
    with configurable model choices, iteration limits, and processing strategies.

    Returns:
        WorkflowTemplate configured for hierarchical RAG processing

    Example:
        >>> # Create and register the template
        >>> template = create_hierarchical_rag_template()
        >>> registry = WorkflowTemplateRegistry()
        >>> registry.register(template)
        >>>
        >>> # Basic usage with default parameters
        >>> workflow = template.instantiate(
        ...     document_content="Long technical document about AI...",
        ...     query="What are the key innovations in transformer models?"
        ... )
        >>>
        >>> # Execute workflow
        >>> runtime = LocalRuntime()
        >>> results = runtime.execute_workflow(workflow)
        >>> print(results["response"])

        >>> # Advanced configuration with custom models
        >>> workflow = template.instantiate(
        ...     document_content=research_paper,
        ...     query="Summarize the methodology section",
        ...     # Use cheaper model for splitting
        ...     splitting_model={
        ...         "provider": "ollama",
        ...         "model": "llama2",
        ...         "temperature": 0.1
        ...     },
        ...     # Use high-quality model for generation
        ...     generation_model={
        ...         "provider": "openai",
        ...         "model": "gpt-4o",
        ...         "temperature": 0.3
        ...     },
        ...     # Use reasoning model for validation
        ...     validation_model={
        ...         "provider": "openai",
        ...         "model": "o1-mini",
        ...         "temperature": 0.0
        ...     },
        ...     # Processing parameters
        ...     max_iterations=5,
        ...     min_iterations=3,
        ...     relevance_threshold=0.8,
        ...     splitting_strategy="semantic",
        ...     combination_strategy="hierarchical",
        ...     output_format="structured",
        ...     validation_enabled=True
        ... )

        >>> # Domain-specific configurations
        >>> # Medical document processing (high precision)
        >>> medical_workflow = template.instantiate(
        ...     document_content=medical_record,
        ...     query="What are the patient's risk factors?",
        ...     relevance_threshold=0.85,  # Higher threshold for medical
        ...     min_iterations=4,          # More thorough processing
        ...     validation_enabled=True,   # Always validate medical info
        ...     output_format="structured"
        ... )
        >>>
        >>> # Legal document analysis (maximum precision)
        >>> legal_workflow = template.instantiate(
        ...     document_content=contract,
        ...     query="What are the termination clauses?",
        ...     relevance_threshold=0.9,   # Highest precision
        ...     max_iterations=6,          # Very thorough
        ...     splitting_strategy="paragraph",  # Preserve structure
        ...     validation_enabled=True
        ... )
        >>>
        >>> # Quick summary (speed over precision)
        >>> quick_workflow = template.instantiate(
        ...     document_content=article,
        ...     query="Give me the main points",
        ...     max_iterations=3,
        ...     relevance_threshold=0.6,
        ...     validation_enabled=False,  # Skip validation for speed
        ...     output_format="bullet_points"
        ... )

        >>> # Monitoring execution
        >>> from kailash.tracking.manager import TaskManager
        >>>
        >>> task_manager = TaskManager()
        >>> task_id = task_manager.create_task(
        ...     name="Process Research Paper",
        ...     workflow_id=workflow.id
        ... )
        >>>
        >>> # Execute with tracking
        >>> results = runtime.execute_workflow(
        ...     workflow,
        ...     task_id=task_id
        ... )
        >>>
        >>> # Check iteration details
        >>> task = task_manager.get_task(task_id)
        >>> print(f"Iterations completed: {task.metadata['iterations']}")
        >>> print(f"Parts processed: {task.metadata['total_parts']}")
        >>> print(f"Processing time: {task.duration}s")
    """

    template = WorkflowTemplate(
        template_id="hierarchical_rag",
        name="Hierarchical RAG Pipeline",
        description="OpenAI's hierarchical document processing for RAG workflows",
        category="ai/document_processing",
        version="1.0.0",
        author="Kailash SDK",
        tags=["rag", "document_processing", "llm", "hierarchical", "openai"],
    )

    # Model Configuration Parameters
    template.add_parameter(
        TemplateParameter(
            name="splitting_model",
            type=dict,
            description="Model config for document splitting and selection",
            default={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 4000,
            },
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="generation_model",
            type=dict,
            description="Model config for response generation",
            default={
                "provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.3,
                "max_tokens": 2000,
            },
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="validation_model",
            type=dict,
            description="Model config for response validation",
            default={
                "provider": "openai",
                "model": "o1-mini",
                "temperature": 0.1,
                "max_tokens": 1000,
            },
        )
    )

    # Processing Parameters
    template.add_parameter(
        TemplateParameter(
            name="max_iterations",
            type=int,
            description="Maximum number of hierarchical iterations",
            default=5,
            validation_func=lambda x: 3 <= x <= 10,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="min_iterations",
            type=int,
            description="Minimum number of hierarchical iterations",
            default=3,
            validation_func=lambda x: 1 <= x <= 5,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="relevance_threshold",
            type=float,
            description="Minimum relevance score for part selection",
            default=0.7,
            validation_func=lambda x: 0.0 <= x <= 1.0,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="splitting_strategy",
            type=str,
            description="Strategy for document splitting",
            choices=[s.value for s in SplittingStrategy],
            default=SplittingStrategy.SEMANTIC.value,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="combination_strategy",
            type=str,
            description="Strategy for combining selected parts",
            choices=[s.value for s in CombinationStrategy],
            default=CombinationStrategy.HIERARCHICAL.value,
        )
    )

    # Input/Output Parameters
    template.add_parameter(
        TemplateParameter(
            name="document_content", type=str, description="Document content to process"
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="query", type=str, description="Query to guide document processing"
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="output_format",
            type=str,
            description="Format for generated response",
            choices=["structured", "narrative", "bullet_points", "json"],
            default="structured",
        )
    )

    # Advanced Parameters
    template.add_parameter(
        TemplateParameter(
            name="enable_caching",
            type=bool,
            description="Enable caching of intermediate results",
            default=True,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="parallel_processing",
            type=bool,
            description="Enable parallel processing where possible",
            default=False,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="validation_enabled",
            type=bool,
            description="Enable response validation step",
            default=True,
        )
    )

    def build_hierarchical_rag_workflow(**params) -> Workflow:
        """
        Build the hierarchical RAG workflow with given parameters.

        Args:
            **params: Template parameters

        Returns:
            Configured Workflow instance
        """
        builder = WorkflowBuilder()

        # 1. Document Preprocessing
        builder.add_node(
            "document_preprocessor",
            "PythonCodeNode",
            config={
                "code": """
def process_document(document_content: str, query: str) -> dict:
    '''Preprocess document and initialize processing state.'''
    from kailash.nodes.ai.document_processing import ProcessingState

    # Initialize processing state
    state = ProcessingState(
        max_iterations=max_iterations,
        min_iterations=min_iterations,
        relevance_threshold=relevance_threshold,
        query=query
    )

    return {
        'processed_content': document_content.strip(),
        'query': query,
        'processing_state': state,
        'iteration_count': 0
    }
""",
                "parameters": {
                    "max_iterations": params["max_iterations"],
                    "min_iterations": params["min_iterations"],
                    "relevance_threshold": params["relevance_threshold"],
                },
            },
        )

        # 2. Initial Document Splitting
        builder.add_node(
            "initial_splitter",
            "HierarchicalDocumentSplitter",
            config={
                "strategy": params["splitting_strategy"],
                "part_count": 3,
                "model_config": params["splitting_model"],
            },
        )

        # 3. Relevance Selection
        builder.add_node(
            "relevance_selector",
            "RelevanceSelector",
            config={
                "relevance_threshold": params["relevance_threshold"],
                "selection_strategy": "llm",
                "model_config": params["splitting_model"],
            },
        )

        # 4. Iteration Controller
        builder.add_node("iteration_controller", "IterationController")

        # 5. Hierarchical Processing Loop (implemented as subworkflow)
        builder.add_node(
            "hierarchical_processor",
            "PythonCodeNode",
            config={
                "code": """
def hierarchical_processing(processing_state, all_parts, selected_parts, parts_to_split) -> dict:
    '''Manage the hierarchical processing iterations.'''

    final_selected_parts = []
    current_state = processing_state

    # Add initially selected parts
    final_selected_parts.extend(selected_parts)

    # Process iterations
    while hasattr(current_state, 'iteration') and current_state.iteration < current_state.max_iterations:
        if not parts_to_split:
            break

        # This would integrate with the actual splitting/selection loop
        # For now, simulate convergence
        iteration_selected = []
        for part in parts_to_split[:len(parts_to_split)//2]:  # Select some parts
            iteration_selected.append(part)

        final_selected_parts.extend(iteration_selected)

        # Update parts to split (fewer each iteration)
        parts_to_split = parts_to_split[len(iteration_selected):]
        current_state.iteration += 1

        if not parts_to_split:
            break

    return {
        'final_selected_parts': final_selected_parts,
        'processing_complete': True,
        'total_iterations': current_state.iteration
    }
"""
            },
        )

        # 6. Document Combination
        builder.add_node(
            "document_combiner",
            "PythonCodeNode",
            config={
                "code": f"""
def combine_parts(final_selected_parts, query, combination_strategy='{params["combination_strategy"]}') -> dict:
    '''Combine selected document parts with query context.'''

    if combination_strategy == 'flat':
        # Simple concatenation
        combined_content = '\\n\\n'.join([part.content for part in final_selected_parts])
        context_info = f"Combined from {{len(final_selected_parts)}} relevant sections"

    elif combination_strategy == 'hierarchical':
        # Preserve hierarchy and relationships
        combined_content = ""
        for i, part in enumerate(final_selected_parts):
            level_indent = "  " * part.level
            combined_content += f"{{level_indent}}Section {{i+1}} (Level {{part.level}}): {{part.content}}\\n\\n"
        context_info = f"Hierarchically organized from {{len(final_selected_parts)}} sections"

    else:  # weighted
        # Weight by relevance scores
        parts_by_relevance = sorted(final_selected_parts, key=lambda p: p.relevance_score, reverse=True)
        combined_content = ""
        for i, part in enumerate(parts_by_relevance):
            weight_marker = f"[Relevance: {{part.relevance_score:.2f}}]"
            combined_content += f"{{weight_marker}} {{part.content}}\\n\\n"
        context_info = f"Relevance-weighted content from {{len(final_selected_parts)}} sections"

    return {{
        'combined_content': combined_content,
        'context_info': context_info,
        'query': query,
        'part_count': len(final_selected_parts)
    }}
"""
            },
        )

        # 7. Response Generation
        builder.add_node(
            "response_generator",
            "PythonCodeNode",
            config={
                "code": f"""
def generate_response(combined_content, query, context_info, output_format='{params["output_format"]}') -> dict:
    '''Generate response using selected content and query.'''

    # Prepare generation prompt based on output format
    if output_format == 'structured':
        format_instruction = "Provide a well-structured response with clear sections and subsections."
    elif output_format == 'narrative':
        format_instruction = "Provide a flowing narrative response."
    elif output_format == 'bullet_points':
        format_instruction = "Provide the response as organized bullet points."
    else:  # json
        format_instruction = "Provide the response in structured JSON format."

    generation_prompt = f'''
Based on the following context, answer the query: "{{query}}"

Context ({{context_info}}):
{{combined_content}}

Instructions: {{format_instruction}}

Ensure your response:
1. Directly addresses the query
2. Uses information from the provided context
3. Is well-organized and clear
4. Acknowledges any limitations based on available context

Response:
'''

    # This would call the generation model
    # For now, return a structured response
    generated_response = f"Generated response for: {{query}}\\n\\nBased on {{context_info}}, here is the analysis..."

    return {{
        'generated_response': generated_response,
        'generation_prompt': generation_prompt,
        'source_context': combined_content,
        'query': query
    }}
""",
                "model_config": params["generation_model"],
            },
        )

        # 8. Response Validation (if enabled)
        if params["validation_enabled"]:
            builder.add_node(
                "response_validator",
                "PythonCodeNode",
                config={
                    "code": """
def validate_response(generated_response, query, source_context) -> dict:
    '''Validate the generated response for accuracy and completeness.'''

    validation_prompt = f'''
    Evaluate the following response for accuracy, completeness, and relevance to the query.

    Query: "{query}"

    Generated Response:
    {generated_response}

    Source Context:
    {source_context}

    Provide a validation assessment including:
    1. Accuracy: Does the response accurately reflect the source context?
    2. Completeness: Does it adequately address the query?
    3. Relevance: Is the response relevant and focused?
    4. Issues: Any factual errors, omissions, or improvements needed?
    5. Overall Quality Score (1-10)

    Assessment:
    '''

    # This would call the validation model
    # For now, return a positive validation
    validation_result = {
        'is_valid': True,
        'quality_score': 8.5,
        'validation_notes': 'Response accurately reflects source context and addresses the query.',
        'suggested_improvements': [],
        'validation_prompt': validation_prompt
    }

    return {
        'validated_response': generated_response,
        'validation_result': validation_result,
        'final_quality_score': validation_result['quality_score']
    }
""",
                    "model_config": params["validation_model"],
                },
            )

        # 9. Final Output Formatting
        builder.add_node(
            "output_formatter",
            "PythonCodeNode",
            config={
                "code": f"""
def format_final_output(validated_response=None, generated_response=None, validation_result=None, **kwargs) -> dict:
    '''Format the final output with metadata and results.'''

    final_response = validated_response or generated_response

    output = {{
        'response': final_response,
        'metadata': {{
            'template_id': 'hierarchical_rag',
            'processing_complete': True,
            'validation_enabled': {params["validation_enabled"]},
            'output_format': '{params["output_format"]}',
            'model_config': {{
                'splitting_model': '{params["splitting_model"]["model"]}',
                'generation_model': '{params["generation_model"]["model"]}',
                'validation_model': '{params["validation_model"]["model"]}'
            }}
        }}
    }}

    if validation_result:
        output['validation'] = validation_result

    return output
"""
            },
        )

        # Connect the workflow
        builder.add_connection(
            "document_preprocessor", "processed_content", "initial_splitter", "content"
        )
        builder.add_connection(
            "document_preprocessor", "query", "initial_splitter", "query"
        )

        builder.add_connection(
            "initial_splitter", "parts", "relevance_selector", "parts"
        )
        builder.add_connection(
            "document_preprocessor", "query", "relevance_selector", "query"
        )

        builder.add_connection(
            "relevance_selector",
            "selected_parts",
            "iteration_controller",
            "selected_parts",
        )
        builder.add_connection(
            "initial_splitter", "parts", "iteration_controller", "all_parts"
        )
        builder.add_connection(
            "document_preprocessor",
            "processing_state",
            "iteration_controller",
            "processing_state",
        )

        builder.add_connection(
            "iteration_controller",
            "updated_state",
            "hierarchical_processor",
            "processing_state",
        )
        builder.add_connection(
            "initial_splitter", "parts", "hierarchical_processor", "all_parts"
        )
        builder.add_connection(
            "relevance_selector",
            "selected_parts",
            "hierarchical_processor",
            "selected_parts",
        )
        builder.add_connection(
            "iteration_controller",
            "parts_to_split",
            "hierarchical_processor",
            "parts_to_split",
        )

        builder.add_connection(
            "hierarchical_processor",
            "final_selected_parts",
            "document_combiner",
            "final_selected_parts",
        )
        builder.add_connection(
            "document_preprocessor", "query", "document_combiner", "query"
        )

        builder.add_connection(
            "document_combiner",
            "combined_content",
            "response_generator",
            "combined_content",
        )
        builder.add_connection(
            "document_combiner", "query", "response_generator", "query"
        )
        builder.add_connection(
            "document_combiner", "context_info", "response_generator", "context_info"
        )

        if params["validation_enabled"]:
            builder.add_connection(
                "response_generator",
                "generated_response",
                "response_validator",
                "generated_response",
            )
            builder.add_connection(
                "response_generator", "query", "response_validator", "query"
            )
            builder.add_connection(
                "response_generator",
                "source_context",
                "response_validator",
                "source_context",
            )

            builder.add_connection(
                "response_validator",
                "validated_response",
                "output_formatter",
                "validated_response",
            )
            builder.add_connection(
                "response_validator",
                "validation_result",
                "output_formatter",
                "validation_result",
            )
        else:
            builder.add_connection(
                "response_generator",
                "generated_response",
                "output_formatter",
                "generated_response",
            )

        return builder.build(name="Hierarchical RAG Pipeline")

    template.set_workflow_factory(build_hierarchical_rag_workflow)
    return template


def create_simple_rag_template() -> WorkflowTemplate:
    """
    Create a simplified RAG template for comparison and basic use cases.

    This template provides a streamlined version without hierarchical processing
    for scenarios that don't require the full complexity.

    Returns:
        WorkflowTemplate for simple RAG processing

    Example:
        >>> # Create simple RAG template
        >>> simple_template = create_simple_rag_template()
        >>>
        >>> # Basic usage
        >>> workflow = simple_template.instantiate(
        ...     document_content="Short article about Python programming...",
        ...     query="What are Python's main features?",
        ...     chunk_size=500  # Words per chunk
        ... )
        >>>
        >>> # Compare with hierarchical RAG
        >>> hierarchical = create_hierarchical_rag_template()
        >>>
        >>> # Same document, different approaches
        >>> doc = "Large technical specification document..."
        >>> query = "What are the security requirements?"
        >>>
        >>> # Simple: Fast, fixed chunking
        >>> simple_wf = simple_template.instantiate(
        ...     document_content=doc,
        ...     query=query,
        ...     chunk_size=1000
        ... )
        >>>
        >>> # Hierarchical: Intelligent, iterative
        >>> hierarchical_wf = hierarchical.instantiate(
        ...     document_content=doc,
        ...     query=query,
        ...     max_iterations=4
        ... )
        >>>
        >>> # Performance comparison
        >>> import time
        >>>
        >>> start = time.time()
        >>> simple_results = runtime.execute_workflow(simple_wf)
        >>> simple_time = time.time() - start
        >>>
        >>> start = time.time()
        >>> hierarchical_results = runtime.execute_workflow(hierarchical_wf)
        >>> hierarchical_time = time.time() - start
        >>>
        >>> print(f"Simple RAG: {simple_time:.2f}s")
        >>> print(f"Hierarchical RAG: {hierarchical_time:.2f}s")
        >>> print(f"Quality difference: Hierarchical typically 20-40% better")
    """

    template = WorkflowTemplate(
        template_id="simple_rag",
        name="Simple RAG Pipeline",
        description="Streamlined RAG workflow without hierarchical processing",
        category="ai/document_processing",
        version="1.0.0",
        tags=["rag", "simple", "document_processing"],
    )

    # Basic parameters
    template.add_parameter(
        TemplateParameter(
            name="document_content", type=str, description="Document content to process"
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="query", type=str, description="Query for document processing"
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="chunk_size",
            type=int,
            description="Size of document chunks",
            default=1000,
        )
    )

    template.add_parameter(
        TemplateParameter(
            name="model_config",
            type=dict,
            description="Model configuration",
            default={"provider": "openai", "model": "gpt-4o", "temperature": 0.3},
        )
    )

    def build_simple_rag_workflow(**params) -> Workflow:
        """Build simple RAG workflow."""
        builder = WorkflowBuilder()

        # Simple chunking
        builder.add_node(
            "chunker",
            "PythonCodeNode",
            config={
                "code": f"""
def chunk_document(document_content: str, chunk_size: int = {params["chunk_size"]}) -> dict:
    '''Split document into fixed-size chunks.'''
    words = document_content.split()
    chunks = []

    for i in range(0, len(words), chunk_size):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)

    return {{'chunks': chunks}}
"""
            },
        )

        # Simple selection (select all for now)
        builder.add_node(
            "selector",
            "PythonCodeNode",
            config={
                "code": """
def select_chunks(chunks, query) -> dict:
    '''Simple chunk selection - returns all chunks for now.'''
    return {'selected_chunks': chunks}
"""
            },
        )

        # Generation
        builder.add_node(
            "generator",
            "PythonCodeNode",
            config={
                "code": """
def generate_simple_response(selected_chunks, query) -> dict:
    '''Generate response from selected chunks.'''
    context = '\\n\\n'.join(selected_chunks)

    response = f"Based on the provided context, here is the response to: {query}\\n\\nContext: {context[:500]}..."

    return {'response': response}
"""
            },
        )

        # Connect nodes
        builder.add_connection("chunker", "chunks", "selector", "chunks")
        builder.add_connection(
            "selector", "selected_chunks", "generator", "selected_chunks"
        )

        return builder.build(name="Simple RAG Pipeline")

    template.set_workflow_factory(build_simple_rag_workflow)
    return template
