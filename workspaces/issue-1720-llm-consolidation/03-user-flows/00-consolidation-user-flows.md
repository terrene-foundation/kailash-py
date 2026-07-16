# #1720 — User Flows

"User" = the developer / agent calling the four-axis `LlmClient`, and (Waves 2–4) the
migrated internal consumers. Each flow is what a real caller invokes and observes.

## UF-1 — Tool-calling on the four-axis client (Wave 1)

```python
client = LlmClient.from_deployment(dep)
resp = await client.complete(messages, tools=[{"type": "function", "function": {...}}])
# resp["tool_calls"] == [{"id","type":"function","function":{"name","arguments"}}]
# feed a role:"tool" result back, call complete() again → model converges
```

Observable: `tool_calls` surfaced in the SAME normalized shape for OpenAI AND Anthropic
AND Bedrock (cross-wire parity). Today: `tool_calls` is silently dropped.

## UF-2 — Structured output (Wave 1)

```python
resp = await client.complete(messages, response_format={"type": "json_schema", "json_schema": {...}})
# resp["text"] is valid JSON conforming to the schema
```

Observable: the wire emits the provider-native structured directive; caller parses `text`.

## UF-3 — Offline test with the mock preset (Wave 1)

```python
client = LlmClient.from_deployment(mock_preset())
resp = await client.complete(messages)   # NO network POST; deterministic canned response
```

Observable: Tier-1 tests run offline; this preset is the precondition for deleting
`providers/llm/mock.py` (Wave 4).

## UF-4 — Byte-neutrality (the Wave-1a safety walk)

```python
# BEFORE any new field is set, the emitted payload is byte-identical to pre-#1720
payload_old == payload_new   # for every wire, tools/response_format/... all None
```

Observable: no existing caller's behavior changes when Wave 1 lands. This is the walk that
gates "Wave 1a done".

## UF-5 — Consumer migration (Wave 3, human-gated)

`llm_agent._provider_llm_response` dual-runs (Wave 2) then switches (Wave 3) from
`get_provider().chat(...)` to `LlmClient.complete(...)`. Observable: agent tool-calling +
structured output behave identically before/after (the dual-run comparison is the evidence).

## UF-6 — Legacy delete (Wave 4, irreversible, human-gated)

Observable: `LlmClient.from_deployment(...).complete(...)` runs end-to-end green in the
release pipeline (the `tests/regression/` four-axis quickstart), AND a mechanical sweep
shows zero residual `kaizen.providers` imports, BEFORE `providers/llm/` is removed.
