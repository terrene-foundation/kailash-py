> **SUPERSEDED — 6 February 2026**
>
> This document was drafted as part of the fair-code/source-available licensing strategy.
> On 6 February 2026, the Board decided to transition to pure Apache 2.0 and donate all
> platform assets to OCEAN Foundation. The Kailash Software License v1.0 was never finalized
> or adopted. See `07-foundation/` and `DECISION-MEMORANDUM.md` for the current strategy.
>
> This document is retained for historical reference only.

# Kailash Software License

## Version 1.0

### Acceptance

By using the Software, You agree to all of the terms and conditions below.

### Definitions

"**Affiliate**" means any entity that controls, is controlled by, or is under
common control with a party, or that acts at the direction of, or for the
benefit of, a party in connection with the subject matter of this License.
"Control" means ownership of more than twenty percent (20%) of the outstanding
voting securities of an entity, the power to direct the management and
policies of an entity, or any arrangement (including through contractual
provisions, variable interest entities, or joint ventures) through which a
party exercises substantial influence over the entity's decisions.

"**Contribution**" means any work of authorship submitted to the Licensor for
inclusion in the Software, including modifications, additions, or deletions.

"**Derivative Work**" means any work that is based on or derived from the
Software, including modifications, translations, adaptations, and extensions.

"**License**" means this Kailash Software License, Version 1.0.

"**Licensed Patents**" means the patent applications and patents identified in
Section 6.4, together with all national and regional phase entries,
continuations, continuations-in-part, divisionals, reissues, reexaminations,
and extensions thereof, and any patents that may issue from such applications,
to the extent owned or controlled by the Licensor.

"**Licensor**" means Terrene Foundation, a company incorporated in Singapore,
and its successors and assigns.

"**Software**" means the Kailash Software Development Kit, including the core
SDK (`kailash`), DataFlow (`kailash-dataflow`), Nexus (`kailash-nexus`), and
Kaizen (`kailash-kaizen`), in Source or Object form, as made available by the
Licensor under this License, including any subset, module, or component thereof
taken individually or in combination.

"**Source form**" means the preferred form for making modifications, including
source code, documentation, and configuration files.

"**Object form**" means any form resulting from mechanical transformation or
translation of Source form, including compiled code, generated documentation,
and packaged distributions.

"**Substantial Additional Functionality**" means functionality that satisfies
ALL of the following criteria: (a) it adds features, capabilities, or
integrations that are not present in the unmodified Software; (b) the added
functionality represents the primary value proposition of the combined work to
its end users, such that the Software serves as a supporting component rather
than the core offering; and (c) a reasonable person skilled in software
development would recognize the combined work as a distinct product or service
from the unmodified Software.

For purposes of criterion (b), the determination shall consider whether end
users would use the combined work primarily for the functionality provided by
the Software, regardless of what additional features are present or how the
combined work is marketed. A combined work in which the Software's
functionality constitutes the majority of the computational work or functional
capability available to end users shall be presumed not to satisfy criterion
(b).

A thin wrapper, user interface layer, configuration framework, or
orchestration layer that primarily exposes, repackages, or provides access to
the Software's existing functionality does not constitute Substantial
Additional Functionality.

"**You**" (or "**Your**") means the individual or Legal Entity exercising
permissions granted by this License. "**Legal Entity**" means the union of the
acting entity and all Affiliates of that entity.

---

### Section 1. Copyright License

The Licensor grants You a non-exclusive, royalty-free, worldwide,
non-sublicensable, non-transferable license to use, copy, distribute, make
available, and prepare Derivative Works of the Software, in each case subject
to the Limitations in Section 2 and the other terms of this License.

A licensee may authorize its employees, contractors, and agents to exercise
rights under this License on the licensee's behalf.

---

### Section 2. Limitations

In the event of any conflict between the permissions in Section 3 and the
Limitations in this Section 2, the Limitations in this Section 2 shall
prevail. The permissions in Section 3 are subject to, and do not override,
limit, or modify, the Limitations in this Section 2.

**2.1 Managed Service Restriction.** You may not provide the Software or any
Derivative Work to third parties as a hosted or managed service, where the
service provides users with access to any of the features or functionality of
the Software. For clarity, the following are examples of prohibited uses under
this Section:

