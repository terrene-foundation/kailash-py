# Setup (If using parallel worktrees)
1. Use 3 parallel processes (worktrees created from main branch)
   - Backend worktree (sync to backend branch)
   - Web worktree - React (sync to web branch)
   - App worktree - Flutter for iOS and Android (sync to the app branch)
2. Branch setup
   - Staging branch
   - Production branch (protected)
3. Review and update/create detailed implementation and integration plans

## From plans to todos
1. Referencing your plans in instructions/.../02-plans/
   - (backend) Work with the subagents in .claude/agents
      - especially the framework specialists: kailash, kaizen, dataflow, nexus
      - follow our procedural directives
      - review and revise the plans as required
2. Work with todo-manager, following our procedural directives
   - create detailed todos for EVERY todo/task required.
   - The detailed todos should be created in todos/active.
     - for kailash sdk: project root
     - for dataflow: apps/kailash-dataflow
     - for kaizen: apps/kailash-kaizen
     - for nexus: apps/kailash-nexus
   - Review after you are done to ensure that you leave no gaps behind.
3. Do not continue until I have approved your todos.
