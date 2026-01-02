# Adding new features/Resolving new issues
1. Discuss the following new features/issues:
   -
2. Please work with subagents and document the plans into 02-plans, following our sequential numbering convention.
3. You MUST always use the todo-manager to create the detailed todos FOR EVERY SINGLE TODO in 000-master.md
   - Review with subagents, before implementation.
4. Continue with the implementation of the next todo/phase using our subagents, following our procedural directives.
5. At the end of each phase, work with the todo-manager and update the detailed todos in todos/active.
   - Ensure that every task is verified with evidence before you close them, then move completed ones to completed/.
   - Ensure that you test comprehensively as you implement, with all tests passing at 100%
     - No tests can be skipped (make sure docker is up and running).
     - Do not rewrite the tests just to get them passing but ensure that it's not infrastructure issues that is causing the errors.
     - Always tests according to the intent of what we are trying to achieve and against users' expectations
       - Do not write simple naive technical assertions.
       - Do not have stubs, hardcodes, simulations, naive fallbacks without informative logs.
6. When writing agents, always remember to utilize the LLM's capabilities instead of naive NLP approaches such as keywords, regex etc.
7. At the end of each phase, write your docs into src/.../docs/developers
   - using as many subdirectories and files as required, and naming them sequentially 00-, 01- for easy referencing.
   - Your docs must focus on capturing the essence and intent, the 'what it is' and 'how to use it', and not status/progress/reports and other irrelevant information.

# Example of multi-apps
1. We need to have the following features and resolve these bugs:
   1. Fix roles editing
   2. Fix teams member management
   3. each SSO user from the same domain must be in the same organization by domain.
      - Given that the first enterprise SSO user login has to be an admin to grant permission
      - it makes sense that subsequent enterprise SSO users login via the same domain should be in the same organization.
   4. based on modern ui/ux approaches, recommend the best way for a user to
      - create an organization during registration, and then
      - allow other users to create an account to this organization
        - with some form of authorization/authentication via the invitation system.
   5. Users should be allowed to belong to multiple tenants please
      - we thus need a super-admin role that can manage multiple tenants
        - and admin role to manage within tenant.
        - This is the current practice for most enterprise SaaS.

2. Please work with subagents, ultrathink, and
   - document the plans into
     - apps/kailash-kaizen/docs/plans (if work needs to be done at the kaizen level), and
     - apps/kaizen-studio/docs/plans,
     - following our sequential numbering convention.
3. Work with todo-manager, following our procedural directives, and create the detailed todos in
   - apps/kailash-kaizen/todos/active (for kaizen) and
   - apps/kaizen-studio/todos/active (for the studio)
   - ensuring that every task in their respective 000-master.md have a corresponding detailed active todo.
4. Then continue with the implementations using our subagents, following our procedural directives.
5. At the end of every phase
   - work with the todo-manager and update
     - the detailed todos in apps/kailash-kaizen/todos/active (for kaizen) and
     - apps/kaizen-studio/todos/active (for the studio UI)
     - Ensure every task is verified with evidence before you close them
       - then move completed todos to completed/.
   - Ensure that you test comprehensively as you implement
     - with all tests passing at the end of each phase.
     - Always write your tests based on the intent of what we are trying to achieve and not just naive technical assertions.
   - Write your docs in the respective apps accordingly, using as many files as required
     - capture the essence and intent, the what it is, and how to use it
     - and not status/progress/reports and other irrelevant information.
   - Also update the following docs accordingly if required
     - .claude/agents/frameworks/kaizen-specialist.md
     - .claude/skills/04-kaizen
     - sdk-users/apps/kaizen
