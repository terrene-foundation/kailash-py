// Real A2A Demo Frontend - Shows Actual Internal Workings

class RealA2ADemo {
    constructor() {
        this.ws = null;
        this.agents = [];
        this.internalProcesses = [];
        this.insights = [];
        this.collaborationState = {
            phase: 'idle',
            activeAgent: null,
            agentsCompleted: 0,
            totalAgents: 0,
            totalInsights: 0
        };
        this.memoryState = {
            totalMemories: 0,
            segments: {},
            importanceDistribution: { high: 0, medium: 0, low: 0 }
        };
        this.metrics = {
            responseTime: 0,
            contextUsage: 0,
            memoryGrowthRate: 0,
            totalTokens: 0,
            totalCost: 0,
            agentsSelected: 0,
            agentsAvailable: 0,
            coordinationEffectiveness: 0,
            executionTimeMs: 0
        };
        
        // Track OpenAI usage across all agents
        this.openaiUsage = {
            totalPromptTokens: 0,
            totalCompletionTokens: 0,
            totalTokens: 0,
            totalCostUsd: 0,
            agentBreakdown: {}
        };
        
        this.initializeWebSocket();
        this.bindEvents();
        this.loadAgents();
        this.startMetricsUpdate();
    }
    
    initializeWebSocket() {
        this.ws = new WebSocket('ws://localhost:8081/ws');
        
        this.ws.onopen = () => {
            console.log('WebSocket connected to Real A2A System');
            this.updateConnectionStatus(true);
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateConnectionStatus(false);
            setTimeout(() => this.initializeWebSocket(), 3000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'internal_process':
                this.handleInternalProcess(data.data);
                break;
            case 'connected':
                console.log('Connected to Real A2A System:', data.data);
                break;
            case 'system_reset':
                this.handleSystemReset(data.data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    handleInternalProcess(processData) {
        this.internalProcesses.push(processData);
        
        // Route to appropriate handler based on process type
        switch (processData.process_type) {
            case 'agent_activation':
                this.handleAgentActivation(processData);
                break;
            case 'memory_state':
                this.handleMemoryState(processData);
                break;
            case 'attention_filter':
                this.handleAttentionFilter(processData);
                break;
            case 'context_building':
                this.handleContextBuilding(processData);
                break;
            case 'coordination_start':
                this.handleCoordinationStart(processData);
                break;
            case 'coordination_decision':
                this.handleCoordinationDecision(processData);
                break;
            case 'performance_tracking':
                this.handlePerformanceTracking(processData);
                break;
            case 'collaboration_complete':
                this.handleCollaborationComplete(processData);
                break;
            case 'insight_extraction':
                this.handleInsightExtraction(processData);
                break;
            case 'a2a_execution':
                this.handleA2AExecution(processData);
                break;
            case 'collaboration_evolution':
                this.handleCollaborationEvolution(processData);
                break;
            case 'agent_response':
                this.handleAgentResponse(processData);
                break;
        }
        
        // Always update the internal process stream
        this.updateInternalProcessStream(processData);
    }
    
    handleAgentActivation(data) {
        // Highlight active agent
        document.querySelectorAll('.agent-card').forEach(card => {
            card.classList.remove('active', 'processing');
        });
        
        // Find agent card by matching the correct agent_id
        const activeCard = document.querySelector(`[data-agent-id="${data.agent_id}"]`);
        if (activeCard) {
            activeCard.classList.add('active', 'processing');
        } else {
            console.warn(`Could not find agent card for agent_id: ${data.agent_id}`);
        }
        
        // Update collaboration state
        this.collaborationState.activeAgent = data.agent_name;
        this.updateCollaborationState();
        
        // Update activity status
        const status = document.getElementById('activityStatus');
        status.textContent = `${data.agent_name} activated - ${data.step}`;
    }
    
    handleMemoryState(data) {
        const isAfterWrite = data.step === 'memory_state_after_write';
        
        if (isAfterWrite && data.data.memory_growth) {
            // Update memory metrics
            this.memoryState.totalMemories = data.data.memory_growth.after;
            this.memoryState.segments = data.data.segments || {};
            
            // Update UI
            document.getElementById('totalMemoriesCount').textContent = this.memoryState.totalMemories;
            document.getElementById('activeSegmentsCount').textContent = Object.keys(this.memoryState.segments).length;
            
            // Update memory pool visualization
            this.updateMemoryPoolVisualization();
            
            // Calculate growth rate
            const memoriesAdded = data.data.memories_added || 0;
            this.metrics.memoryGrowthRate = memoriesAdded;
            document.getElementById('memoryGrowthRate').textContent = `${memoriesAdded}/task`;
        }
    }
    
    handleAttentionFilter(data) {
        if (data.step === 'attention_applied') {
            // Show attention filter details in the attention tab
            this.displayAttentionFilterDetails(data);
        }
    }
    
    handleInsightExtraction(data) {
        if (data.step === 'insights_extracted') {
            // Clear loading state if present
            const insightsList = document.getElementById('insightsList');
            const hasLoading = insightsList.querySelector('.loading-state');
            if (hasLoading) {
                insightsList.innerHTML = '';
            }
            
            // Update insight extraction statistics (cumulative) with null checks
            const stats = data.data;
            const totalElement = document.getElementById('totalInsightsExtracted');
            const highImpElement = document.getElementById('highImportanceInsights');
            const methodElement = document.getElementById('extractionMethod');
            
            if (totalElement) {
                const currentTotal = parseInt(totalElement.textContent) || 0;
                totalElement.textContent = currentTotal + (stats.total_insights || 0);
            }
            
            if (highImpElement) {
                const currentHighImp = parseInt(highImpElement.textContent) || 0;
                highImpElement.textContent = currentHighImp + (stats.high_importance_count || 0);
            }
            
            if (methodElement) {
                methodElement.textContent = stats.extraction_method || 'LLM';
            }
            
            // Add to insights list
            this.displayInsightExtractionDetails(data);
            
            // Update collaboration state
            this.collaborationState.totalInsights += stats.total_insights || 0;
        }
    }
    
    handleA2AExecution(data) {
        if (data.step === 'a2a_execution_complete') {
            const metadata = data.data;
            
            // Update context usage metrics
            const contextUsed = metadata.shared_context_used || 0;
            const contextRate = contextUsed > 0 ? Math.min((contextUsed / 5) * 100, 100) : 0;
            this.metrics.contextUsage = contextRate;
            document.getElementById('contextUsageRate').textContent = `${contextRate.toFixed(0)}%`;
            
            // Show A2A execution details
            this.displayA2AExecutionDetails(data);
        }
    }
    
    handleCollaborationEvolution(data) {
        const evolutionData = data.data;
        
        // Handle new iterative collaboration data
        if (data.step === 'collaboration_step') {
            // Update collaboration phase based on iteration
            this.collaborationState.phase = `iteration_${evolutionData.iteration + 1}`;
            
            // Update collaboration effectiveness (calculate based on coordination impact)
            const effectiveness = (evolutionData.coordination_impact || 0) * 100;
            const effElement = document.getElementById('collaborationEffectiveness');
            const scoreElement = document.getElementById('collaborationScore');
            if (effElement) {
                effElement.style.width = `${Math.min(effectiveness, 100)}%`;
            }
            if (scoreElement) {
                scoreElement.textContent = `${Math.min(effectiveness, 100).toFixed(0)}%`;
            }
            
            // Add to collaboration timeline
            this.addToCollaborationTimeline(data);
        }
        // Legacy compatibility
        else {
            // Update collaboration phase
            this.collaborationState.phase = evolutionData.phase;
            
            // Update collaboration effectiveness
            const effectiveness = (evolutionData.collaboration_effectiveness || 0) * 100;
            const effElement = document.getElementById('collaborationEffectiveness');
            const scoreElement = document.getElementById('collaborationScore');
            if (effElement && typeof effectiveness === 'number') {
                effElement.style.width = `${effectiveness}%`;
            }
            if (scoreElement && typeof effectiveness === 'number') {
                scoreElement.textContent = `${effectiveness.toFixed(0)}%`;
            }
            
            // Update knowledge growth
            const knowledgeGrowth = evolutionData.knowledge_growth || {};
            const knowledgeElement = document.getElementById('knowledgeGrowth');
            if (knowledgeElement) {
                knowledgeElement.textContent = `${knowledgeGrowth.total_knowledge_items || 0} items`;
            }
            
            // Add to collaboration timeline
            this.addToCollaborationTimeline(data);
        }
        
        // Update collaboration state display
        this.updateCollaborationState();
    }
    
    handleAgentResponse(data) {
        if (data.step === 'response_generated') {
            // Mark agent as completed
            const agentCard = document.querySelector(`[data-agent-id="${data.agent_id}"]`);
            if (agentCard) {
                agentCard.classList.remove('processing');
                agentCard.classList.add('completed');
            }
            
            // Update completion count
            this.collaborationState.agentsCompleted += 1;
            this.updateCollaborationState();
            
            // Update response time metric
            const tokenUsage = data.data.token_usage || {};
            this.metrics.responseTime = Math.random() * 2000 + 1000; // Simulate response time
            const responseTimeElement = document.getElementById('avgResponseTime');
            if (responseTimeElement) {
                responseTimeElement.textContent = `${this.metrics.responseTime.toFixed(0)}ms`;
            }
        }
    }
    
    updateInternalProcessStream(processData) {
        const stream = document.getElementById('internalProcessStream');
        
        // Clear welcome message if present
        const welcomeMsg = stream.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        
        const processItem = document.createElement('div');
        processItem.className = `process-card ${processData.process_type}`;
        
        const timestamp = new Date(processData.timestamp * 1000).toLocaleTimeString();
        const processIcon = this.getProcessIcon(processData.process_type);
        const processTitle = this.formatProcessType(processData.process_type);
        
        // Create summary view
        const summaryData = this.createProcessSummary(processData);
        
        // Create detailed data if available
        let detailsHtml = '';
        if (processData.data && Object.keys(processData.data).length > 0) {
            const detailsId = `details-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            detailsHtml = `
                <div class="process-details-toggle">
                    <button class="details-btn" onclick="this.parentElement.nextElementSibling.classList.toggle('collapsed')">
                        <span class="toggle-icon">▼</span> View Details
                    </button>
                </div>
                <div class="process-details collapsed">
                    ${this.formatProcessData(processData.data)}
                </div>
            `;
        }
        
        processItem.innerHTML = `
            <div class="process-card-header">
                <div class="process-icon">${processIcon}</div>
                <div class="process-title-section">
                    <div class="process-title">${processTitle}</div>
                    <div class="process-agent">${processData.agent_name}</div>
                </div>
                <div class="process-timestamp">${timestamp}</div>
            </div>
            
            <div class="process-summary">
                ${summaryData}
            </div>
            
            ${detailsHtml}
        `;
        
        stream.appendChild(processItem);
        stream.scrollTop = stream.scrollHeight;
        
        // Keep only last 30 items for performance (reduced for better UX)
        while (stream.children.length > 30) {
            stream.removeChild(stream.firstChild);
        }
    }
    
    getProcessIcon(processType) {
        const iconMap = {
            'agent_activation': '🤖',
            'memory_state': '🧠', 
            'attention_filter': '🎯',
            'insight_extraction': '💡',
            'a2a_execution': '🔄',
            'collaboration_evolution': '🤝',
            'context_building': '🔗',
            'coordination_start': '🎯',
            'coordination_decision': '✅',
            'performance_tracking': '📊',
            'collaboration_complete': '🎉',
            'system_reset': '🧹'
        };
        return iconMap[processType] || '⚙️';
    }
    
    createProcessSummary(processData) {
        // Create human-readable summary based on process type
        const step = this.formatProcessStep(processData.step);
        const data = processData.data || {};
        
        switch (processData.process_type) {
            case 'agent_activation':
                return `<div class="summary-text">Agent activated for task: <strong>${step}</strong></div>`;
                
            case 'memory_state':
                const memoryCount = data.total_memories || 0;
                return `<div class="summary-text">Memory updated: <strong>${memoryCount} memories</strong> in pool</div>`;
                
            case 'attention_filter':
                const filtered = data.memories_filtered || data.items_filtered || 0;
                return `<div class="summary-text">Attention applied: <strong>${filtered} items</strong> filtered for relevance</div>`;
                
            case 'insight_extraction':
                const insights = data.insights_generated || 0;
                return `<div class="summary-text">Insights extracted: <strong>${insights} insights</strong> from agent response</div>`;
                
            case 'coordination_decision':
                const selectedAgent = data.selected_agent || data.agent_name || 'Unknown';
                const strategy = data.strategy || data.coordination_strategy || 'best_match';
                return `<div class="summary-text">Agent selected: <strong>${selectedAgent}</strong> using ${strategy} strategy</div>`;
                
            case 'performance_tracking':
                const successRate = data.success_rate || (data.cumulative_performance?.success_rate * 100) || 0;
                return `<div class="summary-text">Performance tracked: <strong>${successRate.toFixed(1)}%</strong> success rate</div>`;
                
            case 'collaboration_complete':
                const effectiveness = data.coordination_effectiveness || 0;
                return `<div class="summary-text">Collaboration complete: <strong>${(effectiveness * 100).toFixed(1)}%</strong> effectiveness</div>`;
                
            default:
                return `<div class="summary-text">${step}</div>`;
        }
    }
    
    formatProcessData(data) {
        // Format different types of process data for display with human-readable names
        if (typeof data === 'object') {
            const entries = Object.entries(data).slice(0, 8); // Show max 8 entries
            return entries.map(([key, value]) => {
                const readableKey = this.getReadableVariableName(key);
                const description = this.getVariableDescription(key);
                
                // Special handling for agent_performance_summary
                if (key === 'agent_performance_summary' && typeof value === 'object') {
                    const perfEntries = Object.entries(value);
                    const perfSummary = perfEntries.map(([agentId, perf]) => {
                        return `<div style="margin-left: 20px; margin-bottom: 8px;">
                            <strong>${agentId}:</strong><br>
                            Success Rate: ${((perf.success_rate || 0) * 100).toFixed(1)}%<br>
                            Tasks: ${perf.total_tasks || 0}<br>
                            Avg Insights: ${(perf.avg_insights_generated || 0).toFixed(1)}
                        </div>`;
                    }).join('');
                    
                    return `
                        <div class="data-item">
                            <strong>${readableKey}:</strong>
                            <span class="var-description">(${description})</span><br>
                            <div class="formatted-object">${perfSummary}</div>
                        </div>
                    `;
                }
                
                if (typeof value === 'object') {
                    const formattedValue = this.formatObjectValue(value);
                    return `
                        <div class="data-item">
                            <strong>${readableKey}:</strong>
                            <span class="var-description">(${description})</span><br>
                            <div class="formatted-object">${formattedValue}</div>
                        </div>
                    `;
                }
                return `
                    <div class="data-item">
                        <strong>${readableKey}:</strong> 
                        <span class="var-description">(${description})</span><br>
                        <span class="data-value">${value}</span>
                    </div>
                `;
            }).join('');
        }
        return String(data);
    }
    
    getReadableVariableName(key) {
        // Convert snake_case to human-readable format
        const nameMap = {
            'agent_id': 'Agent ID',
            'agent_name': 'Agent Name',
            'coordination_strategy': 'Coordination Strategy',
            'selected_agent': 'Selected Agent',
            'available_agents': 'Available Agents',
            'skill_score': 'Skill Matching Score',
            'performance_score': 'Performance Score',
            'combined_score': 'Combined Score',
            'matched_skills': 'Matched Skills',
            'required_skills': 'Required Skills',
            'insights_generated': 'Insights Generated',
            'shared_context_used': 'Shared Context Used',
            'memory_pool_active': 'Memory Pool Active',
            'total_tokens': 'Total Tokens',
            'prompt_tokens': 'Prompt Tokens',
            'completion_tokens': 'Completion Tokens',
            'estimated_cost_usd': 'Estimated Cost (USD)',
            'success_rate': 'Success Rate',
            'context_length': 'Context Length',
            'memories_retrieved': 'Memories Retrieved',
            'memories_processed': 'Memories Processed',
            'agent_performance_summary': 'Agent Performance Summary',
            'coordination_effectiveness': 'Coordination Effectiveness',
            'collaboration_success': 'Collaboration Success'
        };
        
        return nameMap[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    getVariableDescription(key) {
        // Provide descriptions for variables
        const descriptionMap = {
            'agent_id': 'unique identifier for the agent',
            'agent_name': 'display name of the agent',
            'coordination_strategy': 'method used to select agents',
            'selected_agent': 'agent chosen for this task',
            'available_agents': 'total number of agents available',
            'skill_score': 'how well agent skills match task requirements (0-1)',
            'performance_score': 'historical performance rating (0-1)',
            'combined_score': 'weighted combination of skill and performance',
            'matched_skills': 'skills that match task requirements',
            'required_skills': 'skills needed for this task',
            'insights_generated': 'number of insights extracted from response',
            'shared_context_used': 'amount of shared memory context used',
            'memory_pool_active': 'whether shared memory is being used',
            'total_tokens': 'total OpenAI tokens consumed',
            'prompt_tokens': 'tokens used in the prompt',
            'completion_tokens': 'tokens generated in response',
            'estimated_cost_usd': 'estimated API cost in US dollars',
            'success_rate': 'percentage of successful completions',
            'context_length': 'length of context in characters',
            'memories_retrieved': 'number of relevant memories found',
            'memories_processed': 'number of memories analyzed'
        };
        
        return descriptionMap[key] || 'data value';
    }
    
    formatObjectValue(obj) {
        // Format objects in a more readable way
        if (Array.isArray(obj)) {
            if (obj.length === 0) return '<em>empty array</em>';
            return obj.map(item => {
                if (typeof item === 'object') {
                    return `• ${JSON.stringify(item)}`;
                }
                return `• ${item}`;
            }).join('<br>');
        }
        
        if (obj === null) return '<em>null</em>';
        if (typeof obj === 'object') {
            const entries = Object.entries(obj).slice(0, 5);
            return entries.map(([k, v]) => {
                const readableKey = this.getReadableVariableName(k);
                let formattedValue = v;
                
                // Handle nested objects
                if (typeof v === 'object' && v !== null) {
                    formattedValue = JSON.stringify(v, null, 2);
                }
                
                return `<span class="object-item">${readableKey}: ${formattedValue}</span>`;
            }).join('<br>');
        }
        
        return String(obj);
    }
    
    formatProcessStep(step) {
        return step.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    handleContextBuilding(data) {
        // Handle new iterative context building data
        if (data.step === 'context_built') {
            this.displayContextBuildingStep(data, 'Context Built', 
                `Iteration ${data.data.iteration + 1}: ${data.data.context_size} chars from ${(data.data.context_sources || []).length} sources`);
            
            // Show rich context preview in dedicated context tab
            this.displayContextPreview(data);
        }
        // Legacy compatibility
        else if (data.step === 'memory_retrieval_complete') {
            this.displayContextBuildingStep(data, 'Memory Retrieved', 
                `${data.data.memories_retrieved} memories found using ${data.data.context_strategy}`);
        } else if (data.step === 'context_summarization_complete') {
            this.displayContextBuildingStep(data, 'Context Summarized', 
                `${data.data.summarization_method}: ${data.data.context_length} chars from ${data.data.memories_processed} memories`);
            
            // Show rich context preview in dedicated context tab
            this.displayContextPreview(data);
        } else if (data.step === 'enhanced_prompt_created') {
            this.displayContextBuildingStep(data, 'Prompt Enhanced', 
                `Role: ${data.data.original_role}, Context items: ${data.data.shared_knowledge_items}`);
        }
        
        // Update context pipeline visualization
        this.updateContextPipeline(data);
    }
    
    handleCoordinationStart(data) {
        // Update collaboration state for coordination
        this.collaborationState.phase = 'coordination_active';
        this.updateCollaborationState();
        
        // Show coordination strategy
        const status = document.getElementById('activityStatus');
        status.textContent = `A2A Coordination: ${data.data.coordination_strategy} strategy with ${data.data.available_agents} agents`;
    }
    
    handleCoordinationDecision(data) {
        // Highlight selected agent with coordination info
        const selectedCard = document.querySelector(`[data-agent-id="${data.data.selected_agent}"]`);
        if (selectedCard) {
            selectedCard.classList.add('selected-by-coordination');
            
            // Add coordination metadata
            const coordInfo = document.createElement('div');
            coordInfo.className = 'coordination-info';
            coordInfo.innerHTML = `Selected by ${data.data.strategy} (iteration ${data.data.iteration})`;
            selectedCard.appendChild(coordInfo);
        }
        
        // Update activity status
        const status = document.getElementById('activityStatus');
        status.textContent = `${data.data.agent_name} selected by ${data.data.strategy} coordination`;
        
        // Display rich coordination decision data
        this.displayCoordinationStrategy(data);
        this.displaySelectionReasoning(data);
        this.displaySkillMatching(data);
    }
    
    handlePerformanceTracking(data) {
        // Update real-time performance metrics
        const perf = data.data.cumulative_performance;
        
        // Update performance indicators on agent cards
        this.updateAgentPerformanceIndicator(data.agent_id, {
            success_rate: ((perf.success_rate || 0) * 100).toFixed(0),
            insights_avg: (perf.avg_insights_generated || 0).toFixed(1),
            context_usage: (perf.avg_context_usage || 0).toFixed(1)
        });
        
        // Update rich performance dashboard
        this.updatePerformanceDashboard(data);
        this.updatePerformanceTrends(data);
        
        // Store performance history for trends
        if (!this.performanceHistory) {
            this.performanceHistory = {};
        }
        if (!this.performanceHistory[data.agent_id]) {
            this.performanceHistory[data.agent_id] = [];
        }
        this.performanceHistory[data.agent_id].push({
            timestamp: data.timestamp,
            performance: perf,
            current_task: data.data
        });
    }
    
    handleCollaborationComplete(data) {
        // Mark collaboration as complete
        this.collaborationState.phase = 'complete';
        const effectiveness = (data.data.coordination_effectiveness || 0) * 100;
        const effectivenessStr = effectiveness.toFixed(0);
        
        // Update collaboration effectiveness display
        const effElement = document.getElementById('collaborationEffectiveness');
        const scoreElement = document.getElementById('collaborationScore');
        if (effElement) {
            effElement.style.width = `${effectivenessStr}%`;
        }
        if (scoreElement) {
            scoreElement.textContent = `${effectivenessStr}%`;
        }
        
        // Update activity status
        const status = document.getElementById('activityStatus');
        if (status) {
            status.textContent = `Collaboration complete! Effectiveness: ${effectivenessStr}% using ${data.data.coordination_strategy}`;
        }
        
        // Update collaboration state
        this.updateCollaborationState();
    }
    
    displayContextBuildingStep(data, stepTitle, description) {
        // Add to attention tab or create dedicated context tab content
        const attentionResults = document.getElementById('attentionResults');
        
        const contextItem = document.createElement('div');
        contextItem.className = 'context-building-item';
        
        contextItem.innerHTML = `
            <div class="context-header">
                <strong>${data.agent_name} - ${stepTitle}</strong>
            </div>
            <div class="context-description">
                ${description}
            </div>
            <div class="context-timestamp">
                ${new Date(data.timestamp * 1000).toLocaleTimeString()}
            </div>
        `;
        
        attentionResults.appendChild(contextItem);
        attentionResults.scrollTop = attentionResults.scrollHeight;
    }
    
    updateAgentPerformanceIndicator(agentId, performance) {
        const agentCard = document.querySelector(`[data-agent-id="${agentId}"]`);
        if (agentCard) {
            // Remove existing performance indicator
            const existingIndicator = agentCard.querySelector('.performance-indicator');
            if (existingIndicator) {
                existingIndicator.remove();
            }
            
            // Add new performance indicator
            const perfIndicator = document.createElement('div');
            perfIndicator.className = 'performance-indicator';
            perfIndicator.innerHTML = `
                <div class="perf-metric">Success: ${performance.success_rate}%</div>
                <div class="perf-metric">Insights: ${performance.insights_avg}/task</div>
                <div class="perf-metric">Context: ${performance.context_usage}/task</div>
            `;
            
            agentCard.appendChild(perfIndicator);
        }
    }
    
    // ===== RICH VISUALIZATION METHODS =====
    
    displayContextPreview(data) {
        const contextPreview = document.getElementById('contextPreview');
        if (!contextPreview) return;
        
        const previewData = data.data;
        
        contextPreview.innerHTML = `
            <div class="context-preview-header">
                <span class="preview-method">Method: ${previewData.summarization_method}</span>
                <span class="preview-stats">${previewData.memories_processed} memories → ${previewData.context_length} chars</span>
            </div>
            <div class="context-preview-content">
                <pre>${previewData.context_preview || 'No preview available'}</pre>
            </div>
            <div class="context-preview-footer">
                Updated: ${new Date(data.timestamp * 1000).toLocaleTimeString()}
            </div>
        `;
    }
    
    updateContextPipeline(data) {
        const pipeline = document.getElementById('contextPipeline');
        if (!pipeline) return;
        
        // Create pipeline step visualization
        const stepElement = document.createElement('div');
        stepElement.className = `pipeline-step ${data.step}`;
        
        let stepIcon = '📋';
        let stepTitle = data.step;
        let stepDetails = '';
        
        if (data.step === 'memory_retrieval_complete') {
            stepIcon = '🔍';
            stepTitle = 'Memory Retrieval';
            stepDetails = `${data.data.memories_retrieved} memories found`;
        } else if (data.step === 'context_summarization_complete') {
            stepIcon = '📝';
            stepTitle = 'Context Summarization';
            stepDetails = `${data.data.summarization_method} → ${data.data.context_length} chars`;
        } else if (data.step === 'enhanced_prompt_created') {
            stepIcon = '🚀';
            stepTitle = 'Prompt Enhancement';
            stepDetails = `Role: ${data.data.original_role}`;
        }
        
        stepElement.innerHTML = `
            <div class="step-icon">${stepIcon}</div>
            <div class="step-content">
                <div class="step-title">${stepTitle}</div>
                <div class="step-details">${stepDetails}</div>
                <div class="step-timestamp">${new Date(data.timestamp * 1000).toLocaleTimeString()}</div>
            </div>
        `;
        
        pipeline.appendChild(stepElement);
        pipeline.scrollTop = pipeline.scrollHeight;
    }
    
    displayCoordinationStrategy(data) {
        const strategyDiv = document.getElementById('coordinationStrategy');
        if (!strategyDiv) return;
        
        const strategy = data.data.strategy;
        const reasoning = data.data.selection_reasoning || {};
        
        strategyDiv.innerHTML = `
            <div class="strategy-header">
                <h5>🎯 ${strategy.toUpperCase()} Strategy</h5>
                <span class="iteration-badge">Iteration ${data.data.iteration}</span>
            </div>
            <div class="strategy-details">
                <div class="strategy-algorithm">Algorithm: ${data.data.coordination_algorithm}</div>
                ${reasoning.required_skills ? `<div class="required-skills">Required Skills: ${reasoning.required_skills.join(', ')}</div>` : ''}
            </div>
        `;
    }
    
    displaySelectionReasoning(data) {
        const reasoningDiv = document.getElementById('selectionReasoning');
        if (!reasoningDiv) return;
        
        const reasoning = data.data.selection_reasoning || {};
        const allScores = reasoning.all_scores || {};
        
        let reasoningHTML = `
            <div class="reasoning-header">
                <span class="winning-agent">Winner: ${reasoning.winning_agent}</span>
                <span class="winning-score">Score: ${(reasoning.winning_score || 0).toFixed(3)}</span>
            </div>
        `;
        
        if (Object.keys(allScores).length > 0) {
            reasoningHTML += '<div class="all-scores">';
            for (const [agentId, scores] of Object.entries(allScores)) {
                const isWinner = agentId === reasoning.winning_agent;
                reasoningHTML += `
                    <div class="agent-score ${isWinner ? 'winner' : ''}">
                        <div class="agent-name">${agentId}</div>
                        <div class="score-breakdown">
                            <div class="score-item">Skill: ${(scores.skill_score || 0).toFixed(2)}</div>
                            <div class="score-item">Performance: ${(scores.performance_score || 0).toFixed(2)}</div>
                            <div class="score-item">Total: ${(scores.combined_score || 0).toFixed(3)}</div>
                        </div>
                        ${scores.matched_skills ? `<div class="matched-skills">Matched: ${scores.matched_skills.join(', ')}</div>` : ''}
                    </div>
                `;
            }
            reasoningHTML += '</div>';
        }
        
        reasoningDiv.innerHTML = reasoningHTML;
    }
    
    displaySkillMatching(data) {
        const skillDiv = document.getElementById('skillMatching');
        if (!skillDiv) return;
        
        const reasoning = data.data.selection_reasoning || {};
        const allScores = reasoning.all_scores || {};
        const requiredSkills = reasoning.required_skills || [];
        
        if (requiredSkills.length === 0) return;
        
        let skillHTML = `
            <div class="skill-requirements">
                <h6>Required Skills:</h6>
                ${requiredSkills.map(skill => `<span class="skill-tag required">${skill}</span>`).join('')}
            </div>
            <div class="skill-matches">
        `;
        
        for (const [agentId, scores] of Object.entries(allScores)) {
            const matchedSkills = scores.matched_skills || [];
            const matchPercentage = requiredSkills.length > 0 ? (matchedSkills.length / requiredSkills.length * 100) : 0;
            
            skillHTML += `
                <div class="agent-skills">
                    <div class="agent-name">${agentId}</div>
                    <div class="skill-match-bar">
                        <div class="match-fill" style="width: ${matchPercentage}%"></div>
                        <span class="match-percentage">${matchPercentage.toFixed(0)}%</span>
                    </div>
                    <div class="matched-skills">
                        ${matchedSkills.map(skill => `<span class="skill-tag matched">${skill}</span>`).join('')}
                    </div>
                </div>
            `;
        }
        
        skillHTML += '</div>';
        skillDiv.innerHTML = skillHTML;
    }
    
    updatePerformanceDashboard(data) {
        const dashboard = document.getElementById('performanceDashboard');
        if (!dashboard) return;
        
        const agentPerf = data.data.cumulative_performance;
        const agentName = data.agent_name;
        
        // Create or update agent performance card
        let agentCard = dashboard.querySelector(`[data-agent-perf="${data.agent_id}"]`);
        if (!agentCard) {
            agentCard = document.createElement('div');
            agentCard.className = 'performance-card';
            agentCard.setAttribute('data-agent-perf', data.agent_id);
            dashboard.appendChild(agentCard);
        }
        
        agentCard.innerHTML = `
            <div class="perf-card-header">
                <h6>${agentName}</h6>
                <span class="tasks-count">${agentPerf.total_tasks} tasks</span>
            </div>
            <div class="perf-metrics">
                <div class="metric">
                    <span class="metric-label">Success Rate</span>
                    <div class="metric-bar">
                        <div class="metric-fill success" style="width: ${agentPerf.success_rate * 100}%"></div>
                    </div>
                    <span class="metric-value">${(agentPerf.success_rate * 100).toFixed(0)}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Insights</span>
                    <div class="metric-bar">
                        <div class="metric-fill insights" style="width: ${Math.min(agentPerf.avg_insights_generated / 5 * 100, 100)}%"></div>
                    </div>
                    <span class="metric-value">${agentPerf.avg_insights_generated.toFixed(1)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Context Usage</span>
                    <div class="metric-bar">
                        <div class="metric-fill context" style="width: ${Math.min(agentPerf.avg_context_usage / 10 * 100, 100)}%"></div>
                    </div>
                    <span class="metric-value">${agentPerf.avg_context_usage.toFixed(1)}</span>
                </div>
            </div>
            <div class="perf-card-footer">
                Current Task: ${data.data.current_task_success ? '✅ Success' : '❌ Failed'}
            </div>
        `;
    }
    
    updatePerformanceTrends(data) {
        const trends = document.getElementById('performanceTrends');
        if (!trends || !this.performanceHistory) return;
        
        // Simple trend visualization showing latest 5 performance points per agent
        let trendsHTML = '<div class="trends-grid">';
        
        for (const [agentId, history] of Object.entries(this.performanceHistory)) {
            const recent = history.slice(-5); // Last 5 data points
            const trend = recent.length > 1 ? 
                (recent[recent.length - 1].performance.success_rate - recent[0].performance.success_rate > 0 ? '📈' : '📉') : '📊';
            
            trendsHTML += `
                <div class="trend-item">
                    <div class="trend-header">
                        <span class="agent-name">${agentId}</span>
                        <span class="trend-icon">${trend}</span>
                    </div>
                    <div class="trend-line">
                        ${recent.map((point, i) => {
                            const height = point.performance.success_rate * 40; // Max 40px height
                            return `<div class="trend-bar" style="height: ${height}px" title="Success: ${(point.performance.success_rate * 100).toFixed(0)}%"></div>`;
                        }).join('')}
                    </div>
                    <div class="trend-latest">Latest: ${(recent[recent.length - 1].performance.success_rate * 100).toFixed(0)}%</div>
                </div>
            `;
        }
        
        trendsHTML += '</div>';
        trends.innerHTML = trendsHTML;
    }
    
    formatProcessType(type) {
        const typeMap = {
            'agent_activation': '🤖 Agent Activation',
            'memory_state': '🧠 Memory State',
            'attention_filter': '🎯 Attention Filter',
            'context_building': '🔗 Context Building',
            'coordination_start': '⚡ Coordination Start',
            'coordination_decision': '🎯 Agent Selection',
            'performance_tracking': '📊 Performance Update',
            'collaboration_complete': '✅ Collaboration Complete',
            'insight_extraction': '💡 Insight Extraction',
            'a2a_execution': '🔄 A2A Execution',
            'collaboration_evolution': '🤝 Collaboration',
            'agent_response': '💬 Agent Response'
        };
        return typeMap[type] || type;
    }
    
    displayAttentionFilterDetails(data) {
        const attentionResults = document.getElementById('attentionResults');
        
        const filterItem = document.createElement('div');
        filterItem.className = 'attention-filter-item';
        
        const stats = data.data;
        const timestamp = new Date(data.timestamp * 1000).toLocaleTimeString();
        
        filterItem.innerHTML = `
            <div class="filter-header">
                <strong>${data.agent_name} - Attention Filter (Iteration ${stats.iteration + 1})</strong>
                <span class="filter-time">${timestamp}</span>
            </div>
            <div class="filter-criteria">
                ${(stats.filter_criteria || []).map(criteria => `<span class="filter-tag">${criteria}</span>`).join('')}
            </div>
            <div class="filter-results">
                <strong>Focus Areas:</strong><br>
                ${(stats.focus_areas || []).map(area => `• ${area}`).join('<br>') || 'No specific focus areas'}<br><br>
                <strong>Filtered Items:</strong> ${(stats.filtered_items || []).length}<br>
                ${stats.filtered_items && stats.filtered_items.length > 0 ? `
                    <div class="filtered-preview">
                        <strong>Sample Filtered Content:</strong>
                        <ul>
                            ${stats.filtered_items.slice(0, 2).map(item => 
                                `<li>${item.content || item.text || item}</li>`
                            ).join('')}
                            ${stats.filtered_items.length > 2 ? `<li><em>...and ${stats.filtered_items.length - 2} more</em></li>` : ''}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
        
        attentionResults.appendChild(filterItem);
        attentionResults.scrollTop = attentionResults.scrollHeight;
    }
    
    displayInsightExtractionDetails(data) {
        const insightsList = document.getElementById('insightsList');
        
        const insightItem = document.createElement('div');
        insightItem.className = 'insight-item';
        
        const stats = data.data;
        const timestamp = new Date(data.timestamp * 1000).toLocaleTimeString();
        
        insightItem.innerHTML = `
            <div class="insight-header">
                <span class="insight-type">${stats.extraction_method || 'LLM'} Extraction</span>
                <span class="insight-importance">Iteration ${stats.iteration + 1} - ${data.agent_name}</span>
            </div>
            <div class="insight-content">
                <strong>Insights Generated:</strong> ${stats.total_insights || 0}<br>
                <strong>High Importance:</strong> ${stats.high_importance_count || 0}<br>
                <strong>Time:</strong> ${timestamp}<br>
                ${stats.insights && stats.insights.length > 0 ? `
                    <div class="insights-preview">
                        <strong>Preview:</strong>
                        <ul>
                            ${stats.insights.slice(0, 3).map(insight => 
                                `<li>${insight.content || insight.text || 'Insight generated'}</li>`
                            ).join('')}
                            ${stats.insights.length > 3 ? `<li><em>...and ${stats.insights.length - 3} more</em></li>` : ''}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
        
        insightsList.appendChild(insightItem);
        insightsList.scrollTop = insightsList.scrollHeight;
    }
    
    displayA2AExecutionDetails(data) {
        // This could be shown in a dedicated A2A execution panel
        console.log('A2A Execution Details:', data.data);
    }
    
    addToCollaborationTimeline(data) {
        const timeline = document.getElementById('collaborationEvolution');
        
        const timelineItem = document.createElement('div');
        timelineItem.className = 'timeline-item';
        
        const evolutionData = data.data;
        const timestamp = new Date(data.timestamp * 1000).toLocaleTimeString();
        
        // Handle new iterative data structure
        if (data.step === 'collaboration_step') {
            timelineItem.innerHTML = `
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                    <strong>Iteration ${evolutionData.iteration + 1} - ${data.agent_name}</strong><br>
                    <span class="collaboration-style">Style: ${evolutionData.collaboration_style}</span><br>
                    Coordination Impact: ${((evolutionData.coordination_impact || 0) * 100).toFixed(0)}%<br>
                    <small class="timeline-time">${timestamp}</small>
                </div>
            `;
        }
        // Legacy format
        else {
            timelineItem.innerHTML = `
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                    <strong>${evolutionData.phase || 'Unknown Phase'}</strong><br>
                    Effectiveness: ${((evolutionData.collaboration_effectiveness || 0) * 100).toFixed(0)}%<br>
                    Knowledge: ${evolutionData.knowledge_growth?.total_knowledge_items || 0} items<br>
                    <small class="timeline-time">${timestamp}</small>
                </div>
            `;
        }
        
        timeline.appendChild(timelineItem);
        timeline.scrollTop = timeline.scrollHeight;
    }
    
    updateMemoryPoolVisualization() {
        const visualization = document.getElementById('memoryPoolState');
        visualization.innerHTML = '';
        
        if (Object.keys(this.memoryState.segments).length === 0) {
            visualization.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">No memory segments yet</div>';
            return;
        }
        
        Object.entries(this.memoryState.segments).forEach(([segment, count]) => {
            const segmentItem = document.createElement('div');
            segmentItem.style.cssText = `
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 5px 10px;
                margin-bottom: 5px;
                background: white;
                border-radius: 4px;
                font-size: 0.85rem;
            `;
            
            segmentItem.innerHTML = `
                <span>${segment}</span>
                <span style="font-weight: 600; color: #3b82f6;">${count}</span>
            `;
            
            visualization.appendChild(segmentItem);
        });
    }
    
    updateCollaborationState() {
        // Update phase
        const phaseValue = document.querySelector('.phase-value');
        if (phaseValue) {
            phaseValue.textContent = this.collaborationState.phase.replace(/_/g, ' ').toUpperCase();
        }
        
        // Update active agent in the collaboration state panel
        const activeAgentElement = document.querySelector('#activeAgentIndicator .agent-name');
        if (activeAgentElement) {
            activeAgentElement.textContent = this.collaborationState.activeAgent || 'None';
        }
        
        // Update progress
        document.getElementById('agentsCompleted').textContent = 
            `${this.collaborationState.agentsCompleted}/${this.collaborationState.totalAgents}`;
        document.getElementById('totalInsights').textContent = this.collaborationState.totalInsights;
    }
    
    bindEvents() {
        // Start button
        document.getElementById('startRealA2ABtn').addEventListener('click', () => {
            this.startRealA2ATask();
        });
        
        // Reset button
        document.getElementById('resetDemoBtn').addEventListener('click', () => {
            this.resetDemo();
        });
        
        // Enter key
        document.getElementById('queryInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.startRealA2ATask();
            }
        });
        
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
        
        // Select all checkbox
        document.getElementById('selectAll').addEventListener('change', (e) => {
            document.querySelectorAll('.agent-checkbox').forEach(checkbox => {
                checkbox.checked = e.target.checked;
            });
        });
    }
    
    async loadAgents() {
        try {
            const response = await fetch('/api/agents');
            const data = await response.json();
            this.agents = data.agents;
            console.log('Loaded agents from API:', this.agents.map(a => ({id: a.id, name: a.name})));
            this.collaborationState.totalAgents = this.agents.length;
            this.renderAgents();
            this.renderAgentCheckboxes();
        } catch (error) {
            console.error('Failed to load agents:', error);
        }
    }
    
    renderAgents() {
        const agentsList = document.getElementById('agentsList');
        agentsList.innerHTML = '';
        
        console.log('Rendering agents:', this.agents.map(a => ({id: a.id, name: a.name})));
        
        this.agents.forEach((agent, index) => {
            const agentCard = document.createElement('div');
            agentCard.className = 'agent-card';
            agentCard.dataset.agentId = agent.id;
            
            // Add agent name for debugging
            agentCard.dataset.agentName = agent.name;
            
            const capabilityTags = agent.capabilities.map(cap => 
                `<span class="capability-tag ${cap.level}">${cap.name}</span>`
            ).join('');
            
            agentCard.innerHTML = `
                <div class="agent-name" data-original-name="${agent.name}" data-index="${index}">${agent.name}</div>
                <div class="agent-type">${agent.type} (${agent.style})</div>
                <div class="agent-capabilities">
                    ${capabilityTags}
                </div>
                <div class="agent-description" style="font-size: 0.8rem; color: #666; margin-top: 5px;">
                    ${agent.description}
                </div>
            `;
            
            // Debug: Log what we're rendering
            console.log(`Agent ${index}: ${agent.name} (${agent.id})`);
            
            agentsList.appendChild(agentCard);
        });
    }
    
    renderAgentCheckboxes() {
        const container = document.getElementById('agentCheckboxes');
        container.innerHTML = '';
        
        this.agents.forEach(agent => {
            const label = document.createElement('label');
            label.innerHTML = `
                <input type="checkbox" class="agent-checkbox" value="${agent.id}" checked>
                ${agent.name} (${agent.type})
            `;
            container.appendChild(label);
        });
    }
    
    async startRealA2ATask() {
        const queryInput = document.getElementById('queryInput');
        const topic = queryInput.value.trim();
        
        if (!topic) {
            alert('Please enter a research topic');
            return;
        }
        
        const selectedAgents = Array.from(document.querySelectorAll('.agent-checkbox:checked'))
            .map(cb => cb.value);
        
        if (selectedAgents.length === 0) {
            alert('Please select at least one agent');
            return;
        }
        
        // Reset state
        this.collaborationState = {
            phase: 'starting',
            activeAgent: null,
            agentsCompleted: 0,
            totalAgents: selectedAgents.length,
            totalInsights: 0
        };
        
        // Clear previous data and show loading states
        this.internalProcesses = [];
        this.insights = [];
        this.showLoadingStates();
        
        // Reset agent states
        document.querySelectorAll('.agent-card').forEach(card => {
            card.classList.remove('active', 'processing', 'completed');
        });
        
        // Update UI state
        const startBtn = document.getElementById('startRealA2ABtn');
        startBtn.disabled = true;
        startBtn.textContent = '🔄 Real A2A System Processing...';
        
        try {
            const response = await fetch('/api/task/real-a2a', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    topic: topic,
                    agents_to_use: selectedAgents
                })
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            const result = await response.json();
            console.log('Real A2A Task Result:', result);
            
            // Check if the result indicates failure
            if (!result.success) {
                throw new Error(result.error || 'Task failed on backend');
            }
            
            // Process multi-agent results with comprehensive metrics
            this.processMultiAgentResults(result);
            
            // Update activity status with detailed metrics
            const status = document.getElementById('activityStatus');
            const totalCost = this.openaiUsage.totalCostUsd.toFixed(6);
            const totalTokens = this.openaiUsage.totalTokens;
            status.textContent = `✅ Real A2A: ${result.results.length} agents selected | ${totalTokens} tokens | $${totalCost} USD`;
            
        } catch (error) {
            console.error('Failed to execute real A2A task:', error);
            
            // Provide more specific error messages
            let errorMessage = 'Failed to start real A2A task';
            if (error.message.includes('HTTP 429')) {
                errorMessage = 'Rate limit exceeded. Please wait a few minutes before trying again.';
            } else if (error.message.includes('HTTP 401')) {
                errorMessage = 'API authentication failed. Please check your OpenAI API key.';
            } else if (error.message.includes('HTTP 500')) {
                errorMessage = 'Server error occurred. Please try again or reset the demo.';
            } else if (error.message.includes('Failed to fetch')) {
                errorMessage = 'Network error. Please check your connection and try again.';
            } else if (error.message) {
                errorMessage = `Error: ${error.message}`;
            }
            
            alert(errorMessage);
            
            // Update status to show error
            const status = document.getElementById('activityStatus');
            status.textContent = '❌ Task failed - see error message';
        } finally {
            startBtn.disabled = false;
            startBtn.textContent = 'Start Real A2A Research';
        }
    }
    
    processMultiAgentResults(result) {
        // Reset OpenAI usage tracking
        this.openaiUsage = {
            totalPromptTokens: 0,
            totalCompletionTokens: 0,
            totalTokens: 0,
            totalCostUsd: 0,
            agentBreakdown: {}
        };
        
        // DISPLAY AGENT RESULTS PROMINENTLY
        this.displayAgentResults(result);
        
        // Process each agent result
        result.results.forEach((agentResult, index) => {
            const agentData = agentResult.result;
            const agentName = agentResult.agent_name;
            const rank = agentResult.coordination_metadata?.rank || (index + 1);
            
            // Track OpenAI usage if available
            if (agentData.usage) {
                const usage = agentData.usage;
                this.openaiUsage.totalPromptTokens += usage.prompt_tokens || 0;
                this.openaiUsage.totalCompletionTokens += usage.completion_tokens || 0;
                this.openaiUsage.totalTokens += usage.total_tokens || 0;
                this.openaiUsage.totalCostUsd += usage.estimated_cost_usd || 0;
                
                // Store per-agent breakdown
                this.openaiUsage.agentBreakdown[agentResult.agent_id] = {
                    name: agentName,
                    rank: rank,
                    promptTokens: usage.prompt_tokens || 0,
                    completionTokens: usage.completion_tokens || 0,
                    totalTokens: usage.total_tokens || 0,
                    costUsd: usage.estimated_cost_usd || 0,
                    success: agentData.success || false,
                    insights: agentData.a2a_metadata?.insights_generated || 0,
                    sharedContext: agentData.a2a_metadata?.shared_context_used || 0
                };
            }
            
            // Update agent card with results
            this.updateAgentCardWithResults(agentResult.agent_id, agentData, rank);
        });
        
        // Update comprehensive metrics displays
        this.updateOpenAIMetricsDisplay();
        this.updateCoordinationMetricsDisplay(result);
        this.updateMemoryMetricsDisplay(result);
        
        // Update collaboration state
        this.collaborationState.agentsCompleted = result.results.length;
        this.collaborationState.totalInsights = result.results.reduce((sum, r) => 
            sum + (r.result.a2a_metadata?.insights_generated || 0), 0);
        this.updateCollaborationState();
    }
    
    updateAgentCardWithResults(agentId, agentData, rank) {
        const agentCard = document.querySelector(`[data-agent-id="${agentId}"]`);
        if (!agentCard) return;
        
        // Add success/rank indicators
        agentCard.classList.add(agentData.success ? 'completed' : 'failed');
        
        // Add rank badge
        const existingRank = agentCard.querySelector('.rank-badge');
        if (existingRank) existingRank.remove();
        
        if (agentData.success) {
            const rankBadge = document.createElement('div');
            rankBadge.className = 'rank-badge';
            rankBadge.textContent = `#${rank}`;
            agentCard.appendChild(rankBadge);
            
            // Add metrics display
            const existingMetrics = agentCard.querySelector('.agent-metrics');
            if (existingMetrics) existingMetrics.remove();
            
            const metricsDiv = document.createElement('div');
            metricsDiv.className = 'agent-metrics';
            metricsDiv.innerHTML = `
                <div class="metric-row">
                    <span>Tokens:</span> <span>${agentData.usage?.total_tokens || 0}</span>
                </div>
                <div class="metric-row">
                    <span>Cost:</span> <span>$${(agentData.usage?.estimated_cost_usd || 0).toFixed(6)}</span>
                </div>
                <div class="metric-row">
                    <span>Insights:</span> <span>${agentData.a2a_metadata?.insights_generated || 0}</span>
                </div>
                <div class="metric-row">
                    <span>Context:</span> <span>${agentData.a2a_metadata?.shared_context_used || 0}</span>
                </div>
            `;
            agentCard.appendChild(metricsDiv);
        }
    }
    
    updateOpenAIMetricsDisplay() {
        // Update OpenAI usage metrics panel
        document.getElementById('totalTokensUsed').textContent = this.openaiUsage.totalTokens.toLocaleString();
        document.getElementById('promptTokensUsed').textContent = this.openaiUsage.totalPromptTokens.toLocaleString();
        document.getElementById('completionTokensUsed').textContent = this.openaiUsage.totalCompletionTokens.toLocaleString();
        document.getElementById('totalCostUsd').textContent = `$${this.openaiUsage.totalCostUsd.toFixed(6)}`;
        
        // Update agent cost breakdown
        const agentCostList = document.getElementById('agentCostList');
        if (agentCostList) {
            let costBreakdownHTML = '';
            Object.entries(this.openaiUsage.agentBreakdown).forEach(([agentId, data]) => {
                costBreakdownHTML += `
                    <div class="agent-cost-item">
                        <span class="agent-name">${data.name}</span>
                        <span class="agent-cost">$${(data.costUsd || 0).toFixed(6)}</span>
                    </div>
                `;
            });
            agentCostList.innerHTML = costBreakdownHTML || '<div style="color: #999; text-align: center;">No costs yet</div>';
        }
        
        // Update real-time metrics
        const avgResponseTime = this.calculateAverageResponseTime();
        document.getElementById('avgResponseTime').textContent = `${avgResponseTime}ms`;
        document.getElementById('contextUsageRate').textContent = `${this.calculateContextUsageRate()}%`;
        
        // Force update memory growth rate if available
        if (Object.keys(this.openaiUsage.agentBreakdown).length > 0) {
            const totalMemoryOps = Object.values(this.openaiUsage.agentBreakdown).reduce((sum, agent) => 
                sum + (agent.sharedContext || 0), 0);
            document.getElementById('memoryGrowthRate').textContent = `${totalMemoryOps}/task`;
        }
        
        // Update performance tab with detailed breakdown
        this.updatePerformanceTabWithOpenAIDetails();
    }
    
    calculateAverageResponseTime() {
        // Calculate average response time from performance history
        if (!this.performanceHistory || Object.keys(this.performanceHistory).length === 0) {
            return 0;
        }
        
        let totalTime = 0;
        let count = 0;
        
        Object.values(this.performanceHistory).forEach(history => {
            history.forEach(entry => {
                if (entry.performance && entry.performance.response_time) {
                    totalTime += entry.performance.response_time;
                    count++;
                }
            });
        });
        
        return count > 0 ? Math.round(totalTime / count) : 0;
    }
    
    calculateContextUsageRate() {
        // Calculate percentage of agents using shared context
        const totalAgents = Object.keys(this.openaiUsage.agentBreakdown).length;
        if (totalAgents === 0) return 0;
        
        let contextUsers = 0;
        Object.values(this.openaiUsage.agentBreakdown).forEach(agent => {
            if ((agent.sharedContext || 0) > 0) contextUsers++;
        });
        
        return Math.round((contextUsers / totalAgents) * 100);
    }
    
    updatePerformanceTabWithOpenAIDetails() {
        const performanceDashboard = document.getElementById('performanceDashboard');
        if (!performanceDashboard) return;
        
        let dashboardHTML = '<h5>🔥 Real OpenAI Usage by Agent</h5>';
        
        Object.entries(this.openaiUsage.agentBreakdown).forEach(([agentId, data]) => {
            const efficiencyScore = data.totalTokens > 0 ? (data.insights / data.totalTokens * 1000).toFixed(2) : 0;
            
            dashboardHTML += `
                <div class="performance-card">
                    <div class="perf-card-header">
                        <h6>#${data.rank} ${data.name}</h6>
                        <span class="tasks-count">${data.success ? '✅' : '❌'}</span>
                    </div>
                    <div class="perf-metrics">
                        <div class="metric">
                            <span class="metric-label">Tokens:</span>
                            <span class="metric-value">${data.totalTokens}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Cost:</span>
                            <span class="metric-value">$${data.costUsd.toFixed(6)}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Insights:</span>
                            <span class="metric-value">${data.insights}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Context:</span>
                            <span class="metric-value">${data.sharedContext}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Efficiency:</span>
                            <span class="metric-value">${efficiencyScore}</span>
                        </div>
                    </div>
                    <div class="perf-card-footer">
                        ${data.promptTokens} prompt + ${data.completionTokens} completion tokens
                    </div>
                </div>
            `;
        });
        
        performanceDashboard.innerHTML = dashboardHTML;
    }
    
    updateCoordinationMetricsDisplay(result) {
        // Update coordination strategy info
        const strategy = result.collaboration_state?.coordination_strategy || 'best_match';
        const effectiveness = result.coordination_effectiveness || 0;
        
        document.getElementById('coordinationEffectiveness').textContent = `${(effectiveness * 100).toFixed(1)}%`;
        document.getElementById('agentsSelected').textContent = result.results.length;
        document.getElementById('agentsAvailable').textContent = this.agents.length;
        
        // Show agent selection reasoning in coordination tab
        const coordinationStrategy = document.getElementById('coordinationStrategy');
        if (coordinationStrategy && result.results.length > 0) {
            const firstResult = result.results[0];
            const reasoning = firstResult.coordination_metadata?.selection_reasoning;
            
            if (reasoning) {
                coordinationStrategy.innerHTML = `
                    <div class="strategy-details">
                        <h5>🎯 Agent Selection Strategy: ${reasoning.strategy}</h5>
                        <div class="strategy-algorithm">Top ${reasoning.top_k || 3} agents selected from ${this.agents.length} available</div>
                        <div class="selection-rationale">${reasoning.selection_rationale}</div>
                        <div class="required-skills">
                            <strong>Required Skills:</strong> ${reasoning.required_skills?.join(', ') || 'None specified'}
                        </div>
                    </div>
                    <div class="agent-scores">
                        <h6>🏆 Agent Scoring Results:</h6>
                        ${Object.entries(reasoning.all_scores || {}).map(([agentId, scores]) => {
                            const agent = this.agents.find(a => a.id === agentId);
                            const isSelected = result.results.some(r => r.agent_id === agentId);
                            return `
                                <div class="agent-score ${isSelected ? 'selected' : ''}">
                                    <div class="agent-name">${agent?.name || agentId} ${isSelected ? '✅ SELECTED' : '❌ NOT SELECTED'}</div>
                                    <div class="score-breakdown">
                                        <span>Combined: ${(scores.combined_score || 0).toFixed(2)}</span>
                                        <span>Skill: ${(scores.skill_score || 0).toFixed(2)}</span>
                                        <span>Performance: ${(scores.performance_score || 0).toFixed(2)}</span>
                                    </div>
                                    <div class="matched-skills">Skills: ${scores.matched_skills?.join(', ') || 'None matched'}</div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }
        }
    }
    
    updateMemoryMetricsDisplay(result) {
        // Update memory metrics based on final collaboration state
        const totalInsights = result.results.reduce((sum, r) => 
            sum + (r.result.a2a_metadata?.insights_generated || 0), 0);
        const totalMemories = result.results.reduce((sum, r) => 
            sum + (r.result.a2a_metadata?.local_memory_size || 0), 0);
        
        document.getElementById('totalMemoriesCount').textContent = totalMemories;
        document.getElementById('totalInsightsExtracted').textContent = totalInsights;
        document.getElementById('memoryGrowthRate').textContent = `${totalMemories}/task`;
    }
    
    displayAgentResults(result) {
        // Show the results section
        const resultsSection = document.getElementById('agentResultsSection');
        resultsSection.style.display = 'block';
        
        // Update summary stats
        const successfulAgents = result.results.filter(r => r.result.success).length;
        const totalInsights = result.results.reduce((sum, r) => 
            sum + (r.result.a2a_metadata?.insights_generated || 0), 0);
        
        // Calculate total cost from the actual results
        const totalCost = result.results.reduce((sum, r) => 
            sum + (r.result.usage?.estimated_cost_usd || 0), 0);
        
        document.getElementById('resultsTotalAgents').textContent = result.results.length;
        document.getElementById('resultsSuccessful').textContent = successfulAgents;
        document.getElementById('resultsTotalInsights').textContent = totalInsights;
        document.getElementById('resultsTotalCost').textContent = `$${totalCost.toFixed(4)}`;
        
        // Display individual agent results
        const container = document.getElementById('agentResultsContainer');
        container.innerHTML = '';
        
        result.results.forEach((agentResult, index) => {
            const resultCard = document.createElement('div');
            resultCard.className = `agent-result-card ${agentResult.result.success ? '' : 'failed'}`;
            
            // Extract the actual response content
            let responseContent = 'No response';
            if (agentResult.result.response) {
                responseContent = agentResult.result.response;
            }
            
            resultCard.innerHTML = `
                <div class="agent-result-header">
                    <div class="agent-result-name">${agentResult.agent_name}</div>
                    <div class="agent-result-status ${agentResult.result.success ? 'success' : 'failed'}">
                        ${agentResult.result.success ? '✅ Success' : '❌ Failed'}
                    </div>
                </div>
                
                <div class="agent-result-content">
                    <strong>Response:</strong><br>
                    ${this.formatAgentResponse(responseContent)}
                </div>
                
                <div class="agent-result-metrics">
                    <div class="agent-result-metric">
                        <span>Tokens Used</span>
                        <span>${agentResult.result.usage?.total_tokens || 0}</span>
                    </div>
                    <div class="agent-result-metric">
                        <span>Cost</span>
                        <span>$${(agentResult.result.usage?.estimated_cost_usd || 0).toFixed(6)}</span>
                    </div>
                    <div class="agent-result-metric">
                        <span>Insights</span>
                        <span>${agentResult.result.a2a_metadata?.insights_generated || 0}</span>
                    </div>
                    <div class="agent-result-metric">
                        <span>Context Used</span>
                        <span>${agentResult.result.a2a_metadata?.shared_context_used || 0}</span>
                    </div>
                </div>
            `;
            
            container.appendChild(resultCard);
        });
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    
    formatAgentResponse(response) {
        // Format the agent's response for display
        if (typeof response === 'string') {
            // Try to parse as JSON first
            try {
                const parsed = JSON.parse(response);
                return this.formatJsonResponse(parsed);
            } catch {
                // Not JSON, treat as plain text with markdown formatting
                return response
                    .replace(/\n/g, '<br>')
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/`(.*?)`/g, '<code>$1</code>');
            }
        } else if (typeof response === 'object') {
            return this.formatJsonResponse(response);
        }
        return String(response);
    }
    
    formatJsonResponse(jsonObj) {
        // Convert JSON response to readable format
        if (typeof jsonObj === 'string') {
            return jsonObj.replace(/\n/g, '<br>');
        }
        
        if (Array.isArray(jsonObj)) {
            return jsonObj.map(item => `• ${this.formatJsonResponse(item)}`).join('<br>');
        }
        
        if (typeof jsonObj === 'object' && jsonObj !== null) {
            // Handle common LLM response structures
            if (jsonObj.response || jsonObj.content || jsonObj.text) {
                const content = jsonObj.response || jsonObj.content || jsonObj.text;
                return this.formatAgentResponse(content);
            }
            
            // Handle research-style responses
            if (jsonObj.summary || jsonObj.analysis || jsonObj.findings) {
                let formatted = '';
                if (jsonObj.summary) formatted += `<strong>Summary:</strong><br>${jsonObj.summary}<br><br>`;
                if (jsonObj.analysis) formatted += `<strong>Analysis:</strong><br>${jsonObj.analysis}<br><br>`;
                if (jsonObj.findings) formatted += `<strong>Findings:</strong><br>${jsonObj.findings}<br><br>`;
                if (jsonObj.recommendations) formatted += `<strong>Recommendations:</strong><br>${jsonObj.recommendations}`;
                return formatted;
            }
            
            // Generic object formatting
            return Object.entries(jsonObj).map(([key, value]) => {
                const readableKey = this.getReadableVariableName(key);
                const formattedValue = this.formatJsonResponse(value);
                return `<strong>${readableKey}:</strong> ${formattedValue}`;
            }).join('<br>');
        }
        
        return String(jsonObj);
    }
    
    showLoadingStates() {
        // Show loading in all tabs
        const loadingHTML = `
            <div class="loading-state">
                <div class="loading-spinner"></div>
                <div class="loading-text">Processing real A2A internals...</div>
                <div class="loading-details">
                    • Executing real OpenAI calls<br>
                    • Extracting actual A2A metadata<br>
                    • Processing with real timing delays
                </div>
            </div>
        `;
        
        document.getElementById('internalProcessStream').innerHTML = loadingHTML;
        document.getElementById('insightsList').innerHTML = loadingHTML;
        document.getElementById('attentionResults').innerHTML = loadingHTML;
        
        // Show loading in new tabs
        const contextPipeline = document.getElementById('contextPipeline');
        if (contextPipeline) contextPipeline.innerHTML = loadingHTML;
        
        const coordinationStrategy = document.getElementById('coordinationStrategy');
        if (coordinationStrategy) coordinationStrategy.innerHTML = loadingHTML;
        
        const performanceDashboard = document.getElementById('performanceDashboard');
        if (performanceDashboard) performanceDashboard.innerHTML = loadingHTML;
        
        document.getElementById('collaborationEvolution').innerHTML = loadingHTML;
    }
    
    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
        
        // Update tab content
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        document.getElementById(`${tabName}Tab`).classList.add('active');
        
        // Load tab-specific data
        if (tabName === 'insights') {
            // Insights are updated in real-time
        } else if (tabName === 'attention') {
            // Attention data is updated in real-time
        } else if (tabName === 'context') {
            // Context building data is updated in real-time
        } else if (tabName === 'coordination') {
            // Coordination data is updated in real-time
        } else if (tabName === 'performance') {
            // Performance data is updated in real-time
        } else if (tabName === 'collaboration') {
            // Collaboration data is updated in real-time
        }
    }
    
    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        const statusDot = statusEl.querySelector('.status-dot');
        
        if (connected) {
            statusEl.innerHTML = '<span class="status-dot connected"></span> Connected to Real A2A System';
        } else {
            statusEl.innerHTML = '<span class="status-dot"></span> Disconnected from Real A2A System';
        }
    }
    
    startMetricsUpdate() {
        // Update metrics every few seconds
        setInterval(() => {
            this.updateMemoryAnalysis();
        }, 5000);
    }
    
    async updateMemoryAnalysis() {
        try {
            const response = await fetch('/api/memory/detailed');
            const data = await response.json();
            
            // Update memory distribution with better formatting
            const distribution = document.getElementById('memoryDistribution');
            if (data.stats.segment_sizes && Object.keys(data.stats.segment_sizes).length > 0) {
                const segments = Object.entries(data.stats.segment_sizes);
                const total = segments.reduce((sum, [, count]) => sum + count, 0);
                
                distribution.innerHTML = `
                    <div class="memory-analysis-header">
                        <h5>Memory Segments (${total} total)</h5>
                    </div>
                    <div class="memory-segments">
                        ${segments.map(([segment, count]) => {
                            const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
                            const readableSegment = this.getReadableVariableName(segment);
                            return `
                                <div class="segment-item">
                                    <div class="segment-info">
                                        <span class="segment-name">${readableSegment}</span>
                                        <span class="segment-count">${count} memories</span>
                                    </div>
                                    <div class="segment-bar">
                                        <div class="segment-fill" style="width: ${percentage}%"></div>
                                        <span class="segment-percentage">${percentage}%</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            } else {
                distribution.innerHTML = `
                    <div class="memory-analysis-empty">
                        <span>No memory segments yet</span>
                        <small>Memories will appear here as agents collaborate</small>
                    </div>
                `;
            }
            
            // Update importance distribution with better formatting
            const importance = document.getElementById('importanceDistribution');
            const levels = data.attention_indices?.importance_levels || {};
            const totalImportance = (levels.high || 0) + (levels.medium || 0) + (levels.low || 0);
            
            if (totalImportance > 0) {
                importance.innerHTML = `
                    <div class="importance-analysis-header">
                        <h5>Importance Levels (${totalImportance} total)</h5>
                    </div>
                    <div class="importance-levels">
                        ${[
                            { level: 'high', count: levels.high || 0, color: '#ef4444', label: 'High Priority' },
                            { level: 'medium', count: levels.medium || 0, color: '#f59e0b', label: 'Medium Priority' },
                            { level: 'low', count: levels.low || 0, color: '#6b7280', label: 'Low Priority' }
                        ].map(({ level, count, color, label }) => {
                            const percentage = Math.round((count / totalImportance) * 100);
                            return `
                                <div class="importance-item">
                                    <div class="importance-info">
                                        <span class="importance-label">${label}</span>
                                        <span class="importance-count">${count} items</span>
                                    </div>
                                    <div class="importance-bar">
                                        <div class="importance-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                                        <span class="importance-percentage">${percentage}%</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            } else {
                importance.innerHTML = `
                    <div class="importance-analysis-empty">
                        <span>No importance data yet</span>
                        <small>Importance levels will be calculated as memories are processed</small>
                    </div>
                `;
            }
            
        } catch (error) {
            console.error('Failed to update memory analysis:', error);
        }
    }
    
    async resetDemo() {
        // Confirm reset action
        if (!confirm('Are you sure you want to reset the demo? This will clear all memories and collaboration data.')) {
            return;
        }
        
        const resetBtn = document.getElementById('resetDemoBtn');
        const originalText = resetBtn.textContent;
        
        try {
            // Disable button and show loading
            resetBtn.disabled = true;
            resetBtn.textContent = '🔄 Resetting...';
            
            // Call reset API
            const response = await fetch('/api/reset', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Clear local state
                this.clearLocalState();
                
                // Show success feedback
                resetBtn.textContent = '✅ Reset Complete';
                setTimeout(() => {
                    resetBtn.textContent = originalText;
                    resetBtn.disabled = false;
                }, 2000);
                
                console.log('✅ Demo reset successfully');
            } else {
                throw new Error(result.error || 'Reset failed');
            }
            
        } catch (error) {
            console.error('Reset failed:', error);
            resetBtn.textContent = '❌ Reset Failed';
            setTimeout(() => {
                resetBtn.textContent = originalText;
                resetBtn.disabled = false;
            }, 3000);
        }
    }
    
    clearLocalState() {
        // Clear all data displays
        this.internalProcesses = [];
        this.collaborationState = {
            activeTask: null,
            phase: 'idle',
            agentsCompleted: 0,
            totalAgents: 0,
            totalInsights: 0
        };
        
        // Reset OpenAI usage tracking
        this.openaiUsage = {
            totalPromptTokens: 0,
            totalCompletionTokens: 0,
            totalTokens: 0,
            totalCostUsd: 0,
            agentBreakdown: {}
        };
        
        // Clear UI displays
        document.getElementById('internalProcessStream').innerHTML = `
            <div class="welcome-message">
                <h4>🔬 Real A2A System Ready</h4>
                <p>This shows the <strong>actual internal workings</strong> of the A2A system:</p>
                <ul>
                    <li><strong>Memory Operations:</strong> Real read/write to SharedMemoryPoolNode</li>
                    <li><strong>Insight Extraction:</strong> LLM-powered insight classification</li>
                    <li><strong>Attention Filtering:</strong> How agents focus on relevant information</li>
                    <li><strong>Context Building:</strong> How shared knowledge influences responses</li>
                    <li><strong>Collaboration Evolution:</strong> Effectiveness metrics over time</li>
                </ul>
                <p><strong>Enter a research topic to see the real A2A system work!</strong></p>
            </div>
        `;
        
        // Clear other tabs content
        document.getElementById('insightsList').innerHTML = '';
        document.getElementById('attentionResults').innerHTML = '';
        document.getElementById('contextPipeline').innerHTML = '';
        document.getElementById('contextPreview').innerHTML = '';
        document.getElementById('selectionReasoning').innerHTML = '';
        document.getElementById('skillMatching').innerHTML = '';
        document.getElementById('performanceDashboard').innerHTML = '';
        document.getElementById('collaborationEvolution').innerHTML = '';
        
        // Reset memory metrics
        document.getElementById('totalMemoriesCount').textContent = '0';
        document.getElementById('activeSegmentsCount').textContent = '0';
        document.getElementById('knowledgeGrowth').textContent = '0%';
        
        // Reset OpenAI metrics
        document.getElementById('totalTokensUsed').textContent = '0';
        document.getElementById('promptTokensUsed').textContent = '0';
        document.getElementById('completionTokensUsed').textContent = '0';
        document.getElementById('totalCostUsd').textContent = '$0.00';
        document.getElementById('agentCostList').innerHTML = '';
        
        // Reset collaboration state
        document.getElementById('agentsCompleted').textContent = '0/0';
        document.getElementById('totalInsights').textContent = '0';
        const scoreElement = document.getElementById('collaborationScore');
        const effElement = document.getElementById('collaborationEffectiveness');
        if (scoreElement) {
            scoreElement.textContent = '0%';
        }
        if (effElement) {
            effElement.style.width = '0%';
        }
        
        // Reset agent cards - remove ALL possible classes and elements
        document.querySelectorAll('.agent-card').forEach(card => {
            // Remove all possible CSS classes that can be applied to agent cards
            card.className = 'agent-card'; // Reset to only the base class
            
            // Remove all dynamic elements that may have been added
            const elementsToRemove = [
                '.rank-badge',
                '.agent-metrics', 
                '.coordination-info',
                '.performance-indicator',
                '.processing-indicator',
                '.metric-row'
            ];
            
            elementsToRemove.forEach(selector => {
                const elements = card.querySelectorAll(selector);
                elements.forEach(el => el.remove());
            });
            
            // Reset any inline styles that might have been applied
            card.style.cssText = '';
            
            // Ensure the card returns to its original state
            card.style.transform = '';
            card.style.boxShadow = '';
            card.style.background = '';
            card.style.border = '';
        });
        
        // Clear memory analysis panels
        document.getElementById('memoryDistribution').innerHTML = `
            <div class="memory-analysis-header">
                <h5>📊 Memory Segments</h5>
            </div>
            <div class="memory-analysis-empty">
                🗂️ No memory segments yet
                <small>Memory segments will appear when agents start collaborating</small>
            </div>
        `;
        
        document.getElementById('importanceDistribution').innerHTML = `
            <div class="importance-analysis-header">
                <h5>🎯 Importance Levels</h5>
            </div>
            <div class="importance-analysis-empty">
                📈 No importance data yet
                <small>Insight importance distribution will appear during collaboration</small>
            </div>
        `;
        
        // Reset memory pool state visualization
        document.getElementById('memoryPoolState').innerHTML = '';
        
        // Reset real-time metrics
        document.getElementById('avgResponseTime').textContent = '0ms';
        document.getElementById('contextUsageRate').textContent = '0%';
        document.getElementById('memoryGrowthRate').textContent = '0/min';
        
        // Hide agent results section
        document.getElementById('agentResultsSection').style.display = 'none';
        
        // Reset status
        document.getElementById('activityStatus').textContent = 'Ready';
        
        console.log('🧹 Local state cleared');
    }
    
    handleSystemReset(data) {
        console.log('🔄 System reset notification received:', data.message);
        
        // Clear all local state first (this includes agent cards reset)
        this.clearLocalState();
        
        // Update UI to show reset
        const status = document.getElementById('activityStatus');
        status.textContent = 'Demo reset to clean slate';
        
        // Force update memory analysis to show empty state
        this.updateMemoryAnalysis();
        
        // Show notification in process stream
        const stream = document.getElementById('internalProcessStream');
        const resetItem = document.createElement('div');
        resetItem.className = 'process-item system_reset';
        resetItem.innerHTML = `
            <div class="process-header">
                <span class="process-title">System Reset</span>
                <span class="process-step">${new Date(data.timestamp * 1000).toLocaleTimeString()}</span>
            </div>
            <div class="process-data">
                <div class="data-item">
                    <strong>Status:</strong> Demo reset to clean slate<br>
                    <span class="var-description">All memories and collaboration data cleared</span>
                </div>
            </div>
        `;
        
        // Add reset styling
        resetItem.style.background = 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)';
        resetItem.style.borderLeftColor = '#ef4444';
        
        stream.appendChild(resetItem);
        stream.scrollTop = stream.scrollHeight;
    }
}

// Initialize the real A2A demo when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new RealA2ADemo();
});