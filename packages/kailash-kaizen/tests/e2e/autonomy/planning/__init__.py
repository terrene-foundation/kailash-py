"""
Tier 3 E2E Tests: Planning Agents

Test suite for planning agents with real LLM infrastructure:
- PlanningAgent: Multi-step plan creation and execution
- PEVAgent: Plan-Execute-Verify-Refine cycle
- ToTAgent: Tree-of-Thoughts exploration

Tests validate:
- Real Ollama LLM inference (llama3.1:8b-instruct-q8_0 - FREE)
- Real OpenAI validation (gpt-4o-mini - PAID)
- Plan generation, execution, and adaptation
- Iterative refinement and quality improvement
- Multiple path exploration and selection

Requirements:
- Ollama running locally with llama3.1:8b-instruct-q8_0 model
- OpenAI API key for quality validation
- No mocking (real infrastructure only)

Test Files:
1. test_planning_agent_e2e.py - 3 tests (Tests 13-15)
2. test_pev_agent_e2e.py - 1 test (Test 16)
3. test_tot_agent_e2e.py - 1 test (Test 17)

Total Budget: $0.10 (OpenAI validation only)
Total Duration: ~3-6 minutes
"""
