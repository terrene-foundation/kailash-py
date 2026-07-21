# DISCOVERY — Serializer-set completeness is a distinct signed-model defect polarity from field-addition

Date: 2026-07-21. Repo class: BUILD. Author: agent. Phase: codify.
relates_to: 0009-DECISION-codify-cross-sdk-serializer-completeness

## The discovery

A cross-SDK signed model (an Ed25519-signed delegation, envelope, or audit record) has
TWO orthogonal ways its serialization can silently break cross-SDK / cross-version
signature verification, and they are OPPOSITE polarities requiring OPPOSITE fixes:

1. **Field ADDED (Rule 4d, #1510):** a new optional field emits a `null` key on the
   not-configured pre-image → changes the signed bytes of EVERY existing instance → they
   fail verify. Fix: PRUNE-when-unset so the not-configured case is byte-identical to
   pre-addition.
2. **Field DROPPED on round-trip (Rule 4e, #1841):** a field ALREADY in the pre-image is
   omitted by ONE serializer among N → the reconstructed record can't recompute the
   pre-image → verify FALSE. Fix: ONE shared serde wired into EVERY serializing path (the
   `security.md` Multi-Site Plumbing / Pre-Encoder Consolidation pattern at the
   persistence layer).

Both are byte-for-byte cross-SDK contract breaks (`cross-sdk-inspection.md` Rule 4), and
CRUCIALLY both are INVISIBLE to per-serializer unit tests — each serializer's own
round-trip test exercises only the fields THAT serializer emits, so a dropped field is
un-observable at the unit layer.

## Why the per-shard redteam structurally could not catch it

#1841 shipped v2/v3 fold-field enrichment across multiple parallel worktree shards. Each
shard's redteam reviewed only its own diff. The cross-serializer completeness break lives
in the UNION of the shards (the store serializer omitted what the record serializer added)
— a gap no per-shard reviewer could see. Only the HOLISTIC post-multi-wave redteam
(`agents.md` § Holistic Post-Multi-Wave Redteam), scoped to the union of all merged
shards on main, surfaced it. This is direct field-evidence for that rule.

## The meta-lesson for verification design

A test can satisfy the LETTER of "add an e2e round-trip regression" while proving NOTHING:
a legacy / all-unset record round-trips an empty fold dict and asserts verify TRUE without
exercising any fold field. The adversarial security review (R2) caught that the FIRST draft
of Rule 4e mandated only the positive pole — the exact inert-tripwire the originating bug
would slip past. The DISCRIMINATING requirement (a FULLY-CONFIGURED record + a NEGATIVE
pole: strip any fold field → verify FALSE) is what makes the field provably load-bearing.
The negative pole, not the positive one, is the load-bearing assertion. Likewise a
"wired into every serializer" mandate enforced by manual grep re-introduces the exact
human-completeness step the bug escaped — the mechanical backstop must enumerate the
serializer set by a NON-CIRCULAR predicate (find functions by "returns a serialization
dict", never by "imports the serde" — the latter can only find compliant functions, never
the dropper).

## For Discussion

1. The R2 security review found that the FIRST codification of a fix-pattern rule tends to
   mandate the POSITIVE proof (the fix works) and omit the NEGATIVE proof (the guard is
   load-bearing / can't be authored inert). Is "every fix-pattern rule must mandate both
   the positive AND the negative pole of its regression" a generalizable meta-rule worth
   surfacing beyond this clause?
2. The holistic redteam caught a break the per-shard reviews structurally could not —
   counterfactually, if #1841 had shipped as ONE shard (no parallel decomposition), would
   the per-shard == holistic review have caught it, or is the store-vs-record split
   independent of shard structure (i.e. a single-shard reviewer would ALSO have missed the
   cross-serializer gap because unit tests hide it)?
