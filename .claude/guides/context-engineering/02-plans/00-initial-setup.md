# Setup
1. Use 3 parallel processes (worktrees created from main branch)
   - Backend worktree (sync to backend branch)
   - Web worktree - React (sync to web branch)
   - App worktree - Flutter for iOS and Android (sync to the app branch)
2. Branch setup
   - Staging branch
   - Production branch (protected)

# Tasks
1. Review and update/create detailed implementation and integration plans given the 3 parallel processes/worktrees

## From plans to todos
1. Referencing your plans in docs/02-plans
   - make any necessary revisions to the organization of the codebase.
   - ALl backend codes should be in src/...
   - All web (react) codes should be in apps/web
   - All mobile (flutter) codes should be in apps/mobile
   - Please consider where should the gateway (nexus) codebase be located.
2. Work with subagents (especially the framework specialists: kailash, kaizen, dataflow, nexus), following our procedural directives, and revise the plans accordingly.
3. After that, work with todo-manager, following our procedural directives, and create detailed todos for EVERY todo/task required.
   - The detailed todos should be created in todos/active.
   - Review after you are done to ensure that you leave no gaps behind.
4. Please use the subagents in .claude/agents/frontend to review your implementation plans and todos for the frontends.
   - Ensure that you are using a consistent set of design principles for all our FE interfaces.
   - Ensure that you are using the latest modern UI/UX principles/components/widgets in your implementation.
5. Do not continue until I have approved your todos.