(a) Offering the Software as a "platform-as-a-service," "software-as-a-
service," or "workflow-as-a-service" product, where third-party users
interact with the Software's features through Your infrastructure;

(b) Embedding the Software in a multi-tenant hosted offering where the
Software's workflow engine, database framework, API platform, or AI
agent capabilities constitute any portion of the service's
functionality available to tenants;

(c) Offering an API, command-line interface, or other programmatic access
to the Software's functionality as a commercial service to third
parties;

(d) Deploying the Software as a backend component of a service where the
primary computational work performed on behalf of third-party users is
substantially derived from the Software's functionality, regardless of
the presence of proprietary interface layers, APIs, or intermediaries;

(e) Providing infrastructure, tooling, management services, marketplace
listings, or deployment mechanisms that are specifically designed to
facilitate the deployment and operation of the Software as a service
for third parties, regardless of which party technically obtains or
installs the Software.

For purposes of this Section, "provide" includes facilitating access to the
Software through pre-configured deployments, marketplace listings, managed
infrastructure specifically configured for the Software, or any arrangement
where You profit from third parties' use of the Software's functionality.

You may not authorize, direct, or arrange for a third party to perform on Your
behalf any activity that would, if performed by You directly, violate this
Section 2.1.

This restriction does not apply to using the Software to power internal
operations of Your own business that are not themselves workflow automation,
database management, API platform, or AI agent services, even if those
operations serve Your customers indirectly (for example, using the Software
internally to process customer orders is permitted; offering the Software
itself or its core capabilities as a customer-facing platform is not).

**2.2 Standalone Commercial Distribution Restriction.** You may not sell,
license for a fee, or commercially distribute the Software or any Derivative
Work as a standalone product where the Software constitutes the primary
deliverable, unless such Derivative Work includes Substantial Additional
Functionality as defined in this License.

**2.3 License Key Integrity.** You may not move, change, disable, or
circumvent any license key functionality or licensing enforcement mechanism in
the Software, if any.

**2.4 Notice Preservation.** You may not alter, remove, or obscure any
licensing, copyright, patent, or other notices of the Licensor in the
Software. Any distribution of the Software or Derivative Works must include
a complete, unmodified copy of this License.

**2.5 Compliance Verification.** Upon reasonable written notice (no more than
once per twelve-month period), the Licensor may request, and You shall provide
within thirty (30) days, a written certification describing Your use of the
Software and confirming compliance with this License.

---

### Section 3. Permitted Uses

For avoidance of doubt and subject to the Limitations in Section 2, the
following uses are expressly permitted under this License:

**3.1 Internal Business Use.** Using the Software for the internal operations
of Your organization, including building internal tools, automating business
processes, and developing internal applications, regardless of whether those
operations generate revenue. Internal operations include use by Your
employees, contractors, and agents acting on Your behalf within the scope of
their engagement with You.

**3.2 Component Use.** Using the Software as a component, library, or
dependency within a larger application, system, or product that You develop
and distribute, provided that the larger work constitutes a Derivative Work
with Substantial Additional Functionality beyond the Software itself, and
provided that such use does not violate the Managed Service Restriction in
Section 2.1.

**3.3 Consulting and Professional Services.** Providing consulting,
implementation, customization, deployment, training, and support services to
third parties that involve using, configuring, deploying, or managing the
Software, provided that the Software itself is not offered as a hosted or
managed service in violation of Section 2.1. For clarity, deploying,
configuring, maintaining, and managing the Software on a client's own
infrastructure or cloud account, where the client is the licensee and You act
as the client's agent, does not constitute providing a hosted or managed
service under Section 2.1.

**3.4 Personal, Educational, and Research Use.** Using the Software for
personal projects, academic research, educational purposes, evaluation, and
non-commercial experimentation without restriction.

**3.5 Derivative Works Distribution.** Creating, distributing, and
commercially licensing Derivative Works that include the Software as a
component, provided that such Derivative Works include Substantial Additional
Functionality and comply with all other terms of this License, including the
Limitations in Section 2 and Section 5 (Attribution and Notices).
Distribution of Derivative Works that do not include Substantial Additional
Functionality is not permitted under this License.

