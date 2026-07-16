export const meta = {
  name: '1720-wave-a-redteam-round',
  description: 'One holistic redteam round over the #1720 Wave-A diff: parallel multi-dimension review, adversarial verify each finding, return only confirmed findings ranked by severity',
  phases: [
    { title: 'Review' },
    { title: 'Verify' },
  ],
}

// args: { base, head, round, priorConfirmed }  (priorConfirmed: array of {file, summary} already fixed/known)
const base = (args && args.base) || 'main'
const head = (args && args.head) || 'feat/1720-wave-a-foundation'
const round = (args && args.round) || 1
const prior = (args && args.priorConfirmed) || []

const priorText = prior.length
  ? `\nAlready-surfaced findings from prior rounds (do NOT re-report unless still present after a fix):\n${prior.map((p, i) => `${i + 1}. ${p.file}: ${p.summary}`).join('\n')}`
  : '\n(first round — no prior findings)'

const scope = `Scope: the diff \`git diff ${base}...${head}\` (kailash-py, packages/kailash-kaizen). This is #1720 Wave-A: the dual-run tool_choice="required" fix, the shared kaizen.llm.deployment_resolver (+azure mapping, +legacy_tool_choice_default, +UnsupportedDeploymentProvider for azure_ai_foundry), EmbedOptions.input_type pin, F3 HuggingFace chat-schema routing (CompletionRouting.use_chat_schema + client dispatch guard + huggingface_chat_preset), and the tests/parity/ offline legacy-vs-four-axis harness. NONE of this cuts over any production consumer (that is Wave-B, gated) — flag any change that DOES alter a live path as a HIGH finding.`

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    ran: { type: 'boolean', description: 'true if you actually completed the review (evidence gate)' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          file: { type: 'string' },
          symbol: { type: 'string', description: 'grep-stable symbol anchor' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string', description: 'concrete inputs/state -> wrong behavior' },
        },
        required: ['severity', 'file', 'summary', 'failure_scenario'],
      },
    },
  },
  required: ['ran', 'findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    ran: { type: 'boolean' },
    real: { type: 'boolean', description: 'true only if the defect genuinely exists and reproduces' },
    reasoning: { type: 'string' },
    corrected_severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NOT_A_BUG'] },
  },
  required: ['ran', 'real', 'reasoning', 'corrected_severity'],
}

const DIMENSIONS = [
  {
    key: 'correctness',
    agentType: 'reviewer',
    prompt: `You are the CORRECTNESS reviewer for #1720 Wave-A, round ${round}. ${scope}${priorText}

Run MECHANICAL sweeps BEFORE judgment, then reason:
1. \`git -C /Users/esperie/repos/kailash/build/kailash-py diff ${base}...${head} --stat\` and read the full diff of changed src files.
2. tool_choice invariant: confirm the dual-run shadow now reproduces legacy tool_choice="required" (tools present + unset) via legacy_tool_choice_default; grep that legacy openai/azure/docker default matches what the helper returns. A mismatch is HIGH.
3. F3: confirm the classic HF path stays BYTE-NEUTRAL when use_chat_schema is False/unset (no tools/tool_choice keys), and the flag is guarded to the HuggingFaceInference wire only (not passed to other shapers). A universal-pass or a byte-changing classic path is HIGH.
4. resolver: confirm azure/azure_openai map to a correct OpenAiChat-compatible deployment and azure_ai_foundry raises UnsupportedDeploymentProvider (typed, not silent None).
5. Confirm NO production consumer path changed (Wave-A is additive/test/shadow only).
Report findings via the schema. Set ran=true only if you read the actual diff.`,
  },
  {
    key: 'security',
    agentType: 'security-reviewer',
    prompt: `You are the SECURITY reviewer for #1720 Wave-A, round ${round}. ${scope}${priorText}

Focus: (1) no hardcoded secrets/tokens/api keys in src or the new tests/parity fixtures (placeholder keys only); (2) the HF chat route + BYOK api_key threading does not leak the key into logs/URLs (observability §8 — schema/field names hashed, no raw creds); (3) azure credential resolution reads env/config only; (4) the parity fixtures contain no real credentials. Read the actual diff (\`git diff ${base}...${head}\`) before judging. Report via schema; ran=true only if you read the diff.`,
  },
  {
    key: 'orphan_parity',
    agentType: 'general-purpose',
    prompt: `You are the ORPHAN + PARITY-VALIDITY reviewer for #1720 Wave-A, round ${round}. ${scope}${priorText}

Two jobs:
1. ORPHAN sweep (orphan-detection rules): every new public symbol in kaizen.llm __all__ (resolve_deployment_for, legacy_tool_choice_default, UnsupportedDeploymentProvider, huggingface_chat_preset) has an eager import AND a real call site/test. \`pytest --collect-only -q\` across tests/ exits 0. use_chat_schema field is genuinely consumed (not an accepted-but-unused kwarg — zero-tolerance 3c).
2. PARITY-VALIDITY (critical): inspect tests/parity/ — verify it injects SHARED canned bytes into BOTH the legacy and four-axis stacks (NOT each mock self-generating, which would be FALSE parity). Any parity assertion that relies on the two mocks agreeing by themselves is a HIGH finding (parity theatre). Confirm one-sided wires (bedrock/vertex/mistral) and azure_ai_foundry blocker use strict-xfail/documented-delta, not silent skip or false assert-equal. Run \`cd /Users/esperie/repos/kailash/build/kailash-py/packages/kailash-kaizen && ../../.venv/bin/python -m pytest tests/parity/ -q\` and confirm green/xfail.
Report via schema; ran=true only if you actually ran the commands.`,
  },
]

