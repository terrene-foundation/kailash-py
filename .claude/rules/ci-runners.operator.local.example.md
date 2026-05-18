# ci-runners Operator-Local Values — Schema / Template

Operator-local concrete values for the kailash-py self-hosted CI runbook
(`.claude/variants/py/rules/ci-runners.md`, rules §6/§7/§8).

Copy this file to `ci-runners.operator.local.md` (same directory) and fill in
your real deployment values. `ci-runners.operator.local.md` is **gitignored and
is NEVER committed or synced** — it is the only place the operator-specific
runner hostnames and the org-derived self-hosted runner label live. The shipped
rule carries only generic placeholders + this schema, so no operator/engagement
identifiers appear in any synced `.claude/` artifact (issue #260 / #252
disclosure class — same pattern as #255's `repin-targets.local.json` and the
rs `ci-runners.operator.local.example.md`).

When you execute a protocol in `ci-runners.md`, read THIS deployment's values
from your local file and substitute the placeholders into the commands.

Lines beginning with `#`/`>` (like this header) are documentation; the
key → value table below is the load-bearing content.

---

## Placeholders → operator values

| Placeholder in `ci-runners.md` | What it is                                                                                                                                                                                                             | Example value       |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `<runner-host-1>`              | Hostname/registered name of the first self-hosted runner referenced in the §6 zombie-job example (largest / primary build host).                                                                                       | `example-runner-1`  |
| `<runner-host-2>`              | Hostname/registered name of the second self-hosted runner referenced in the §6 zombie-job example.                                                                                                                     | `example-runner-2`  |
| `<runner-label-arm>`           | Self-hosted ARM runner LABEL used in `runs-on:` for tag-gated release jobs (§8) and as the third §6 zombie-job example. Typically an org-derived label, NOT a GitHub-hosted label nor the Foundation slug.             | `example-linux-arm` |
| `<runner-name>` / `<name>`     | The per-runner suffix used in the `launchctl`/`systemctl` service-label path (`actions.runner.terrene-foundation-kailash-py.<runner-name>`) and the launchd plist filename (`com.github.actions.runner.<name>.plist`). | `runner-1`          |

## Notes

- `terrene-foundation/kailash-py` is the canonical **Foundation** repo path and
  is a DIFFERENT, legitimate value — it is never templated and appears verbatim
  in the shipped rule's `gh api`, service-label, and plist references.
- `<runner-label-arm>` is the **non-Foundation**, org-derived dispatcher label a
  release job targets via `runs-on:`. It is distinct from `<runner-host-N>`
  (a host identity used only as an illustrative example in the §6 prose).
- The service label / plist stem on macOS is the launchd job label registered
  by the runner installer; `launchctl print gui/$UID | grep -i runner` on the
  host reveals the exact suffix for this deployment.
- Keep this file's structure identical to the schema above so a reader can map
  every placeholder mechanically and round-trip-reconstruct every command.
