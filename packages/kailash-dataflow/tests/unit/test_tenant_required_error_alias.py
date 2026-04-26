# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — TenantRequiredError canonical name + MLTenantRequiredError
back-compat alias coverage.

Closes F-B-23 (W6-003). Renamed ``MLTenantRequiredError`` →
``TenantRequiredError`` in kailash-dataflow 2.3.2 to match the spec's
canonical name (``specs/dataflow-ml-integration.md`` § 5). The old name
remains as a deprecated alias slated for removal in v3.0; access emits a
``DeprecationWarning`` (per ``rules/zero-tolerance.md`` Rule 1 / user
``feedback_no_shims`` — the alias is a 1-release migration bridge, NOT
a permanent shim).

This file is intentionally Tier 1: the alias resolution is a
module-import-time concern with no infrastructure dependency.
"""

from __future__ import annotations

import warnings

import pytest


@pytest.mark.unit
def test_tenant_required_error_canonical_import_succeeds():
    """Canonical name imports without warning from both surfaces."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any DeprecationWarning would fail
        from dataflow.ml import TenantRequiredError as Public  # noqa: F401
        from dataflow.ml._errors import TenantRequiredError as Internal  # noqa: F401

    # Both surfaces resolve to the same class object.
    from dataflow.ml import TenantRequiredError as Public
    from dataflow.ml._errors import TenantRequiredError as Internal

    assert Public is Internal


@pytest.mark.unit
def test_alias_resolves_to_canonical_class_via_dataflow_ml():
    """``dataflow.ml.MLTenantRequiredError`` IS ``dataflow.ml.TenantRequiredError``."""
    import dataflow.ml as ml_mod

    canonical = ml_mod.TenantRequiredError

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        alias = ml_mod.MLTenantRequiredError

    assert alias is canonical, (
        "MLTenantRequiredError MUST resolve to TenantRequiredError; "
        "alias is intentional 1-release back-compat bridge, NOT a separate class"
    )


@pytest.mark.unit
def test_alias_resolves_to_canonical_class_via__errors():
    """``dataflow.ml._errors.MLTenantRequiredError`` IS the canonical class."""
    import dataflow.ml._errors as errors_mod

    canonical = errors_mod.TenantRequiredError

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        alias = errors_mod.MLTenantRequiredError

    assert alias is canonical


@pytest.mark.unit
def test_alias_emits_deprecation_warning_on_access():
    """Accessing ``MLTenantRequiredError`` emits exactly one DeprecationWarning."""
    import dataflow.ml as ml_mod

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Trigger the __getattr__ once.
        _ = ml_mod.MLTenantRequiredError

    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert (
        len(deprecation_warnings) == 1
    ), f"expected exactly 1 DeprecationWarning, got {len(deprecation_warnings)}"
    msg = str(deprecation_warnings[0].message)
    assert "MLTenantRequiredError" in msg
    assert "TenantRequiredError" in msg
    assert "v3.0" in msg, "deprecation warning MUST cite removal milestone"


@pytest.mark.unit
def test_alias_emits_deprecation_warning_via__errors_module():
    """The same DeprecationWarning fires when accessing through ``_errors``."""
    import dataflow.ml._errors as errors_mod

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = errors_mod.MLTenantRequiredError

    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 1
    assert "v3.0" in str(deprecation_warnings[0].message)


@pytest.mark.unit
def test_raise_via_alias_caught_by_canonical_except():
    """Raising via either name is caught by ``except TenantRequiredError``."""
    from dataflow.ml import TenantRequiredError

    # Raise via canonical name.
    with pytest.raises(TenantRequiredError, match="canonical"):
        raise TenantRequiredError("canonical")

    # Raise via the alias (ignoring the deprecation warning emitted on lookup).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from dataflow.ml import MLTenantRequiredError as AliasCls

    with pytest.raises(TenantRequiredError, match="via alias"):
        raise AliasCls("via alias")


@pytest.mark.unit
def test_alias_absent_from_public_all():
    """``MLTenantRequiredError`` is intentionally NOT in ``__all__``.

    The alias is reachable via ``__getattr__`` for migration callers; star-
    imports MUST pick up only the canonical name so new code does not
    inherit the deprecated symbol.
    """
    import dataflow.ml as ml_mod
    import dataflow.ml._errors as errors_mod

    assert "TenantRequiredError" in ml_mod.__all__
    assert "MLTenantRequiredError" not in ml_mod.__all__
    assert "TenantRequiredError" in errors_mod.__all__
    assert "MLTenantRequiredError" not in errors_mod.__all__


@pytest.mark.unit
def test_unknown_attribute_raises_attribute_error():
    """``__getattr__`` MUST NOT swallow typos — only the documented alias resolves."""
    import dataflow.ml as ml_mod

    with pytest.raises(AttributeError, match="MLTenantRequired"):
        # Plausible typo that MUST NOT be silently aliased.
        _ = ml_mod.MLTenantRequired
