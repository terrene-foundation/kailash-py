# Codex CLI modernization — 2026-09-28

User-authorized scope: update this repository's Codex docs, guides and artifacts using subagents; verify and land all changes on `dev`; remove the task's worktrees, branches and refs. Separately, inspect loom read-only and deliver complete adaptation guidance to the named work-consol pickup directory. This does not authorize editing loom or promoting dev to main.

Baseline: kailash-py `4df93818243fec527590876c0022f6d1f8cacb5a`; loom `e3abb6b765186b70ad841edcc3445a1cbc0b3a80`; installed CLI `0.154.0`; latest official release listed on audit date `0.157.1`.

## Approved implementation decomposition

| Lane | Owned surface | Invariants | Verification |
| --- | --- | --- | --- |
| Documentation | Codex guide, architect, command/skill authoring and delegation references, coordination skill | Accurate dated capabilities; canonical/generated provenance; honest evidence scope; no permission broadening | Source/generated checks, links, absolute-state obsolete-claim review |
| Hook compatibility | Codex registration, runtime wrapper, shared output formatter's Codex branch, hook-authoring guidance | Correct matcher; stable root resolution; event-specific output; preserve CC/Gemini contracts; preserve stdin/status | Focused subprocess tests with negative controls and event/runtime coverage |
| Artifact emission | CLI emitter, path adaptation, specialist definitions/prompts and tests | Preserve source references; valid native definitions; exclusions/tier/role parity; preserve compatibility; consumer projection boundary | Fixture emission, TOML parsing, inclusion/exclusion tests, generated-content checks |
| Integration | Combined verification, baseline regeneration where appropriate, delivery report and loom package | Reviewed union; clean dev landing; preserve other sessions; bounded cleanup | Two consecutive clean correctness/security rounds; targeted tests; remote SHA ancestry and worktree/ref inventory |

Each implementation lane has an isolated sibling worktree and conventional commit. Root integrates commits without touching other sessions' worktrees. No new sync manifest is introduced into this BUILD repo: loom's distribution spec requires a narrowed consumer projection.

## Research corrections carried into implementation

- The review example combining `--uncommitted` and `--base` is rejected by the installed CLI.
- Bash-only hooks and generic-only agents are obsolete claims against current official docs.
- Current docs describe `.agents/skills`; this session still exposes `.codex/skills`. Preserve compatibility rather than infer removal.
- A queue acceptance receipt is not a recipient acknowledgement.
- Native hook availability is not proof that a particular registration is trusted or enforced.
- Canonical source references must not be rewritten into generated authority paths.

The delivery evidence will distinguish fixture/subprocess checks from live CLI behavior. No claim of runtime enforcement, named-agent execution or headless reliability may exceed the instrument's tested scope.