For avoidance of doubt, a Derivative Work that includes Substantial Additional
Functionality remains subject to the Limitations in Section 2, including the
Managed Service Restriction and the Standalone Commercial Distribution
Restriction.

---

### Section 4. Contributions

If You submit a Contribution to the Licensor for inclusion in the Software,
You hereby grant the Licensor a perpetual, worldwide, non-exclusive,
royalty-free, irrevocable license to use, copy, modify, prepare derivative
works of, distribute, and sublicense the Contribution, under copyright and
patent claims that You own or control that are necessarily infringed by the
Contribution.

Notwithstanding the above, nothing in this Section supersedes or modifies the
terms of any separate contributor license agreement You may have executed with
the Licensor.

---

### Section 5. Attribution and Notices

**5.1** Any distribution of the Software or Derivative Works must include:
(a) a copy of this License; (b) the NOTICE file, if one is provided with the
Software; and (c) the PATENTS file, if one is provided with the Software.

**5.2** Derivative Works must carry prominent notices, visible to end users
during normal use of the product (such as in an "About" dialog, startup
screen, documentation homepage, or API response headers), stating that the
product includes or is based on the Kailash SDK by Terrene Foundation, and
identifying the nature of the modifications made.

**5.3** You may not use the trade names, trademarks, service marks, or product
names of the Licensor (including "Kailash," "DataFlow," "Nexus," and "Kaizen")
or names confusingly similar thereto, to endorse or promote products derived
from the Software without prior written consent from the Licensor, except as
required for reasonable and customary use in describing the origin of the
Software. You may not present a Derivative Work in a manner that could
reasonably lead end users to believe it is an official product of, or endorsed
by, the Licensor.

---

### Section 6. Patent Grant

**6.1 Grant of Patent License.** Subject to the terms and conditions of this
License, the Licensor hereby grants to You a perpetual, worldwide,
non-exclusive, royalty-free patent license under the Licensed Patents to make,
have made, use, offer to sell, sell, import, and otherwise transfer the
Software, where such license applies only to those patent claims that are
necessarily infringed by the Software as distributed by the Licensor, including
any subset, module, or component thereof.

**6.2 Defensive Termination.** If You (or any of Your Affiliates) initiate
patent litigation or proceedings (including, without limitation, filing a
declaratory judgment action, cross-claim, counterclaim, inter partes review,
post-grant review, reexamination, opposition, invalidation action, or any
administrative or judicial proceeding) against the Licensor or any contributor
to the Software, alleging that the Software as distributed by the Licensor
constitutes direct or contributory patent infringement, or challenging the
validity, enforceability, or scope of any Licensed Patent, then:

(a) The patent license granted to You under Section 6.1 shall terminate
immediately as of the date such litigation or proceeding is filed; and

(b) Your copyright license under Section 1 shall also terminate
immediately as of the date such litigation or proceeding is filed.

For the purposes of this Section, "initiate" includes causing, directing,
funding, or materially supporting the initiation of such litigation or
proceeding by any third party.

No cure period applies to termination under this Section 6.2.

**6.3 Patent License Conditioned on Material Compliance.** The patent license
granted under Section 6.1 is expressly conditioned on Your material compliance
with the Limitations in Section 2 and the terms of this Section 6. If Your
rights under this License terminate permanently under Section 7.4 for
violations of Section 2 (Limitations), the patent license granted under
Section 6.1 simultaneously and automatically terminates. Temporary termination
under Section 7.1 for violations of provisions other than Section 2 does not
affect the patent license, provided that You cure any such violation within
the applicable cure period under Section 7.2. Upon reinstatement of Your
rights under Section 7.3, any temporarily suspended patent license is also
reinstated.

**6.4 Patent Identification.** The Licensed Patents are:

(a) **PCT International Application No. PCT/SG2024/050503**, titled
"A System and Method for Development of a Service Application on an
Application Development Platform," with priority date 14 August 2023,
and all national and regional phase entries thereof, including filings
at the Intellectual Property Office of Singapore (IPOS), the United
States Patent and Trademark Office (USPTO), and the China National
Intellectual Property Administration (CNIPA), and any patents that may
issue from such applications;

