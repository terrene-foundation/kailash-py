# CONNECTION: Per-Node Governance (#234) Spans kailash-pact + kailash-kaizen

The GovernedSupervisor lives in `packages/kailash-kaizen/`, not `packages/kailash-pact/`. Per-node governance requires:

1. GovernanceCallback protocol defined in kailash-pact
2. GovernedSupervisor.run() in kailash-kaizen to accept execute_node callback
3. Cross-package integration tests
4. Version compatibility between the two packages

This is the highest-risk change in the plan — cross-package coordination with independent release cycles.
