# ci-runners Operator-Local Values — THIS DEPLOYMENT (gitignored)

Real concrete values for the kailash-py self-hosted CI runbook on this
operator's deployment. **Gitignored — never committed, never synced**
(issue #260 / #252). Populated from the pre-#260 verbatim contents of
`ci-runners.md`. Schema: `ci-runners.operator.local.example.md`.

When executing a protocol in `ci-runners.md`, substitute these values for the
generic placeholders.

---

## Placeholders → real values (this deployment)

| Placeholder in `ci-runners.md` | Real value                                     |
| ------------------------------ | ---------------------------------------------- |
| `<runner-host-1>`              | jacks-mac-studio                               |
| `<runner-host-2>`              | esperies-mini                                  |
| `<runner-label-arm>`           | esperie-linux-arm                              |
| `<runner-name>` / `<name>`     | (per-host suffix, e.g. registered runner name) |

## Reconstructed commands / values (real values substituted)

§6 — zombie-job cancellation protocol (illustrative runner examples):

```
jacks-mac-studio, esperies-mini, esperie-linux-arm
```

§8 — tag-gated release jobs (`runs-on:` label substitution):

```yaml
runs-on: esperie-linux-arm
```

§8 Why/Origin: the tag-time bugs (missing build deps, missing `gh` CLI)
surfaced on `esperie-linux-arm`.

Note: `terrene-foundation/kailash-py` in the shipped rule's `gh api`,
service-label, and plist references is the canonical Foundation path and is
NOT templated — it stays verbatim.
