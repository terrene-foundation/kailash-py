# DISCOVERY: Fabric Engine Confirmed Operational — With Gaps

Treasury Fabric integration testing (42 loans, 22 active, 7 currencies, real production data) confirmed:

- Materialized products work correctly
- Virtual products broken (#245 — serving layer returns data:None)
- dev_mode skips pre-warming (#248)
- 12/12 adapter tests pass
- Consumer adapters validated with 6 real transforms (treasury, cash_reporting, mcm, simulations, chat, loans_by_country)

This resolves red team M1 (Fabric Engine operational status unknown). PR 4C (consumer adapters) can proceed — only needs materialized products + serving layer, which work. PR 5A (#245) must land to unblock virtual product usage.
