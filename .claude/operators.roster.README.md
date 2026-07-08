# operators.roster.json — placeholder semantics

This note documents the `PLACEHOLDER-` person_id convention that
`.claude/operators.roster.schema.json`, `roster-schema-validate.js`, and the
genesis fold engine reference. It is the canonical prose home for the
architecture §2.1 "unenrolled-but-reserved person_id" contract.

## The `PLACEHOLDER-` prefix

A person_id key in `persons{}` MAY be prefixed with `PLACEHOLDER-`. The prefix
marks the slot as **reserved but not yet bound to a real signing key** — a
person_id that exists in the roster structurally but is not yet an enrolled
operator. The schema's `propertyNames.pattern` admits it explicitly:

```
^(PLACEHOLDER-)?(?!_)[a-zA-Z0-9][a-zA-Z0-9._-]*$
```

(The leading-alphanumeric / no-leading-underscore constraint rejects
`__proto__`-style prototype-pollution keys and path-traversal segments; the
optional `PLACEHOLDER-` prefix rides in front of that conservative identifier.)

## The shared predicate — `isUnenrolled`

Every consumer decides "is this person_id enrolled?" through ONE predicate so
the definition never drifts:

```js
// .claude/hooks/lib/roster-schema-validate.js
function isUnenrolled(personId) {
  return typeof personId === "string" && personId.startsWith("PLACEHOLDER-");
}
```

Downstream consumers rely on this shared predicate rather than re-deriving the
prefix check: `eligibility.js`, `derive-n.js`, `fold-genesis-anchor.js`,
`recovery-fallback.js`, and `genesis-ceremony.js` (which binds the signing key
to a **non-**`PLACEHOLDER-` owner person — a placeholder can never be the
genesis owner-bind target).

## Where placeholders appear

- **Reserved person slots.** A `PLACEHOLDER-<id>` key holds a roster position
  before its real key material is registered. `_validateProviderIdentity` skips
  the `github_login` / `principal` requirement for unenrolled entries — a
  placeholder is not yet bound to a collaborator login.
- **Scaffold roster detection (fresh genesis).** The genesis fold treats a
  roster whose `genesis.repo_owner` is unenrolled (per `isUnenrolled`) as a
  **scaffold roster** — the fresh-repo state before the owner is anchored. On
  that scaffold state, while the coordination log has no folded anchor yet,
  `genesis-anchor-guard.js` advisory-passes-through so the first commits can
  land; its fail-closed block engages only once a real (non-scaffold) owner is
  written without a folded anchor. Writing a real
  (non-placeholder) owner into the roster BEFORE the ceremony folds the anchor
  puts the repo into a half-enrolled fail-CLOSED state — run the ceremony
  before the first signed commit (see `skills/45-genesis-bootstrap/SKILL.md`
  and `skills/43-ecosystem-init/SKILL.md` § "Enroll BEFORE the bootstrap
  commit").

## Attribution is by key, not by placeholder name

A `PLACEHOLDER-` key is signage only, exactly like `display_id` — it carries no
authority. Authority is bound to `verified_id` (a signing-key fingerprint) and
`person_id` once the real key is registered. Tooling MUST attribute via
`verified_id`, never a placeholder key.