(b) **Singapore Application Ref. P251088SG**, titled "Method and System
for Orchestrating Artificial Intelligence Workflow," with priority
date 7 October 2025, and any PCT application, national phase entry,
continuation, or divisional application claiming priority therefrom,
and any patents that may issue from such applications;

(c) Any other patent or patent application hereafter owned or controlled
by the Licensor that is necessarily infringed by the Software as
distributed by the Licensor at the time such patent is filed or
acquired.

**6.5 Scope of Patent Grant.** The patent license granted under Section 6.1:

(a) Applies to patent claims that are necessarily infringed by the
functionality of the Software as provided by the Licensor, including
normal configuration, parameterization, and use through the Software's
published APIs and intended interfaces;

(b) Extends to Derivative Works to the extent such works necessarily
infringe the Licensed Patents by incorporating functionality of
the Software that is substantially as provided by the Licensor;

(c) Does not extend to patent claims that are infringed solely by
modifications made by You or third parties that alter the patented
method or process, or by combinations of the Software with other
software, hardware, or technology not provided by the Licensor, where
the infringement would not occur but for such modification or
combination;

(d) Does not extend to uses of the Software that directly and specifically
violate the Managed Service Restriction in Section 2.1 or the
Standalone Commercial Distribution Restriction in Section 2.2.

**6.6 No Implied Licenses.** Except as expressly stated in this Section 6,
no other patent licenses are granted by the Licensor, whether by implication,
estoppel, or otherwise.

**6.7 Patent Assignment Covenant.** Any assignment, transfer, or sale of the
Licensed Patents by the Licensor shall be subject to the patent license
granted herein. The Licensor shall ensure that any assignee or transferee of
the Licensed Patents is bound by the terms of this Section 6 and honors the
patent license granted to licensees who are in compliance with this License.

**6.8 Patent Exhaustion.** The patent license granted herein does not
constitute an authorized sale for purposes of patent exhaustion doctrine,
except to the extent that You distribute the Software in full compliance with
all terms of this License.

---

### Section 7. Termination

**7.1 Automatic Termination.** Your rights under this License will terminate
automatically if You fail to comply with any of its terms.

**7.2 Notice and Cure.** If the Licensor provides You with notice of a
violation, Your rights under this License will be reinstated provided that:

(a) You cure the violation within thirty (30) calendar days of receiving
the notice (or ten (10) calendar days for violations of Section 2.1
or Section 2.2, which shall require the complete cessation of the
prohibited activity); and

(b) You provide the Licensor with written confirmation that the violation
has been cured.

**7.3 Reinstatement.** Upon satisfaction of the conditions in Section 7.2,
Your rights under this License are reinstated from the date of cure.
Reinstatement does not waive, release, or affect the Licensor's right to seek
damages, injunctive relief, or equitable remedies for the period during which
the violation occurred.

**7.4 Subsequent Violations.** If the Licensor has previously provided You
with notice of a violation of Section 2 (Limitations) and You commit a
subsequent willful violation of Section 2, Your rights under this License
(including the patent license under Section 6) terminate permanently and may
not be reinstated. For purposes of this Section, a "subsequent violation"
includes violations by any entity that is a successor, assignee, or
transferee of You, or any entity formed or acquired primarily for the purpose
of avoiding the consequences of this Section. After twenty-four (24) months
from permanent termination, You may request reinstatement in writing, which
the Licensor shall not unreasonably withhold if You demonstrate that the
circumstances giving rise to the violation have been permanently remedied.

**7.5 Survival.** Sections 6.2 (Defensive Termination), 6.7 (Patent
Assignment Covenant), 8 (Disclaimer of Warranty), 9 (Limitation of Liability),
and this Section 7.5 survive termination of this License.

**7.6 Exception for Patent Proceedings.** Notwithstanding Sections 7.2 and
7.3, termination under Section 6.2 (Defensive Termination for patent
litigation or validity challenges) is immediate and permanent. No cure period
or reinstatement applies to termination triggered by Section 6.2.

