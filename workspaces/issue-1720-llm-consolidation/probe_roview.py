# SUPERSEDED 2026-09-11 (/sweep): roview finding RESOLVED on dev (L13 ReadOnlyAttributeProxy.__getattribute__).
# Retained as the verification trail; the bypass this probes for no longer exists on dev.

import sys

sys.path.insert(0, "packages/kailash-pact/src")
import inspect

from pact import engine as E

src = inspect.getsource(E._ReadOnlyGovernanceView)
print("has __getattr__ blocklist :", "_BLOCKED" in src)
print("has __getattribute__ guard:", "__getattribute__" in src)
print("--- is _engine set as a normal instance attribute? ---")
init = inspect.getsource(E._ReadOnlyGovernanceView.__init__)
print(init.strip()[:220])
print()
print("CONSEQUENCE: __getattr__ fires ONLY when normal lookup FAILS.")
print("If _engine is a real instance attribute, `view._engine` never reaches")
print("the blocklist at all -- so `view._engine.<any mutation>` bypasses it.")
