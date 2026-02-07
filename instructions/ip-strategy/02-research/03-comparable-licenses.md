> **HISTORICAL DOCUMENT — RESEARCH**
>
> This research was conducted as part of the IP strategy development process (February 2026).
> The research informed the final decision to adopt pure Apache 2.0 rather than a custom
> license. On 6 February 2026, the Board decided on unconditional Apache 2.0 donation to
> OCEAN Foundation. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 03 - Comparable License Analysis

## Document Purpose

Side-by-side analysis of fair-code compatible licenses to determine the best fit for Kailash SDK.

## License Comparison Matrix

| Feature                  | Commons Clause  | SUL            | ELv2           | BSL                       | SSPL                        |
| ------------------------ | --------------- | -------------- | -------------- | ------------------------- | --------------------------- |
| Source available         | Yes             | Yes            | Yes            | Yes                       | Yes                         |
| Internal use             | Free            | Free           | Free           | Free                      | Free                        |
| Personal/educational use | Free            | Free           | Free           | Free                      | Free                        |
| Modify & extend          | Yes             | Yes            | Yes            | Yes                       | Yes                         |
| Consulting services      | Restricted      | Free           | Free           | Free                      | Free                        |
| Component in larger app  | Depends         | Depends        | Yes            | Yes                       | Depends                     |
| Standalone sale          | No              | No             | No             | No                        | No                          |
| Hosted/managed service   | No              | No             | No             | No                        | Must open-source full stack |
| Competing product        | Depends         | No             | No             | Time-limited              | Depends                     |
| Converts to open source  | No              | No             | No             | Yes (time delay)          | No                          |
| faircode.io listed       | Yes             | Yes            | Yes            | Yes                       | Yes                         |
| Patent clause            | Depends on base | No             | No             | No                        | No                          |
| Legal precedent          | Moderate        | Low (n8n only) | High (Elastic) | High (MariaDB, HashiCorp) | Moderate (MongoDB)          |
| Copyleft element         | No              | No             | No             | No                        | Yes (strong)                |

## Detailed Analysis Per License

### Commons Clause + Apache 2.0

**How it works**: Appends to an existing OSI license. Adds: "The Software is provided to you by the Licensor under the License, as defined below, subject to the following condition: Without limiting other conditions in the License, the grant of rights under the License will not include, and the License does not grant to you, the right to Sell the Software."

**Pros for Kailash:**

- Closest to current license structure (Apache 2.0 + restriction)
- Minimal change from current terms
- Well-understood in the market

**Cons for Kailash:**

- "Sell" is ambiguous (same problem n8n had)
- Doesn't explicitly address hosted services
- No patent clause (relies on Apache 2.0's patent grant)
- n8n already proved this model is inadequate

### Sustainable Use License (SUL)

**How it works**: Standalone license. Permits use for internal business, personal, or non-commercial purposes. Distribution only free of charge for non-commercial use.

**Pros for Kailash:**

- Battle-tested by n8n (closest comparable product)
- Explicitly permits consulting services
- Clear, unambiguous language
- faircode.io recognized
- Strong community acceptance

**Cons for Kailash:**

- "Internal business purposes" may not clearly cover SDK-as-component use
- No patent grant clause (would need to be added)
- No explicit hosted service restriction (covered indirectly)
- Single-company precedent (only n8n)

### Elastic License 2.0 (ELv2)

**How it works**: Standalone license with two specific restrictions: (1) Cannot provide the software as a managed service, (2) Cannot circumvent license key functionality.

**Pros for Kailash:**

- Highest legal precedent (Elastic, a public company, relies on it)
- Explicitly addresses the managed service problem
- Simple, clear language
- Very permissive for all non-competing uses
- Component use explicitly permitted

**Cons for Kailash:**

- License key restriction clause is irrelevant to Kailash
- No patent grant clause (would need to be added)
- Elastic's specific context (search engine) differs from SDK

### Business Source License (BSL)

**How it works**: Restricts certain uses for a defined period, after which the code converts to a specified open-source license (e.g., Apache 2.0). The "Additional Use Grant" defines what's allowed during the restriction period.

**Pros for Kailash:**

- Highest overall legal precedent (MariaDB, HashiCorp, CockroachDB)
- Time-delayed open source creates goodwill
- Very flexible (Additional Use Grant is customizable)
- Strong community understanding

**Cons for Kailash:**

- Complexity of managing the time conversion
- Code eventually becomes fully open source (may not align with long-term strategy)
- Requires defining a "Change Date" and "Change License"
- No patent clause

### Server Side Public License (SSPL)

**How it works**: Modified AGPL. If you offer the software as a service, you must release the source code for your entire service stack (including management, monitoring, etc.).

**Pros for Kailash:**

- Strongest protection against cloud provider exploitation
- MongoDB's track record proves it works

**Cons for Kailash:**

- Overly aggressive for an SDK (requires service stack disclosure)
- Controversial in the community
- OSI explicitly rejected it as open source
- Would deter enterprise adoption of the SDK
- Not appropriate for component/library use cases

## Recommendation Matrix for Kailash

Scoring each license (1-5, 5 = best fit):

| Criterion                  | Weight | Commons Clause | SUL      | ELv2     | BSL      | SSPL     |
| -------------------------- | ------ | -------------- | -------- | -------- | -------- | -------- |
| Clarity of terms           | 25%    | 2              | 4        | 5        | 4        | 3        |
| SDK/component use          | 20%    | 3              | 3        | 5        | 4        | 1        |
| Hosted service protection  | 15%    | 2              | 3        | 5        | 4        | 5        |
| Legal precedent            | 15%    | 3              | 2        | 5        | 5        | 3        |
| Community acceptance       | 10%    | 3              | 4        | 4        | 4        | 2        |
| Transition ease            | 10%    | 5              | 3        | 3        | 2        | 1        |
| Patent grant compatibility | 5%     | 4              | 3        | 3        | 3        | 2        |
| **Weighted Score**         |        | **2.85**       | **3.25** | **4.55** | **3.85** | **2.50** |

## Top Recommendation

**Elastic License 2.0 (ELv2)** scores highest for Kailash because:

1. It explicitly permits component/SDK use (critical for Kailash's adoption model)
2. It explicitly addresses the managed service threat
3. It has the strongest legal precedent among a public company
4. It can be augmented with a patent grant clause
5. Its language is simple and unambiguous

**Alternative: Sustainable Use License (SUL)** if the priority is alignment with n8n's workflow automation community and the fair-code movement specifically. Would need modifications for SDK-as-component use case.

**Hybrid option: Custom "Kailash Software License"** modeled primarily on ELv2 with:

- SUL's explicit consulting permission
- Added patent grant clause with defensive termination
- Explicit SDK-as-component permission

## Sources

- [Elastic License 2.0 FAQ](https://www.elastic.co/licensing/elastic-license/faq)
- [MariaDB BSL](https://mariadb.com/bsl-faq-mariadb/)
- [MongoDB SSPL FAQ](https://www.mongodb.com/licensing/server-side-public-license/faq)
- [n8n SUL](https://docs.n8n.io/sustainable-use-license/)
- [Commons Clause](https://commonsclause.com/)
