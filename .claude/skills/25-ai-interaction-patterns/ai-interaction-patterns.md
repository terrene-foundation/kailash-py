# AI Interaction Patterns Reference

Complete reference for AI-specific UX patterns. Based on [Shape of AI](https://www.shapeof.ai) (CC-BY-NC-SA) by Emily Campbell, extended with implementation guidance for Kailash SDK applications.

---

## 1. WAYFINDERS

_Help users construct their first prompt and get started._

The blank-canvas problem is the single biggest barrier to AI adoption. Users who don't know what to ask won't return. Wayfinders solve this by making the first interaction frictionless.

### Gallery

**Definition**: Collections of example generations that show what's possible, spark ideas, and make example-based creation frictionless.

**Variations**:

- **Curated Gallery**: Hand-selected by the platform team for quality and capability demonstration
- **Community Gallery**: User-submitted with voting, trending, and remix features
- **Dynamic Gallery**: Algorithmically surfaced based on trends, user profiles, or activity

**Design Guidance**:

- Provide clear previews (thumbnails, snippets) for quick scanning
- Organize with categories, tags, and filters to prevent cognitive overload
- Make examples actionable: one-click remix with visible prompt and parameters
- Balance polished curated work with authentic user-created examples
- Expose metadata (prompts, models, styles) for reverse-engineering understanding
- Rotate content regularly; retire outdated items

**When to Use**: Onboarding, inspiration phase, capability discovery, marketing.

**Related Patterns**: Initial CTA, Templates, Prompt Details, Suggestions, Preset Styles.

---

### Suggestions

**Definition**: Lists of 3-5 prompt options that help users understand capabilities and maintain conversation momentum.

**Three Forms**:

- **Static**: Fixed prompts for onboarding, varying by mode but not personalized
- **Contextual**: Dynamically shift based on current page, document, or content being viewed
- **Adaptive**: Evolve from individual behavior and system learning over time

**Design Guidance**:

- Clicking a suggestion MUST run the prompt (either as editable starting point or direct execution)
- Leverage context: update suggestions when modes, attachments, or content change
- Display 3-6 options ordered by relevance; excessive options cause scanning fatigue
- Use suggestions to model good prompts during onboarding
- Avoid displaying everywhere; focus on moments users need guidance
- Confirm or preview suggestions that trigger data access or heavy computation

**When to Use**: Cold start, after mode changes, idle periods, onboarding.

**Related Patterns**: Inline Action, Follow-up.

---

### Templates

**Definition**: Structured prompt scaffolds for common or complex tasks, reducing the cognitive load of prompt engineering.

**Design Guidance**:

- Organize by use case (not by AI capability)
- Show preview of expected output before user commits
- Allow customization of template parameters
- Track which templates are used most to improve curation

**When to Use**: Recurring tasks, complex prompts, enterprise workflows.

---

### Follow-ups

**Definition**: Prompts, questions, or inline actions that help users refine or extend their initial interaction.

**Five Forms**:

1. **Conversation extenders**: Suggest additional topics after completing prior actions
2. **Clarifying questions**: Address missing information or ambiguity
3. **Depth probes**: Offer drilling into specific aspects
4. **Comparisons**: Present pros/cons, alternatives, or benchmarks
5. **Action nudges**: Transform results into actionable next steps

**Design Guidance**:

- Ground suggestions in context; base follow-ups on the AI's last response, not generic options
- Explain the connection: make users understand why this follow-up is relevant
- Maintain scannability: offer high-value, limited-choice follow-ups
- Mix exploration directions: balance "zoom in" refinements with "zoom out" pivots
- Visually separate follow-ups from the main output
- Allow users to regenerate follow-up options

**When to Use**: After every AI response (nearly universal pattern).

**Related Patterns**: Sample Response, Memory, Action Plan.

---

### Initial CTA

**Definition**: The entry-point design that reduces first-interaction friction and sets expectations.

**Design Guidance**: Position galleries, suggestions, or templates at the primary entry point. Avoid an empty text box with no guidance.

---

### Nudges

**Definition**: Proactive guidance that helps users write better prompts without requiring expertise.

**Design Guidance**: Show nudges contextually (e.g., "Try being more specific about the time period") rather than as generic tips. Offer one nudge at a time to avoid overwhelm.

---

### Prompt Details

**Definition**: Expose the parameters and prompts behind generated content for educational transparency.

**Design Guidance**: Show full prompts, model used, parameter settings. Enable one-click copying of prompts for reuse.

---

### Randomize

**Definition**: Serendipity-driven exploration that introduces unexpected but productive variation.

**Design Guidance**: Offer as a secondary action ("Surprise me") alongside more directed options. Show what parameters were randomized so users can learn.

---

## 2. PROMPT ACTIONS

_Different actions users can direct AI to complete._

### Open Input

**Definition**: The foundational interaction model enabling natural language dialogue. A simple, familiar interface that lowers the barrier to initial engagement.

**Four Contexts**:

1. **Chat box**: Persistent bottom input for conversational back-and-forth
2. **Inline composer**: Operates on text selections within editors
3. **Command-style prompt**: Single-line input with structured flags/controls
4. **Side panel composer**: Panel-based input supporting files, tools, and settings

**Design Guidance**:

- Set a clear default scope and make scope switching a single-step action
- Provide constructive error handling: specify what's missing and suggest solutions
- Don't assume prompt expertise; provide templates, examples, and guidance
- Maintain parameter and model selection options throughout the workflow

**When to Use**: Universal; every AI product needs at least one open input pattern.

**Related Patterns**: Controls, Inline Action, Parameters.

---

### Inline Action

**Definition**: Targeted edits within existing content, operating on selections rather than full documents.

**Design Guidance**: Keep scope tight; user should understand exactly what will be modified. Show before/after preview when possible.

---

### Chained Action

**Definition**: Multi-step sequential tasks where each action feeds into the next.

**Design Guidance**: Show the chain visually (step 1 → step 2 → step 3). Allow editing intermediate results before proceeding.

---

### Regenerate

**Definition**: Re-run a prompt with potential parameter variations to get different output.

**Design Guidance**: Never overwrite the original; show regenerated work as new versions. Allow parameter adjustment between regenerations.

---

### Transform / Restyle / Expand / Summary / Synthesis / Restructure

**Content modification action family**:

- **Transform**: Change format/structure (table → bullet list, JSON → YAML)
- **Restyle**: Change tone/style while preserving content
- **Expand**: Elaborate with more detail
- **Summary**: Condense to key points
- **Synthesis**: Combine multiple sources into unified output
- **Restructure**: Reorganize without changing content

**Design Guidance**: Make the action verb explicit in the UI. Show before/after or diff when possible.

---

### Describe

**Definition**: Generate text/data from visual or audio input (image → text, audio → transcript).

---

### Auto-fill

**Definition**: AI-populated form fields based on context or prior data.

**Design Guidance**: Always show what was auto-filled with option to edit. Mark auto-filled fields visually.

---

### Madlibs

**Definition**: Guided prompt construction through structured fill-in-the-blank templates.

**Design Guidance**: Use when prompts have a known structure. Keep blanks to 3-5 fields maximum.

---

### Inpainting

**Definition**: Selective region-based editing for visual content.

---

## 3. TUNERS

_Adjust contextual data, token weights, and input details to refine the prompt._

### Attachments

**Definition**: File upload and document context management for AI reference.

**Design Guidance**:

- Show processing status (uploaded → indexing → ready)
- Display which attachments are actively in context
- Allow selective activation/deactivation of documents
- Warn when approaching context window limits
- Show relevance scores per document

---

### Connectors

**Definition**: Integration with external data sources (databases, APIs, knowledge bases).

**Design Guidance**: Show connection status (active/inactive/error). Allow source-specific permission controls.

---

### Model Management

**Definition**: Model selection, switching, and transparency about which model is active.

**Design Guidance**:

- Signal when routing changes the model to prevent perceived deception
- Show model capabilities/limitations alongside selection
- Warn about cost differences between models
- Never silently downgrade without notification

---

### Parameters

**Definition**: Fine-tune generation settings (temperature, max length, style controls, etc.).

**Design Guidance**: Hide behind "Advanced" for novices; expose for experts. Show impact preview ("Higher temperature = more creative, less consistent").

---

### Prompt Enhancer

**Definition**: Automatic prompt improvement suggestions before submission.

**Design Guidance**: Show original vs. enhanced prompt side-by-side. Let user accept, reject, or modify the enhancement.

---

### Modes

**Definition**: Task-specific AI behavior profiles (e.g., "Creative mode", "Precise mode", "Code mode").

**Design Guidance**: Make the active mode visible at all times. Show how mode affects behavior.

---

### Preset Styles / Saved Styles

**Definition**: Pre-configured or user-saved parameter combinations for quick reuse.

**Design Guidance**: Organize by use case. Allow one-click application and customization.

---

### Voice and Tone

**Definition**: Configure AI personality characteristics (formal/casual, warm/professional, concise/detailed).

**Design Guidance**:

- Separate from content parameters; voice affects HOW things are said, not WHAT
- Combine with Memory for persistent personality across sessions
- Support context-switching (different voice for work vs. personal)

---

### Filters

**Definition**: Narrow the scope of AI input or output (date range, source type, content category).

---

## 4. GOVERNORS

_Human-in-the-loop features to maintain user oversight and agency._

### Action Plan

**Definition**: AI outlines intended steps before execution, allowing user confirmation or adjustment. The critical checkpoint for complex and compute-heavy tasks.

**Two Modes**:

- **Advisory**: Plans inform reasoning but don't require approval
- **Contractual**: Plans require explicit user verification before proceeding

**Variations**:

- **Step Lists**: Linear action sequences requiring quick confirmation
- **Execution Previews**: Structured plans with explicit approval gates
- **Content Outlines**: Document/slide scaffolds with optional confirmation
- **Adaptive Plans**: Evolving plans with repeated confirmations during multi-step processes

**Design Guidance**:

- Display plans BEFORE consuming resources
- Keep plans readable; users should understand intent in a few seconds
- Enable modification without requiring full regeneration
- Allow experienced users to collapse or bypass plans
- Ensure execution matches the plan; unexplained deviations erode trust quickly

**When to Use**: Complex tasks, expensive generation, agentic workflows, multi-step processes.

**Related Patterns**: Stream of Thought, Verification, Draft Mode.

---

### Stream of Thought

**Definition**: The visible trace of how AI navigated from input to answer, including plans formed, tools called, code executed, and decisions made.

**Three Expressions**:

1. **Human-readable plans**: Preview what the AI will do
2. **Execution logs**: Record tool calls, code execution, and results
3. **Compact summaries**: Capture logical reasoning, insights, and decisions

**Design Guidance**:

- Show the plan before acting; present a short, editable sequence of steps
- Keep plan, execution, and supporting evidence in synchronized but separate views
- Adjust disclosure level based on task complexity
- Treat every step as a clear state: queued, running, waiting, error, retried, completed
- Adapt to different modalities (text links, code export, voice summaries, visual paths)

**Universal Form**: "A bounded box, with details minimized or hidden behind a click, showing the AI's logic in real time or for review when complete."

**When to Use**: Any task > 5 seconds. Non-trivial reasoning. Multi-step processes.

**Related Patterns**: Citations, Controls, Action Plan.

---

### Controls

**Definition**: User controls for managing active AI generation.

**Four Controls**:

1. **Stop**: End generation mid-stream (most common; nearly universal)
2. **Pause**: Halt without losing progress; resume later
3. **Fast-forward**: Confirm continued generation for long responses
4. **Play/Submit**: Initiate new tasks (paper airplane, magic wand icons)

**Queue Pattern**: Let users stack tasks for AI to complete while it finishes previous work. Queued tasks can be modified or deleted without canceling current work.

**Design Guidance**:

- Stop button must be consistently placed and always one-click accessible
- Provide graceful pause and resume to prevent work loss
- Let users act in the flow of work; queue tasks without interrupting
- Use Variations instead of overwriting when regenerating

**When to Use**: During any generation that takes > 2 seconds.

**Related Patterns**: Action Plan, Sample Response.

---

### Draft Mode

**Definition**: Begin work using fewer details or less powerful processing before committing to a full, resource-intensive run.

**Variations**:

- **Explicit Drafting**: Intentional quality reduction framed positively (faster, cheaper)
- **Implicit Drafting**: Reduced step counts, short snippets, outlines before full output
- **Model Routing**: Default to cheaper model during iteration, upgrade on request

**Design Guidance**:

- Users should NEVER be surprised by lower-quality output
- Specify what's reduced (model tier, steps, resolution, duration) alongside speed/cost impact
- Preserve seeds, prompts, and parameters between draft and final versions
- Keep upgrade, duplication, and comparison functions single-click accessible
- If auto-switching occurs, surface clear notice with override options
- Display token, time, or credit impacts at decision points

**When to Use**: Expensive generation (images, video, presentations, long documents, code projects).

**Related Patterns**: Sample Response, Model Management, Parameters.

---

### Branches

**Definition**: Divergent exploration paths allowing users to explore "what if" without losing prior work.

**Design Guidance**: Visualize as a tree. Allow merging insights back to main thread. Show branch point clearly.

---

### Variations

**Definition**: Multiple output options generated from the same prompt for comparison and selection.

**Three Methods**:

- **Branched Variations**: Simultaneous generation (typically 4) displayed as a grid
- **Convergent Variations**: Linear list where user selects one to merge into main content
- **Preset Variations**: Pre-applied modifications (professional vs. casual tone) for direct comparison

**Design Guidance**:

- Keep follow-up actions close to maintain workflow momentum
- Enable regenerating new variants from the same interface
- Use adjustable parameters (quantity, seed, variation degree) while preserving metadata
- NEVER overwrite the original output without confirmation

**When to Use**: Image generation, writing, code suggestions, any creative output.

**Related Patterns**: Parameters, Branches, Regenerate.

---

### Citations

**Definition**: Connect generated output back to underlying source material for verification and trust.

**Four Variations**:

- **Inline Highlights**: Direct passage references within attached documents
- **Direct Quotations**: Specific quotes from longer texts backing each point
- **Multi-Source References**: Search results with metadata (titles, favicons) for scanning
- **Lightweight Links**: Full URLs listed at conclusion for transparency

**Design Guidance**:

- Match citation specificity to context (exact passages for facts, collections for discovery)
- Place citations where users naturally expect them (inline for claims, panels for exploration)
- Balance speed with depth through hover previews and click-through access
- Clearly indicate unavailable or missing sources rather than obscuring gaps
- Use concise metadata (titles, favicons, site names) for relevance assessment
- Allow filtering, removing, or adding citations without restarting generation

**When to Use**: Any factual claim, research output, document analysis, enterprise contexts.

**Related Patterns**: Summary, Synthesis, Footprints.

---

### References

**Definition**: Link to supporting materials without the inline attribution structure of citations.

---

### Verification

**Definition**: Confirmation gates before irreversible or high-impact actions.

**Design Guidance**: Show exactly what will happen. Make "cancel" the default/easy action.

---

### Memory

**Definition**: AI retains and references information across sessions, transforming interactions from transactional to persistent.

**Three Scopes**:

- **Global Memory**: Cross-all-surfaces retention; convenient but risks unintended application
- **Scoped Memory**: Workspace or conversation-limited; prevents carryover but less convenient
- **Ephemeral Memory**: Current-session-only; privacy-preserving, similar to incognito

**Design Guidance**:

- Memory should NEVER be a black box; show users when memories are added, allow management
- Distinguish preferences (communication style) from facts (biographical information)
- Support code-switching for different contexts (personal vs. professional)
- Mark capture moments with lightweight confirmations ("Saved to memory")
- Offer incognito/memory-off modes for temporary non-persistent sessions
- Enable selective editing, removal, or addition of remembered details

**When to Use**: Returning users, personalization, any product where context persistence adds value.

**Related Patterns**: Voice and Tone, Incognito Mode.

---

### Cost Estimates

**Definition**: Transparency about resource (tokens, compute time, credits) consumption before committing.

**Design Guidance**: Show estimated cost BEFORE execution. Compare to alternatives (draft vs. final, model A vs. model B).

---

### Sample Response

**Definition**: Quick small-scale preview before committing to full generation.

---

### Shared Vision

**Definition**: Collaborative alignment between user and AI on the intended outcome.

---

## 5. TRUST BUILDERS

_Give users confidence that AI results are ethical, accurate, and trustworthy._

### Disclosure

**Definition**: Label AI interactions and content so users can distinguish them from human-created content.

**Application Contexts**:

- **AI-Native Products**: Differentiate user-uploaded content from AI-captured sources (no need to disclose "this is AI" since users expect it)
- **Blended Products**: Label AI-generated or edited content mixed with human content
- **AI Agents**: Clearly mark bot-delivered content in chat environments
- **All Cases**: Proactively inform users when data collection occurs

**Disclosure Forms**:

- Bot and assistant labeling (names, avatars, badges)
- Feature-level disclosure (inline chips like "AI Assist")
- Output attribution (watermarks, "AI-generated" badges)

**Design Guidance**:

- Name the actor consistently with clear sender lines and distinct avatars
- Label actions, not features ("Summarized with AI" > "AI Assist")
- Use visual differentiation through color, opacity, or styling
- Balance branding with usability; don't confuse AI with human actors
- Avoid deception in sensitive contexts (support, healthcare)
- Disclose realistic synthetic media to prevent confusion
- Allow opt-out options where possible

**When to Use**: Always in blended content; always when AI agents interact; always for synthetic media.

**Related Patterns**: Consent, Caveat, Data Ownership, Incognito Mode.

---

### Caveat

**Definition**: UI elements reminding users that AI may be wrong, incomplete, or biased. Nearly ubiquitous but limited in effectiveness.

**Placement Contexts**:

- Below input fields or above outputs in chatbots
- Top of generated sections in document assistants
- Warning headers in API responses
- Spoken caveats in voice agents
- Stricter versions in enterprise settings

**Design Guidance**:

- Position where they align with outputs for moment-of-decision visibility
- Write in simple, clear language; link to technical documentation
- Targeted notes ("Check dates for accuracy") outperform generic warnings
- Use alongside complementary patterns (Citations, Verification), not alone
- Assume non-compliance: don't presume caveats prevent harmful behavior

**Critical Limitation**: Users develop "caveat blindness" due to ubiquity, similar to ignoring terms-of-service. Complex AI behavior resists reduction to simple warnings.

**When to Use**: All AI outputs. But never as the SOLE safety mechanism.

**Related Patterns**: Citations, Attachments.

---

### Consent

**Definition**: Intentionally obtaining permission before sharing user data with AI systems.

**Three Domains**:

- **Personal Data**: Recording or analyzing conversations, especially for training
- **Organizational Data**: Preventing proprietary information from reaching third-party AI
- **Other People's Data**: Recording voices, images, or text of non-primary users

**Variations**:

- **Opt-in Disclosure**: Active agreement before recording
- **Silent by Default**: Capture without notifying others (controversial)
- **Post-hoc Alerts**: Notify after recording begins
- **Consent for Training**: Explicit requests for data use in model fine-tuning

**Design Guidance**:

- Make consent explicit and visible from the surface where interaction occurs
- Opt-in as standard; silence cannot constitute agreement
- Differentiate consent types: recording, training, and sharing independently
- Enable reversibility: stop collection or delete data at any time
- Use multimodal indicators (LEDs, sound, vibration) when screens unavailable
- Notify ALL participants in shared environments, not just initiators
- Disclose downstream uses separately from core functionality
- Respect dignity beyond mere compliance

**When to Use**: Recording, transcription, data collection, model training, shared environments.

**Related Patterns**: Disclosure, Caveat, Data Ownership.

---

### Data Ownership

**Definition**: Transparency about how user data is stored, used, shared, and deleted.

**Design Guidance**: Separate from consent UI. Show clear toggles for each data use type. Enable export and deletion.

---

### Watermark

**Definition**: Mark AI-generated media for provenance tracking.

**Design Guidance**: Use Content Credentials (C2PA) standards. Balance visibility with aesthetics. Make watermark verification accessible.

---

### Footprints

**Definition**: Aggregate attribution showing origins of synthesized content.

---

### Incognito Mode

**Definition**: Non-persistent sessions where nothing is remembered or stored.

**Design Guidance**: Make entry/exit obvious. Show clear indicator throughout incognito session. Prevent accidental data capture.

---

## 6. IDENTIFIERS

_Distinct qualities of AI that can be modified at brand or model level._

### Avatar

**Definition**: The visual form AI takes when interacting with users. Serves three core functions: communicate operational state, establish entity identity, and mediate trust.

**Four Variations**:

- **Minimal Marks**: Lightweight icons (like Claude's starburst) emphasizing utility and neutrality without implying human agency
- **Branded Characters**: Distinctive but abstracted personas providing warmth and memorability; risk overpromising through parasocial attachment
- **Photorealistic/Animated Agents**: Fully animated assistants for immersive contexts; higher visual realism implies stronger competence expectations
- **Voice Avatars**: Synthetic voices with distinct accent, pitch, and cadence signaling state and personality without visual components

**Design Guidance**:

- Make strategic visibility choices (background utility vs. social partner)
- Use unambiguous state indicators through motion or sound
- Integrate avatar as a functional UI element, not decoration
- Voice IS avatar; it affects perceived competence
- Balance brand distinctiveness with abstraction
- Offer customization features where appropriate
- AVOID deceptive photorealism that oversells capability

**When to Use**: Any AI product where the AI has a visible "presence" (chat, voice, agents).

**Related Patterns**: Disclosure, Personality.

---

### Personality

**Definition**: The substantive behavioral characteristics of AI shaped by training and implementation choices. NOT a superficial overlay; personality meaningfully affects response patterns, emphasis, tone, hedging, and conversational boundaries.

**Design Guidance**:

- Acknowledge personality as unavoidable; even "neutral" models exhibit tendencies
- Balance consistency with adaptability; excessive tone variation erodes confidence
- Separate empathy from authority; warm responses must not compromise accuracy
- Signal when routing changes personality (model switching)
- Memory reinforces personality persistence and deepens parasocial bonds
- Guard against sycophancy: over-agreeableness boosts engagement but undermines agency
- Design attachment off-ramps: shift toward neutrality when excessive comfort-seeking emerges
- Evaluate personality in testing: assess false authority and tone drift over extended interactions

**When to Use**: Branding decisions, multi-persona products, voice assistants, long-form interactions.

**Related Patterns**: Model Management, Memory, Voice and Tone, Name.

---

### Name

**Definition**: The naming strategy for AI entities, affecting initial trust and capability expectations.

**Design Guidance**: Names set expectations. Human names imply human-like capability. Abstract names (Copilot, Assistant) set more appropriate expectations. Be consistent.

---

### Color

**Definition**: Using color to communicate brand identity and AI operational state.

**Design Guidance**: Reserve specific colors for AI state (thinking, generating, error, complete). Don't reuse AI state colors for other UI purposes.

---

### Iconography

**Definition**: Visual language specific to AI affordances (sparkle for AI-generated, brain for thinking, etc.).

**Design Guidance**: Be consistent across the product. Don't overuse AI-specific icons; use them at decision points and state changes only.

---

## Pattern Interaction Map

Patterns rarely exist in isolation. Common compositions:

```
ONBOARDING FLOW:
  Initial CTA → Gallery/Suggestions → Open Input → Follow-ups

GENERATION FLOW:
  Open Input + Parameters → Action Plan → Stream of Thought → Controls → Variations

TRUST FLOW:
  Disclosure → Citations → Caveat → Verification

PERSONALIZATION FLOW:
  Memory + Voice & Tone + Saved Styles → Adaptive Suggestions

AGENTIC FLOW:
  Open Input → Action Plan → Stream of Thought → Controls → Verification → Citations
```

---

## Implementation Notes for Kailash Applications

When building AI interfaces with the Kailash SDK ecosystem:

- **Kaizen agents** power the AI backend; the Signature system maps to Tuner parameters
- **Nexus** serves the multi-channel frontend (API for web, CLI for terminal, MCP for AI tools)
- **DataFlow** stores conversation history, memory, citations, and user preferences
- **Interactive Widgets (Skill 20)** handle the rendering of AI responses as structured UI
- **Conversation UX (Skill 22)** handles thread management and branching data models

The patterns in this document are DESIGN patterns, not implementation patterns. They describe WHAT to build and WHY, not HOW to build it in code. For implementation, pair this skill with the relevant framework specialist (frontend-developer, flutter-specialist, react-specialist).

---

**Source**: Shape of AI (shapeof.ai) by Emily Campbell. Licensed CC-BY-NC-SA.
**Version**: 1.0 - 2026-02-24
