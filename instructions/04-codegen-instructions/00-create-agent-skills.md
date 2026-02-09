### Create project specific agents and skills
1. Using as many subagents as required, peruse docs/00-developers
   - Ultrathink and read beyond the docs into the intent of this project/product
   - Understand the roles and use of agents, skills, docs
     - Agents - What to do, how to think about this, what can it work with, following the procedural directives
     - Skills - Distilled knowledge that agents can achieve 100% situational aware with
     - docs (specifically 00-developers) - Full knowledge base
2. Create/Update agents in .claude/agents/project
   - please web research how Claude subagents should be written, what the best practices are, and how they should be used.
   - specialized agents whose combined expertise cover 100% of this codebase/project/product
   - use-case agents that can work across skills and guide the main agent in coordinating work that are best done by specialized agents.
3. Create the accompanying skills in .claude/skills/project
   - please web research how Claude skills should be written, what the best practices are, and how they should be used.
   - do not create any more subdirectories
   - ensure single entry point for skills (SKILL.md) that references multiple skills files in the same directory
     - skills must be as detailed as possible to the extent that the agents can deliver most of their work just by using them
     - do not treat skills as the knowledge base
       - it's supposed to contain the most critical information and logical links/frameworks between the information in the knowledge base
       - should REFERENCE instead of repeating the knowledge base (docs/00-developers)
