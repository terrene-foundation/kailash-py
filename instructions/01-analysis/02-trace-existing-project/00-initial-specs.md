# These instructions are for the purpose of tracing an existing project with product focus

## Always be explicit about objectives and expectations
### Creating a knowledge base that can be further distilled for use by agents and skills
1. I want to create a set of agents and skills that can reference distilled knowledge of this repository.
   - for the purpose of:
     - Resolving bugs
     - creating new features
     - Repivoting features
     - and performing other development lifecycle activities...
       - I want you to check against our docs, tests, even git commits to see what activities are prone to repeat.
       - Then research widely and analyze what such activities are required in development lifecycles for a project of this nature.
2. This is a solution for ... and we envision it to be a product with the following soft rule:
     - 80% of the codebase/features/efforts can be reused (agnostic)
     - 15% of the client specific requirements goes into consideration for self-service functionalities that can be reused (agnostic)
     - 5% customization
3. Assume that the current project has documentations and comments that could have been misaligned and missing
   - Analyze thoroughly with subagents and skills, then peruse the codebase, docs, and tests
     - Analyze and achieve a 100% trace on the current state
       - Ensure that you review with independent subagents and ensure that there are no gaps.
       - Document your analysis, in details, to the extent that any developer can read it and achieve 100% situational awareness
         - Use as many subdirectories and files as required, and name them 01-, 02-, etc., for easy referencing.
         - Ensure that each subdirectory has a README.md that serves as the first landing point for navigation purpose.
   - If there are un-numbered directories or files in docs/, peruse and analyze them carefully against your analysis
     - move and organized them into docs/00-developers
       - ensuring that missing gaps are created with detailed documentation
       - obsolete information is removed
       - repeated information are consolidated
     - ensure that you validate every claim with evidence (from codebase and tests) using subagents
4. If there are issues and comments logged in jira/github:
   - Access them using mcp (check docs/codebase for existing implementations)
   - Analyze and categorize all these issues
      - CRITICALLY, you MUST read the intent behind the issues/feedback/comments
        - DO NOT treat issues and comments as naive technical problems that requires patching
        - ALWAYS ensure that you have a 'user story' that specifically states the intent, objective, and deliverable/KPI.
          - Always assume that comments are vague and can be interpreted in different ways
            - thus, perform deep analysis and identify the root causes
        - Exercise your expertise.
   - Rationalize them and create a system of knowledge base and procedures that would help developers
     - analyze the issues comprehensively
     - compare requirements against our codebase
     - deep dive into root causes for the purpose of creating optimal, elegant, and parsimonious fixes
     - follow our soft rule above
     - create well-intentioned and well-thought replies to any queries, issues, or comments

### Create project specific agents and skills
1. Using as many subagents as required, peruse docs/00-developers
   - Think deeply and read beyond the docs into the intent of this project/product
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

### Converting/Upgrading the project into one with product focus
1. Keep this soft rule in mind for everything you do in this section
   - 80% of the codebase/features/efforts can be reused (agnostic)
   - 15% of the client specific requirements goes into consideration for self-service functionalities that can be reused (agnostic)
   - 5% customization
2. Research thoroughly and distill the value propositions and UNIQUE SELLING POINTS of our solution
   - Scrutinize and critique the intent and vision of this solution, with the focus of creating a product with perfect product market fit
   - Research widely on competing products, gaps, painpoints, and any other information that can help us build a solid base of value propositions
   - It is critical to define the unique selling points. Do not confuse value proposition with unique selling points.
     - Be extremely critical and scrutinize your unique selling points.
3. Evaluate it using platform model thinking
   - Seamless direct transactions between users (producers, consumers, partners)
     - Producers: Users who offer/deliver a product or service
     - Consumers: Users who consume a product or service
     - Partners: To facilitate the transaction between producers and consumers
4. Evaluate it using the AAA framework
   - Automate: Reduce operational costs
   - Augment: Reduce decision-making costs
   - Amplify: Reduce expertise costs (for scaling)
5. Features must sufficiently cover the following network behaviors to achieve strong network effects
   - Accessibility: Easy for users to complete a transaction
     - transaction is activity between producer and consumer, not necessarily monetary in nature)
   - Engagement: Information that are useful to users for completing a transaction
   - Personalization: Information that are curated for an intended use
   - Connection: Information sources that are connected to the platform (one or two-way)
   - Collaboration: Producers and consumers can jointly work together seamlessly
6. Do not re-invent, extend.
   - unless the existing codebase cannot support the value propositions.
     - Priority: USP > VP > Features > codebase
7. Document in details, your analysis in docs/01-analysis, and plans in docs/02-plans, and user flows in docs/03-user-flows.
   - Use as many subdirectories and files as required
   - Name them sequentially as 01-, 02-, etc, for easy referencing
