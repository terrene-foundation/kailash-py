# DECISION — Cross-repo READ authorized: kailash-rs FeatureStore retrieval check

cross-repo-authorized: terrene-foundation/kailash-rs

## Grant (User-Authorized Exception — repo-scope-discipline.md, all five conditions)

1. **User-initiated** — genuine user turn (2026-06-03).
2. **Explicit + specific** — verbatim: "i approve your cross-sdk check". The action I proposed and the user approved: a READ-ONLY inspection of the kailash-rs FeatureStore retrieval path to determine whether it has the same #1241 gap (canonical retrieval surface cannot complete because the binding consumes a FeatureGroup the schema doesn't satisfy). Per cross-sdk-inspection.md MUST-1.
3. **Confirmed** — I proposed "if you want the cross-SDK Rust check, say the word"; user replied with explicit approval before any read.
4. **Journaled before acting** — this entry + the marker line above land BEFORE the first `gh`/read command against kailash-rs.
5. **Scoped exactly** — ONLY read the kailash-rs FeatureStore / feature-retrieval source. NO writes. Filing any cross-SDK issue against kailash-rs requires a SEPARATE human gate per upstream-issue-hygiene.md Rule 1 (draft + present + await per-issue approval). This grant covers the READ only.

## Bound

Local clone read OR `gh` read against terrene-foundation/kailash-rs, scoped to the FeatureStore retrieval surface. Any finding recorded here + in the architecture plan; any upstream filing deferred to a separate gate.

## Finding (cross-SDK READ result, 2026-06-03)

kailash-rs `FeatureStore` (`crates/kailash-ml/src/engine/feature_store.rs:136`) is a
DIFFERENT architecture: a `save`/`load`/`list`/`delete`/`latest_version` feature-set
artifact store backed by a `FeatureStoreBackend` trait (`InMemoryFeatureStore` /
`FileSystemFeatureStore`, storing `Array2<f64>`). It has NO `get_features`, NO
`FeatureGroup`, NO `.materialize`, NO DataFlow-bridge, NO point-in-time retrieval.

→ The #1241 bug class (declarative FeatureSchema forwarded to a FeatureGroup-shaped
binding it cannot satisfy) is **structurally impossible in Rust** — Rust uses a
save/load artifact-store design, not the polars-native DataFlow-bridge the Python
canonical surface uses. **No cross-SDK issue to file** (cross-sdk-inspection.md MUST-1
checklist: other SDK does NOT have this bug; Rule 3a structural API-divergence).

Separate, pre-existing observation (NOT #1241, NOT filed): the two SDKs' FeatureStore
designs diverge (py = DataFlow-bridge w/ PIT retrieval; rs = save/load artifact store).
That EATP-D6 semantic-divergence question is broader than #1241 and out of scope here.

Cross-repo grant CLOSED — read-only, no writes performed, no issue filed.
