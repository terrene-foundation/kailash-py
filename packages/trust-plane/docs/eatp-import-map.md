# EATP Import Map — Trust-Plane

Last Updated: 2026-03-15

This document maps every EATP symbol imported by trust-plane, organized by source module. Use this to assess the impact of EATP API changes on trust-plane.

## By Source Module

### `eatp` (root)

| Symbol              | Used In                    |
| ------------------- | -------------------------- |
| `CapabilityRequest` | `project.py`, `migrate.py` |
| `TrustKeyManager`   | `project.py`, `migrate.py` |
| `TrustOperations`   | `project.py`, `migrate.py` |

### `eatp.authority`

| Symbol                    | Used In                    |
| ------------------------- | -------------------------- |
| `AuthorityPermission`     | `project.py`, `migrate.py` |
| `OrganizationalAuthority` | `project.py`, `migrate.py` |

### `eatp.chain`

| Symbol               | Used In                            |
| -------------------- | ---------------------------------- |
| `ActionResult`       | `project.py`, `cli.py`, `proxy.py` |
| `AuthorityType`      | `project.py`, `migrate.py`         |
| `CapabilityType`     | `project.py`, `migrate.py`         |
| `VerificationResult` | `project.py`                       |

### `eatp.crypto`

| Symbol             | Used In      |
| ------------------ | ------------ |
| `generate_keypair` | `project.py` |

### `eatp.enforce.shadow`

| Symbol           | Used In      |
| ---------------- | ------------ |
| `ShadowEnforcer` | `project.py` |

### `eatp.enforce.strict`

| Symbol           | Used In                                             |
| ---------------- | --------------------------------------------------- |
| `HeldBehavior`   | `project.py`                                        |
| `StrictEnforcer` | `project.py`                                        |
| `Verdict`        | `project.py`, `proxy.py`, `conformance/__init__.py` |

### `eatp.postures`

| Symbol                     | Used In                                 |
| -------------------------- | --------------------------------------- |
| `PostureStateMachine`      | `project.py`                            |
| `PostureTransitionRequest` | `project.py`                            |
| `TrustPosture`             | `project.py`, `conformance/__init__.py` |

### `eatp.reasoning`

| Symbol                 | Used In                                                        |
| ---------------------- | -------------------------------------------------------------- |
| `ConfidentialityLevel` | `project.py`, `cli.py`, `bundle.py`, `conformance/__init__.py` |
| `ReasoningTrace`       | `project.py`, `conformance/__init__.py`                        |

### `eatp.store.filesystem`

| Symbol            | Used In                    |
| ----------------- | -------------------------- |
| `FilesystemStore` | `project.py`, `migrate.py` |

## Summary

- **6 trust-plane source files** import from EATP
- **9 EATP submodules** are used
- **19 unique symbols** imported
- **Highest-impact module**: `project.py` (imports from all 9 submodules)