log(`Redteam round ${round} over ${base}...${head} — ${DIMENSIONS.length} dimensions`)

const perDim = await pipeline(
  DIMENSIONS,
  (d) => agent(d.prompt, { label: `review:${d.key}`, phase: 'Review', agentType: d.agentType, schema: FINDINGS_SCHEMA })
    .then((r) => ({ dim: d.key, review: r })),
  ({ dim, review }) => {
    if (!review || review.ran !== true) {
      // Evidence gate: errored/empty reviewer is ZERO evidence — re-run once.
      const d = DIMENSIONS.find((x) => x.key === dim)
      return agent(d.prompt + '\n\n[RE-RUN: your prior return was empty/errored; you MUST actually run the sweeps and set ran=true.]',
        { label: `review:${dim}:rerun`, phase: 'Review', agentType: d.agentType, schema: FINDINGS_SCHEMA })
        .then((r2) => ({ dim, review: r2 }))
    }
    return { dim, review }
  },
  // Verify each finding adversarially (independent skeptic, default-to-refuted).
  // EVIDENCE GATE: a throttled/errored verify is ZERO evidence — retry once, and
  // if still unresolved SURFACE it as `unverified` (NEVER silently drop it, the
  // round-1 false-convergence bug).
  ({ dim, review }) => {
    const findings = (review && review.findings) || []
    if (!findings.length)
      return { dim, ran: review && review.ran === true, confirmed: [], unverified: [] }
    const verifyPrompt = (f, retry) =>
      `Adversarially VERIFY this #1720 Wave-A finding. Default to real=false unless you can reproduce it against the actual code at /Users/esperie/repos/kailash/build/kailash-py (packages/kailash-kaizen). Read the cited file, run the repro if you can.

Finding [${f.severity}] ${f.file} ${f.symbol || ''}: ${f.summary}
Failure scenario: ${f.failure_scenario}

Is this a REAL defect in the ${base}...${head} diff, or a false positive? ${scope}${retry ? '\n\n[RE-RUN: prior verify returned empty/errored; you MUST actually read the code and set ran=true.]' : ''}`
    return parallel(findings.map((f) => async () => {
      let v = await agent(verifyPrompt(f, false),
        { label: `verify:${dim}:${(f.file || '').split('/').pop()}`, phase: 'Verify', schema: VERDICT_SCHEMA })
      if (!v || v.ran !== true) {
        v = await agent(verifyPrompt(f, true),
          { label: `verify:${dim}:${(f.file || '').split('/').pop()}:rerun`, phase: 'Verify', schema: VERDICT_SCHEMA })
      }
      return { finding: f, verdict: v }
    })).then((verds) => {
      const confirmed = verds
        .filter((x) => x.verdict && x.verdict.ran === true && x.verdict.real === true && x.verdict.corrected_severity !== 'NOT_A_BUG')
        .map((x) => ({ ...x.finding, severity: x.verdict.corrected_severity, verify_reasoning: x.verdict.reasoning }))
      const unverified = verds
        .filter((x) => !x.verdict || x.verdict.ran !== true)
        .map((x) => ({ ...x.finding, note: 'verify errored/throttled after retry — UNVERIFIED, not clean' }))
      return { dim, ran: review.ran === true, confirmed, unverified }
    })
  }
)

const results = perDim.filter(Boolean)
const allRan = results.every((r) => r.ran === true)
const confirmed = results.flatMap((r) => r.confirmed || [])
const unverified = results.flatMap((r) => r.unverified || [])
const sevRank = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
confirmed.sort((a, b) => (sevRank[a.severity] ?? 9) - (sevRank[b.severity] ?? 9))

log(`Round ${round}: allReviewersRan=${allRan}, confirmed=${confirmed.length}, unverified=${unverified.length}`)

// A round is clean ONLY when every reviewer ran, zero confirmed findings, AND
// zero findings left unverified (an unverified finding is not evidence of clean).
return {
  round,
  base,
  head,
  allReviewersRan: allRan,
  clean: allRan && confirmed.length === 0 && unverified.length === 0,
  confirmed,
  unverified,
}
