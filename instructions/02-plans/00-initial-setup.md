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
1. Referencing your plans in docs/02-plans
   - make any necessary revisions to the organization of the codebase.
     - All backend codes should be in src/...
     - All web (react) codes should be in apps/web
     - All mobile (flutter) codes should be in apps/mobile
   - Please consider where should the gateway (nexus) codebase be located.
2. (backend) Work with the subagents in .claude/agents
   - especially the framework specialists: kailash, kaizen, dataflow, nexus
   - follow our procedural directives
   - review and revise the plans as required
3. (frontend) Work with the subagents in .claude/agents/frontend
   - review your implementation plans and todos for the frontends.
   - use a consistent set of design principles for all our FE interfaces.
   - use the latest modern UI/UX principles/components/widgets in your implementation.
4. Work with todo-manager, following our procedural directives
   - create detailed todos for EVERY todo/task required.
   - The detailed todos should be created in todos/active.
   - Review after you are done to ensure that you leave no gaps behind.
5. Do not continue until I have approved your todos.
