"""
Load tests for Kaizen AI Framework.

Tests system behavior under high load with real infrastructure:
- 1000+ conversation turns per session
- 100+ concurrent agents
- 10,000+ hooks triggered per hour
- Memory tier overflow handling
- Resource limit enforcement under load
- Sustained load (1 hour+) - optional with @pytest.mark.slow
"""
