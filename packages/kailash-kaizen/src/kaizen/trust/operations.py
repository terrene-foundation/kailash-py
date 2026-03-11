"""
Trust Operations — compatibility shim re-exporting from eatp.operations.

All core trust operations (ESTABLISH, DELEGATE, VERIFY, AUDIT) and
supporting types now live in the ``eatp`` package.  This module re-exports
them so that existing ``from kaizen.trust.operations import ...`` continues
to work.

The Kaizen-specific ``OrganizationalAuthorityRegistry`` (DataFlow-backed)
is also re-exported for backwards compatibility.
"""

from eatp.operations import *  # noqa: F401,F403

# Re-export Kaizen-specific DataFlow-backed registry for backwards compat
from kaizen.trust.authority import OrganizationalAuthorityRegistry  # noqa: F401