**7.7 Equitable Relief.** You acknowledge that any breach of Section 2 may
cause irreparable injury to the Licensor for which monetary damages would be
an inadequate remedy. The Licensor shall be entitled to seek equitable relief,
including injunction and specific performance, in addition to all other
remedies available at law or in equity.

**7.8 Enforcement Rights.** Nothing in this License shall limit the Licensor's
right to seek damages, injunctive relief, or other remedies for breach of
Section 2 (Limitations), Section 5 (Attribution and Notices), or unauthorized
use of the Software.

---

### Section 8. Disclaimer of Warranty

THE SOFTWARE IS PROVIDED "AS IS," WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT. THE LICENSOR
DOES NOT WARRANT THAT THE SOFTWARE WILL BE UNINTERRUPTED, ERROR-FREE, OR
FREE OF HARMFUL COMPONENTS. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE
OF THE SOFTWARE IS WITH YOU.

---

### Section 9. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL THE
LICENSOR OR ANY CONTRIBUTOR BE LIABLE TO YOU FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING BUT NOT
LIMITED TO PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES, LOSS OF USE, DATA,
OR PROFITS, OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF OR INABILITY
TO USE THE SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

---

### Section 10. General

**10.1 Entire Agreement.** This License constitutes the entire agreement
between the Licensor and You with respect to the Software and supersedes all
prior or contemporaneous oral or written communications, proposals, and
representations with respect to the Software. This License does not supersede
or modify the terms of any separate enterprise license agreement, contributor
license agreement, or other written agreement executed between You and the
Licensor.

**10.2 Severability.** If any provision of this License is held to be
unenforceable or invalid, that provision will be modified to the minimum
extent necessary to make it enforceable, and the remaining provisions of this
License will continue in full force and effect.

**10.3 Waiver.** No failure or delay by the Licensor in exercising any right
under this License shall constitute a waiver of that right, nor shall any
single or partial exercise of any right preclude any further exercise of that
right or any other right.

**10.4 Assignment.** You may not assign or transfer this License or any rights
or obligations under it without the Licensor's prior written consent, except
that this License shall automatically transfer to any successor entity in
connection with a merger, acquisition, or sale of all or substantially all of
Your assets, provided that the successor agrees to be bound by all terms of
this License. The Licensor may assign this License in connection with a
merger, acquisition, corporate reorganization, or sale of all or substantially
all of its assets, subject to Section 6.7.

**10.5 Governing Law.** This License shall be governed by and construed in
accordance with the laws of Singapore, without regard to its conflict of laws
provisions. Any dispute arising under this License shall be subject to the
exclusive jurisdiction of the courts of Singapore, except that the Licensor
may seek injunctive or other equitable relief in any court of competent
jurisdiction.

**10.6 No Agency.** Nothing in this License creates a partnership, joint
venture, agency, or employment relationship between You and the Licensor.

**10.7 Export Compliance.** You are responsible for complying with all
applicable export and import laws and regulations in Your use and distribution
of the Software.

**10.8 Government Use.** If the Software is acquired by or on behalf of the
United States government, the Software is "commercial computer software" and
"commercial computer software documentation" as those terms are defined in
48 C.F.R. 2.101, and the government's rights in the Software are limited to
those rights granted under this License.

**10.9 Good Faith.** The Licensor shall exercise its rights under this License
in good faith and shall not use ambiguous terms to impose unreasonable
restrictions on uses that are consistent with the purpose and intent of this
License. Before providing notice of violation under Section 7.2, the Licensor
shall make reasonable efforts to engage in good faith discussion with You to
resolve any ambiguity regarding compliance.

**10.10 Enterprise Licensing.** For enterprise license agreements including
patent indemnification, hosted service rights, custom support terms, and
additional commercial rights, contact the Licensor at info@terrene.foundation.

---

### Section 11. How to Apply This License

To apply this License to your distribution of the Software, include the
following notice in source files:

```
Copyright [year] Terrene Foundation

Licensed under the Kailash Software License, Version 1.0 (the "License");
you may not use this file except in compliance with the License. You may
obtain a copy of the License at

    https://github.com/terrene-foundation/kailash-py/blob/main/LICENSE

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.
```

---

**Kailash Software License, Version 1.0**

Copyright 2025-2026 Terrene Foundation All rights reserved.
