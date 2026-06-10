"""
Privacy-aware RAG nodes.

This module provides best-effort privacy hygiene helpers for RAG pipelines:
- Regex-based PII detection and redaction (email, phone, SSN, credit-card,
  IP, simple name/date patterns) — best-effort, pattern-based, NOT a formal
  guarantee
- Query generalization/anonymization (term replacement + word dropout)
- Compliance-aware retrieval (consent validation, jurisdiction filtering,
  classification-based truncation) — see ComplianceRAGNode

These are operational privacy hygiene measures, not cryptographic guarantees.
The module does NOT implement differential privacy, homomorphic encryption,
or secure multi-party computation; no such cryptographic mechanism is present
in the code.
"""

import hashlib
import logging
import random
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node

# Registering imports (mirrors realtime.py #1120): referenced only by STRING via
# `builder.add_node("PythonCodeNode", ...)` / consumed by security workflows; the
# import runs the `@register_node` side effect that populates the registry. Do NOT
# drop to satisfy an unused-import linter.
from kailash.nodes.code.python import PythonCodeNode  # noqa: F401
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.nodes.security.credential_manager import (  # noqa: F401
    CredentialManagerNode,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


@register_node()
class PrivacyPreservingRAGNode(WorkflowNode):
    """
    Privacy-aware RAG node — regex PII redaction + query generalization.

    The node's real, useful capability is **best-effort, pattern-based PII
    redaction**: it detects and replaces email/phone/SSN/credit-card/IP and
    simple name/date patterns with stable hashed sentinels before retrieval,
    and generalizes/anonymizes queries (term replacement + random word
    dropout). It also writes a structured audit record of what hygiene steps
    ran.

    This is operational privacy hygiene, NOT a formal privacy guarantee.
    Regex redaction is best-effort and will miss PII it has no pattern for.

    NOTE on the score perturbation step: the node optionally adds random
    noise to retrieval scores. This is NOT differential privacy — there is
    no privacy-budget accounting, no composition tracking across queries,
    and the noise is drawn from a non-cryptographic PRNG. Do NOT rely on it
    for any privacy claim; it is optional score perturbation only.

    When to use:
    - Best for: stripping obvious PII (emails, phone numbers, SSNs) from
      free-text before it reaches a retrieval/LLM stage
    - Not ideal for: any setting requiring a provable privacy guarantee, or
      PII forms the regex patterns do not cover
    - Performance: small overhead for the regex + generalization passes

    Capabilities (what the code actually does):
    - Best-effort regex PII detection + redaction with stable hashed sentinels
    - Query generalization/anonymization (term replacement + word dropout)
    - Optional retrieval-score perturbation (NOT a privacy guarantee)
    - k-anonymity-style result clustering of similar documents
    - Structured audit record of which hygiene steps ran

    Example:
        private_rag = PrivacyPreservingRAGNode(
            score_noise=1.0,     # optional retrieval-score perturbation scale
            redact_pii=True,
            anonymize_queries=True
        )

        # This is a WorkflowNode: the wrapped inner workflow is fed via the
        # `inputs={node_id: {param: value}}` mapping (each codegen stage reads
        # the external inputs it needs). The free-text query reaches the PII
        # detector as `text`; the executor + audit stages read query/documents/
        # consent directly.
        query = "What is John Smith's diagnosis based on symptoms X, Y, Z?"
        result = private_rag.execute(
            inputs={
                "pii_detector": {"text": query},
                "query_anonymizer": {"query": query},
                "private_rag_executor": {"query": query, "documents": medical_records},
                "audit_logger": {
                    "query": query,
                    "user_consent": {"data_usage": True, "retention_days": 7},
                },
            }
        )

        # The terminal `result_formatter` stage publishes its output under the
        # auto-mapped `result_formatter_result` key:
        privacy_results = result["result_formatter_result"][
            "privacy_preserving_results"
        ]
        # privacy_results["results"]        -> regex-detectable PII redacted
        # privacy_results["privacy_report"] -> which hygiene steps actually ran
        # privacy_results["audit_record"]   -> structured audit of the steps
        # Query logged as: "What is [PERSON_NAME_<hash>]'s diagnosis ...?"

    Parameters:
        score_noise: Scale for optional retrieval-score perturbation. Larger
            = more perturbation. This is NOT a differential-privacy epsilon
            and provides no formal guarantee.
        redact_pii: Detect and redact regex-matchable PII (best-effort)
        anonymize_queries: Generalize/anonymize queries before processing
        audit_logging: Write a structured audit record of hygiene steps

    Returns:
        results: Results with regex-detectable PII redacted
        privacy_report: Which hygiene steps were applied
        audit_record: Audit information about the hygiene steps
        confidence_bounds: Score uncertainty introduced by perturbation
    """

    def __init__(
        self,
        name: str = "privacy_preserving_rag",
        score_noise: float = 1.0,
        redact_pii: bool = True,
        anonymize_queries: bool = True,
        audit_logging: bool = True,
    ):
        self.score_noise = score_noise
        self.redact_pii = redact_pii
        self.anonymize_queries = anonymize_queries
        self.audit_logging = audit_logging
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create privacy-preserving RAG workflow"""
        builder = WorkflowBuilder()
        # The audit_logger node is wired only when self.audit_logging is True;
        # initialize the id to None so the closure-parity wiring branch below
        # is statically reachable even when audit_logging is False.
        audit_logger_id: Optional[str] = None

        # PII detector and redactor
        pii_detector_id = builder.add_node(
            "PythonCodeNode",
            node_id="pii_detector",
            config={
                "code": f"""
import re
import hashlib
from datetime import datetime

def detect_and_redact_pii(text, redact={self.redact_pii}):
    '''Detect and redact personally identifiable information'''

    original_text = text
    redacted_text = text
    pii_found = {{}}

    if not redact:
        return {{
            "processed_text": text,
            "pii_found": {{}},
            "redaction_applied": False
        }}

    # PII patterns
    patterns = {{
        "email": r'\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{{2,}}\\b',
        "phone": r'\\b\\d{{3}}[-.]?\\d{{3}}[-.]?\\d{{4}}\\b',
        "ssn": r'\\b\\d{{3}}-\\d{{2}}-\\d{{4}}\\b',
        "credit_card": r'\\b\\d{{4}}[\\s-]?\\d{{4}}[\\s-]?\\d{{4}}[\\s-]?\\d{{4}}\\b',
        "ip_address": r'\\b(?:[0-9]{{1,3}}\\.{{3}}[0-9]{{1,3}})\\b',
        "person_name": r'\\b[A-Z][a-z]+ [A-Z][a-z]+\\b',  # Simple name pattern
        # Non-capturing groups: re.findall returns the WHOLE match string,
        # not group tuples. Capturing-group form crashed `match.encode()`
        # below (F9 #1112).
        "date_of_birth": r'\\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/(?:19|20)\\d{{2}}\\b'
    }}

    # Detect and redact each PII type
    for pii_type, pattern in patterns.items():
        matches = re.findall(pattern, redacted_text)
        if matches:
            pii_found[pii_type] = []
            for match in matches:
                # Short fingerprint for audit correlation; NOT a secure or
                # irreversible hash (8 hex chars of SHA-256 is brute-forceable
                # for low-entropy PII like phone numbers).
                hash_value = hashlib.sha256(match.encode()).hexdigest()[:8]
                pii_found[pii_type].append({{
                    "hash": hash_value,
                    "type": pii_type,
                    "length": len(match)
                }})

                # Redact with type indicator
                replacement = f"[{{pii_type.upper()}}_{{hash_value}}]"
                redacted_text = redacted_text.replace(match, replacement)

    # Additional sensitive data patterns
    sensitive_terms = ["diagnosis", "medication", "treatment", "salary", "account"]
    for term in sensitive_terms:
        if term in redacted_text.lower():
            # Partially redact sensitive terms
            pattern = re.compile(f'{{term}}[:\\s]*([^,.;]+)', re.IGNORECASE)
            redacted_text = pattern.sub(f'{{term}}: [REDACTED]', redacted_text)

    # F9 #1113: function MUST return the redaction dict; the prior
    # `result = {{...}}` bound a function-scope local that was never
    # returned, dropping the redact-True branch's output to None.
    return {{
        "processed_text": redacted_text,
        "pii_found": pii_found,
        "redaction_applied": original_text != redacted_text,
        "redaction_count": sum(len(items) for items in pii_found.values())
    }}

# F9 #1114: PythonCodeNode reads `result` from module scope; the codegen
# MUST execute the function at module scope so the outbound port carries
# the redaction dict (the function was previously defined but never called).
result = detect_and_redact_pii(text, redact={self.redact_pii})
# Drop the helper so PythonCodeNode's output-validation gate (which
# JSON-serializes every binding) sees only the JSON-safe `result`.
del detect_and_redact_pii
"""
            },
        )

        # Query anonymizer
        query_anonymizer_id = builder.add_node(
            "PythonCodeNode",
            node_id="query_anonymizer",
            config={
                "code": f"""
def anonymize_query(query, pii_info, anonymize={self.anonymize_queries}):
    '''Anonymize and generalize queries for privacy'''
    # F9 #1118 sibling: import inside the function body. PythonCodeNode
    # passes separate (globals, locals) to exec(), so a module-scope import
    # binds into LOCAL namespace and is invisible to this function's closure.
    # The generalization-rule regex pass + word-dropout RNG below need these.
    import re
    import random

    if not anonymize:
        return {{
            "anonymized_query": query,
            "anonymization_applied": False,
            "generalization_level": 0
        }}

    anonymized = query
    generalizations = []

    # Use PII detection results
    if pii_info.get("redaction_applied"):
        anonymized = pii_info.get("processed_text", query)
        generalizations.append("pii_redacted")

    # Generalize specific terms
    generalization_rules = {{
        # Medical
        "cancer|tumor|carcinoma": "oncological condition",
        "diabetes|insulin": "metabolic condition",
        "depression|anxiety": "mental health condition",

        # Financial
        "\\$\\d+": "monetary amount",
        "credit score \\d+": "credit score",
        "income|salary|wage": "compensation",

        # Location
        "\\b\\d{{5}}\\b": "zipcode",
        "street|avenue|road": "address",

        # Time
        "january|february|march|april|may|june|july|august|september|october|november|december": "month",
        "monday|tuesday|wednesday|thursday|friday|saturday|sunday": "day"
    }}

    for pattern, replacement in generalization_rules.items():
        if re.search(pattern, anonymized, re.IGNORECASE):
            anonymized = re.sub(pattern, replacement, anonymized, flags=re.IGNORECASE)
            generalizations.append(f"{{pattern}}->{{replacement}}")

    # Add query perturbation for additional privacy
    if len(anonymized.split()) > 5:
        words = anonymized.split()
        # Randomly drop 10% of non-essential words
        essential_words = set(["what", "how", "why", "when", "where", "who", "is", "are", "the"])
        words_to_keep = []
        for word in words:
            if word.lower() in essential_words or random.random() > 0.1:
                words_to_keep.append(word)
        anonymized = " ".join(words_to_keep)
        generalizations.append("word_dropout")

    # F9 #1117: function MUST return its dict; the prior `result = {{...}}`
    # bound a function-scope local that was never returned, so the module
    # never saw the anonymization output.
    return {{
        "anonymized_query": anonymized,
        "anonymization_applied": True,
        "generalization_level": len(generalizations),
        "techniques_used": generalizations
    }}

# F9 #1117: module-scope call so PythonCodeNode's outbound port carries the
# anonymization dict (the function was previously defined but never called).
# `query` is an external workflow input; `pii_info` is wired from
# pii_detector.result. `del` the helper so the output gate sees only `result`.
result = anonymize_query(query, pii_info, anonymize={self.anonymize_queries})
del anonymize_query
"""
            },
        )

        # Optional retrieval-score perturbation.
        # NOT differential privacy: there is no privacy-budget accounting, no
        # composition tracking across queries, and the noise is drawn from a
        # non-cryptographic PRNG. This perturbs scores so the exact retrieval
        # ranking is less directly readable; it provides NO formal guarantee.
        dp_noise_id = builder.add_node(
            "PythonCodeNode",
            node_id="dp_noise_injector",
            config={
                "code": f"""
def perturb_scores(scores, noise_scale={self.score_noise}):
    '''Add random noise to retrieval scores.

    NOT a differential-privacy mechanism and NOT a formal privacy guarantee.
    Optional score perturbation only: noise is drawn from a non-cryptographic
    PRNG with no privacy-budget accounting or cross-query composition.
    '''
    # F9 #1118 sibling: import inside the function body. PythonCodeNode passes
    # separate (globals, locals) to exec(), so module-scope imports are
    # invisible to this function's closure.
    import math
    import random

    if noise_scale <= 0 or not scores:
        # No perturbation requested, OR no retrieval scores to perturb (an
        # empty retrieval set must NOT divide-by-zero on the avg below).
        return {{
            "dp_scores": list(scores),
            "noise_added": False,
            "avg_noise": 0.0
        }}

    noisy_scores = []
    noise_values = []

    for score in scores:
        # Draw a symmetric noise sample and add it to the score.
        u = random.random() - 0.5
        noise = -noise_scale * math.copysign(1, u) * math.log(1 - 2 * abs(u))

        # Clip to valid range [0, 1]
        noisy_score = max(0, min(1, score + noise))

        noisy_scores.append(noisy_score)
        noise_values.append(noise)

    # F9 #1117: function MUST return its dict; the prior `result = {{...}}`
    # bound a function-scope local that was never returned, so the perturbed
    # scores never reached the module-scope output.
    return {{
        "dp_scores": noisy_scores,
        "noise_added": True,
        "avg_noise": sum(abs(n) for n in noise_values) / len(noise_values)
    }}

# F9 #1117: module-scope call so PythonCodeNode publishes the perturbation
# dict. The wire from private_rag_executor.result carries that node's whole
# returned dict {{"retrieval_results": {{documents, scores, query_used,
# privacy_applied}}}}, so unwrap the inner score LIST before perturbing (a bare
# dict would iterate keys). Tolerate either the wrapped or a bare-list shape.
if isinstance(scores, dict):
    _retrieval_scores = scores.get("retrieval_results", {{}}).get("scores", [])
else:
    _retrieval_scores = scores
result = perturb_scores(_retrieval_scores, noise_scale={self.score_noise})
del perturb_scores, _retrieval_scores
"""
            },
        )

        # Secure aggregator
        secure_aggregator_id = builder.add_node(
            "PythonCodeNode",
            node_id="secure_aggregator",
            config={
                "code": """
def aggregate_results(retrieval_results, dp_info):
    '''Group similar documents into k-anonymity-style clusters.

    This is content-similarity clustering (group documents whose content
    prefix hashes match, surface clusters of size >= 2 as an aggregate). It
    is NOT cryptographic secure aggregation / secure multi-party computation
    and provides no formal privacy guarantee.
    '''
    # F9 #1118 sibling: import inside the function body. PythonCodeNode passes
    # separate (globals, locals) to exec(), so a module-scope import is
    # invisible to this function's closure. The content-prefix clustering
    # below hashes document prefixes via hashlib.
    import hashlib

    # The wire from private_rag_executor.result carries that node's whole
    # returned dict {"retrieval_results": {documents, scores, ...}}; unwrap the
    # inner retrieval payload. Tolerate a pre-unwrapped dict too.
    inner = retrieval_results.get("retrieval_results", retrieval_results)

    documents = inner.get("documents", [])
    dp_scores = dp_info.get("dp_scores", [])

    # Group similar documents into clusters.
    aggregated_results = []

    # Group similar documents to prevent inference attacks
    doc_clusters = {}

    for i, (doc, score) in enumerate(zip(documents, dp_scores)):
        # Simple clustering by content similarity
        content_hash = hashlib.sha256(doc.get("content", "")[:100].encode()).hexdigest()[:4]
        cluster_key = f"cluster_{content_hash}"

        if cluster_key not in doc_clusters:
            doc_clusters[cluster_key] = []

        doc_clusters[cluster_key].append({
            "doc": doc,
            "score": score,
            "index": i
        })

    # Aggregate clusters
    for cluster_id, cluster_docs in doc_clusters.items():
        if len(cluster_docs) >= 2:  # k-anonymity-style grouping with k=2
            # Average scores in cluster
            avg_score = sum(d["score"] for d in cluster_docs) / len(cluster_docs)

            # Real aggregation occurred: >=2 documents collapsed into one result.
            aggregated_results.append({
                "content": f"[Aggregated from {len(cluster_docs)} similar documents]",
                "score": avg_score,
                "cluster_size": len(cluster_docs),
                "aggregated": True  # k>=2 grouping actually happened
            })
        else:
            # Single document - NO aggregation, only a length truncation.
            # Do NOT claim protection here: the doc stands alone (k=1).
            doc_info = cluster_docs[0]
            aggregated_results.append({
                "content": doc_info["doc"].get("content", "")[:200] + "...",  # Truncate
                "score": doc_info["score"],
                "cluster_size": 1,
                "aggregated": False  # k=1: truncated only, not aggregated
            })

    # Sort by score
    aggregated_results.sort(key=lambda x: x["score"], reverse=True)

    # F9 #1117: function MUST return its dict; the prior `result = {...}`
    # bound a function-scope local that was never returned, so the clustered
    # results never reached the module-scope output.
    return {
        "secure_results": aggregated_results[:5],  # Limit results
        "aggregation_method": "k-anonymity clustering",
        "k_value": 2,
        "clusters_formed": len(doc_clusters)
    }

# F9 #1117: module-scope call so PythonCodeNode publishes the aggregation
# dict. `retrieval_results` is wired from private_rag_executor.retrieval_results;
# `dp_info` is wired from dp_noise_injector.result. `del` the helper so the
# output gate sees only `result`.
result = aggregate_results(retrieval_results, dp_info)
del aggregate_results
"""
            },
        )

        # Privacy-aware RAG executor
        private_rag_executor_id = builder.add_node(
            "PythonCodeNode",
            node_id="private_rag_executor",
            config={
                "code": """
# Execute RAG over the (possibly) anonymized query.
anonymized_query = anonymized_query_info.get("anonymized_query", query)
documents = documents

# Whether any query-side hygiene actually ran upstream. The anonymizer sets
# anonymization_applied (which also covers PII redaction folded into the query).
# Derive the flag — do NOT hardcode True on the redact_pii=False path.
privacy_applied = bool(anonymized_query_info.get("anonymization_applied", False))

# Simple retrieval (would use actual RAG in production)
query_words = set(anonymized_query.lower().split())
scored_docs = []

for doc in documents[:100]:  # Limit for privacy
    content = doc.get("content", "").lower()
    doc_words = set(content.split())

    # Calculate similarity
    if query_words:
        overlap = len(query_words & doc_words)
        score = overlap / len(query_words)
    else:
        score = 0.0

    if score > 0:
        scored_docs.append({
            "document": doc,
            "score": score
        })

# Sort by score
scored_docs.sort(key=lambda x: x["score"], reverse=True)

# Extract top results
top_docs = scored_docs[:10]

result = {
    "retrieval_results": {
        "documents": [d["document"] for d in top_docs],
        "scores": [d["score"] for d in top_docs],
        "query_used": anonymized_query,
        "privacy_applied": privacy_applied
    }
}
"""
            },
        )

        # Audit logger
        if self.audit_logging:
            audit_logger_id = builder.add_node(
                "PythonCodeNode",
                node_id="audit_logger",
                config={
                    "code": """
def create_audit_record(query, pii_info, anonymization_info, dp_info, results, user_consent):
    '''Create privacy audit record for compliance'''
    # F9 #1118 sibling: import inside the function body. PythonCodeNode passes
    # separate (globals, locals) to exec(), so a module-scope import binds into
    # LOCAL namespace and is invisible to this function's closure
    # (`datetime.now()` on the module raises AttributeError otherwise).
    from datetime import datetime as _datetime_class
    import hashlib

    # Hash original query for audit without storing it
    query_hash = hashlib.sha256(query.encode()).hexdigest()

    audit_record = {
        "timestamp": _datetime_class.now().isoformat(),
        "query_hash": query_hash,
        "privacy_measures": {
            "pii_redaction": {
                "applied": pii_info.get("redaction_applied", False),
                "pii_types_found": list(pii_info.get("pii_found", {}).keys()),
                "redaction_count": pii_info.get("redaction_count", 0)
            },
            "query_anonymization": {
                "applied": anonymization_info.get("anonymization_applied", False),
                "generalization_level": anonymization_info.get("generalization_level", 0),
                "techniques": anonymization_info.get("techniques_used", [])
            },
            "score_perturbation": {
                # Optional retrieval-score noise. NOT differential privacy and
                # NOT a formal privacy guarantee (no budget accounting, no
                # cross-query composition, non-cryptographic PRNG).
                "applied": dp_info.get("noise_added", False),
                "avg_noise": dp_info.get("avg_noise", 0)
            },
            "result_aggregation": {
                "method": results.get("aggregation_method", "none"),
                "k_anonymity": results.get("k_value", 1)
            }
        },
        "user_consent": user_consent or {
            "data_usage": False,
            "retention_days": 0
        },
        "pii_hygiene": {
            # Factual action descriptor — NOT a regulatory compliance verdict.
            # This node does best-effort regex PII redaction; it does NOT
            # assess or determine GDPR/CCPA/HIPAA compliance.
            "pii_redaction_attempted": pii_info.get("redaction_applied", False),
            "compliance_note": "best-effort PII hygiene only; NOT a GDPR/CCPA/HIPAA compliance determination"
        },
        "data_retention": {
            "query_stored": False,
            "results_stored": False,
            "retention_period": user_consent.get("retention_days", 0) if user_consent else 0
        }
    }

    # F9 #1117: function MUST return its dict; the prior `result = {...}`
    # bound a function-scope local that was never returned, so the audit
    # record never reached the module-scope output port.
    return {"audit_record": audit_record}

# F9 #1117: module-scope call so PythonCodeNode publishes the `audit_record`
# port the result_formatter wiring reads. `query` + `user_consent` are external
# workflow inputs; pii_info / anonymization_info / dp_info / results are wired
# from pii_detector / query_anonymizer / dp_noise_injector / secure_aggregator.
# `del` the helper so the output gate sees only `result`.
result = create_audit_record(
    query, pii_info, anonymization_info, dp_info, results, user_consent
)
del create_audit_record
"""
                },
            )

        # Result formatter with privacy report
        result_formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_formatter",
            config={
                "code": f"""
def format_private_results(secure_results, audit_record, pii_info, anonymization_info, dp_info):
    '''Format results with privacy protection report'''

    # Calculate confidence bounds due to score perturbation noise
    if dp_info.get("noise_added"):
        avg_noise = dp_info.get("avg_noise", 0)
        confidence_bounds = {{
            "lower": max(0, 1 - 2 * avg_noise),
            "upper": min(1, 1 + 2 * avg_noise),
            "confidence_level": 0.95
        }}
    else:
        confidence_bounds = {{
            "lower": 0.9,
            "upper": 1.0,
            "confidence_level": 1.0
        }}

    privacy_report = {{
        "privacy_techniques_applied": [],
        "information_loss": 0.0
    }}

    # Compile the hygiene steps that ACTUALLY ran.
    if pii_info.get("redaction_applied"):
        privacy_report["privacy_techniques_applied"].append("PII redaction")
        privacy_report["information_loss"] += 0.1

    if anonymization_info.get("anonymization_applied"):
        privacy_report["privacy_techniques_applied"].append("Query generalization")
        privacy_report["information_loss"] += 0.15

    if dp_info.get("noise_added"):
        # Optional score perturbation — NOT differential privacy, no guarantee.
        privacy_report["privacy_techniques_applied"].append("Score perturbation")
        privacy_report["information_loss"] += dp_info.get("avg_noise", 0)

    if secure_results.get("clusters_formed", 0) > 1:
        privacy_report["privacy_techniques_applied"].append("K-anonymity clustering")

    # Derive descriptors from what actually ran (never a hardcoded verdict).
    techniques_count = len(privacy_report["privacy_techniques_applied"])
    # data_minimization is true only if a minimizing step actually ran
    # (PII redaction or query generalization reduce the data exposed).
    privacy_report["data_minimization"] = bool(
        pii_info.get("redaction_applied")
        or anonymization_info.get("anonymization_applied")
    )
    # Factual strength descriptor derived from the count of hygiene steps.
    if techniques_count == 0:
        privacy_report["anonymization_strength"] = "none"
    elif techniques_count == 1:
        privacy_report["anonymization_strength"] = "minimal"
    else:
        privacy_report["anonymization_strength"] = "multi-step"

    # F9 #1117: function MUST return its dict; the prior `result = {{...}}`
    # bound a function-scope local that was never returned, so the TERMINAL
    # node published nothing and the WorkflowNode's whole output was empty.
    return {{
        "privacy_preserving_results": {{
            "results": secure_results.get("secure_results", []),
            "privacy_report": privacy_report,
            "audit_record": audit_record.get("audit_record") if {self.audit_logging} else None,
            "confidence_bounds": confidence_bounds,
            "metadata": {{
                "score_noise_scale": {self.score_noise},
                "techniques_count": len(privacy_report["privacy_techniques_applied"]),
                "data_retention": "none"
            }}
        }}
    }}

# F9 #1117: module-scope call so this TERMINAL node publishes the documented
# privacy_preserving_results (results / privacy_report / audit_record /
# confidence_bounds) the node docstring promises. All five inputs are wired:
# secure_results <- secure_aggregator.result, audit_record <- audit_logger
# .audit_record (only when audit_logging=True), pii_info / anonymization_info /
# dp_info from their producers. When audit_logging=False the audit_record port
# is not wired, so default it to an empty dict before the call. `del` the
# helper so the output gate sees only `result`.
try:
    audit_record
except NameError:
    audit_record = {{}}
result = format_private_results(
    secure_results, audit_record, pii_info, anonymization_info, dp_info
)
del format_private_results
"""
            },
        )

        # Connect workflow
        builder.add_connection(
            pii_detector_id, "result", query_anonymizer_id, "pii_info"
        )
        builder.add_connection(
            query_anonymizer_id,
            "result",
            private_rag_executor_id,
            "anonymized_query_info",
        )
        # PythonCodeNode publishes a single `result` output port carrying the
        # whole returned dict (NOT each nested key as its own port). Every
        # inter-node edge reads `result`; each downstream codegen unwraps the
        # nested shape it needs (e.g. private_rag_executor's `result` carries
        # {"retrieval_results": {documents, scores, ...}}).
        builder.add_connection(private_rag_executor_id, "result", dp_noise_id, "scores")
        builder.add_connection(
            private_rag_executor_id,
            "result",
            secure_aggregator_id,
            "retrieval_results",
        )
        builder.add_connection(dp_noise_id, "result", secure_aggregator_id, "dp_info")

        if self.audit_logging:
            # audit_logger_id was bound inside the prior `if self.audit_logging`
            # block (when self.audit_logging is True); narrow for the checker.
            assert audit_logger_id is not None
            builder.add_connection(
                pii_detector_id, "result", audit_logger_id, "pii_info"
            )
            builder.add_connection(
                query_anonymizer_id, "result", audit_logger_id, "anonymization_info"
            )
            builder.add_connection(dp_noise_id, "result", audit_logger_id, "dp_info")
            builder.add_connection(
                secure_aggregator_id, "result", audit_logger_id, "results"
            )
            builder.add_connection(
                audit_logger_id, "result", result_formatter_id, "audit_record"
            )

        builder.add_connection(
            secure_aggregator_id, "result", result_formatter_id, "secure_results"
        )
        builder.add_connection(
            pii_detector_id, "result", result_formatter_id, "pii_info"
        )
        builder.add_connection(
            query_anonymizer_id, "result", result_formatter_id, "anonymization_info"
        )
        builder.add_connection(dp_noise_id, "result", result_formatter_id, "dp_info")

        return builder.build(name="privacy_preserving_rag_workflow")


@register_node()
class SecureMultiPartyRAGNode(Node):
    """
    Multi-party aggregation placeholder — NON-FUNCTIONAL SIMULATION.

    WARNING — DO NOT USE FOR ANY PRIVACY-SENSITIVE WORKLOAD. This node does
    NOT implement secure multi-party computation, secret sharing, or
    homomorphic encryption. It performs NO cryptography and does NOT compute
    over the supplied ``party_data``: the per-party "encrypted" values it
    aggregates are samples from ``random.random()``, so the returned
    ``aggregate_result`` is the mean/sum of random numbers, unrelated to the
    inputs. The ``computation_proof`` field is a hash label, not a
    cryptographic proof, and the ``privacy_preserved`` / ``fully_encrypted``
    flags are hardcoded ``True`` with nothing backing them.

    It exists only as an interface/shape placeholder. It is flagged for
    REMOVAL — a real implementation would require an actual MPC/secret-sharing
    or homomorphic-encryption library, none of which is present here. Until a
    real implementation lands (or the node is removed), treat any output as
    meaningless.

    Parameters:
        parties: List of participating party identifiers (labels only)
        protocol: Dispatch label ("secret_sharing" | "homomorphic") selecting
            which simulated code path runs — NOT a real cryptographic protocol
        threshold: Minimum number of parties required before the simulated
            path runs (an input-count check only)

    Returns (all simulated — see WARNING above):
        aggregate_result: Mean/sum of per-party RANDOM values (not real data)
        computation_proof: A hash label, NOT a cryptographic proof
        party_contributions: Per-party status placeholders
    """

    def __init__(
        self,
        name: str = "secure_multiparty_rag",
        parties: Optional[List[str]] = None,
        protocol: str = "secret_sharing",
        threshold: int = 2,
    ):
        # User-approved deprecation (zero-tolerance Rule 6a — remove via a
        # deprecation cycle). This node is a NON-FUNCTIONAL simulation: it
        # performs NO cryptography (no secret sharing / homomorphic encryption /
        # MPC) and does NOT compute over party_data — it aggregates
        # random.random() placeholders. It is slated for REMOVAL in a future
        # minor release. There is no real in-tree alternative; do not rely on
        # its output for any privacy-sensitive workload.
        warnings.warn(
            "SecureMultiPartyRAGNode is a non-functional simulation: it performs "
            "NO cryptography (no secret sharing, homomorphic encryption, or "
            "multi-party computation) and does NOT compute over party_data (it "
            "aggregates random placeholder values). It is DEPRECATED and will be "
            "REMOVED in a future minor release. Do not use it for any "
            "privacy-sensitive workload; no real alternative is provided.",
            DeprecationWarning,
            stacklevel=2,
        )
        resolved_parties = parties or []
        super().__init__(
            name=name,
            parties=resolved_parties,
            protocol=protocol,
            threshold=threshold,
        )
        self.parties = resolved_parties
        self.protocol = protocol
        self.threshold = threshold

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="secure_multiparty_rag",
                description="Node instance name",
            ),
            "parties": NodeParameter(
                name="parties",
                type=list,
                required=False,
                default=None,
                description="Participating party identifiers (labels only)",
            ),
            "protocol": NodeParameter(
                name="protocol",
                type=str,
                required=False,
                default="secret_sharing",
                description=(
                    "Dispatch label selecting the simulated code path "
                    "('secret_sharing' | 'homomorphic') — NOT a real "
                    "cryptographic protocol (this node is a non-functional "
                    "simulation; see class docstring)"
                ),
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=int,
                required=False,
                default=2,
                description="Minimum number of parties before the simulated path runs",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query label (not used in any real computation)",
            ),
            "party_data": NodeParameter(
                name="party_data",
                type=dict,
                required=True,
                description=(
                    "Per-party data — NOTE: this node does NOT compute over "
                    "these values (simulation only; see class docstring)"
                ),
            ),
            "computation_type": NodeParameter(
                name="computation_type",
                type=str,
                required=False,
                default="average",
                description="Aggregation label ('average' | 'sum' | 'count')",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the multi-party aggregation SIMULATION.

        WARNING: non-functional simulation. See the class docstring — no
        cryptography runs and ``party_data`` is not computed over.
        """
        query = kwargs.get("query", "")
        party_data = kwargs.get("party_data", {})
        computation_type = kwargs.get("computation_type", "average")

        # Validate parties
        if len(party_data) < self.threshold:
            return {
                "error": f"Insufficient parties: {len(party_data)} < {self.threshold}",
                "required_parties": self.threshold,
            }

        # Dispatch to the matching SIMULATED code path (no real crypto).
        if self.protocol == "secret_sharing":
            result = self._secret_sharing_computation(
                query, party_data, computation_type
            )
        elif self.protocol == "homomorphic":
            result = self._homomorphic_computation(query, party_data, computation_type)
        else:
            result = {"error": f"Unknown protocol: {self.protocol}"}

        return result

    def _secret_sharing_computation(
        self, query: str, party_data: Dict, computation_type: str
    ) -> Dict[str, Any]:
        """SIMULATION — no secret sharing is performed.

        Aggregates RANDOM per-party values (NOT ``party_data``). See the class
        docstring. A real implementation requires an actual secret-sharing /
        MPC library, which is not present.
        """

        # Per-party placeholder values — random, NOT derived from party_data.
        shares = {}
        for party, data in party_data.items():
            shares[party] = {
                "share_id": hashlib.sha256(f"{party}_{query}".encode()).hexdigest()[:8],
                "value": random.random(),  # placeholder; NOT an encrypted share
                "commitment": hashlib.sha256(str(data).encode()).hexdigest()[:16],
            }

        # Aggregate the random placeholder values (meaningless output).
        if computation_type == "average":
            aggregated_value = sum(s["value"] for s in shares.values()) / len(shares)
        elif computation_type == "sum":
            aggregated_value = sum(s["value"] for s in shares.values())
        elif computation_type == "count":
            aggregated_value = len([s for s in shares.values() if s["value"] > 0.5])
        else:
            aggregated_value = 0.5

        # Descriptive record — a hash label, NOT a cryptographic proof.
        computation_record = {
            "protocol": "simulated_secret_sharing",
            "simulation": True,
            "parties_involved": list(shares.keys()),
            "threshold_met": len(shares) >= self.threshold,
            "record_hash": hashlib.sha256(
                f"{aggregated_value}_{list(shares.keys())}".encode()
            ).hexdigest()[:32],
            "timestamp": datetime.now().isoformat(),
        }

        return {
            "aggregate_result": aggregated_value,
            "computation_proof": computation_record,
            "party_contributions": {
                party: {"status": "contributed", "share_id": share["share_id"]}
                for party, share in shares.items()
            },
            "simulation": True,
        }

    def _homomorphic_computation(
        self, query: str, party_data: Dict, computation_type: str
    ) -> Dict[str, Any]:
        """SIMULATION — no homomorphic encryption is performed.

        Aggregates RANDOM per-party values (NOT ``party_data``). See the class
        docstring. A real implementation requires an actual HE library, which
        is not present.
        """

        placeholder_results = []
        for party in party_data:
            placeholder_results.append(
                {
                    "party": party,
                    "value": random.random() * 100,  # placeholder, NOT encrypted
                }
            )

        # Aggregate the random placeholder values (meaningless output).
        if computation_type == "average":
            final_result = sum(r["value"] for r in placeholder_results) / len(
                placeholder_results
            )
        else:
            final_result = sum(r["value"] for r in placeholder_results)

        return {
            "aggregate_result": final_result,
            "computation_proof": {
                "protocol": "simulated_homomorphic",
                "simulation": True,
            },
            "party_contributions": {
                r["party"]: {"computed": True} for r in placeholder_results
            },
            "simulation": True,
        }


@register_node()
class ComplianceRAGNode(Node):
    """
    Compliance-Aware RAG Node

    Ensures RAG operations comply with privacy regulations.

    When to use:
    - Best for: Regulated industries, international operations
    - Regulations: GDPR, CCPA, HIPAA, PIPEDA
    - Features: Consent management, data retention, right to be forgotten

    Example:
        compliance_rag = ComplianceRAGNode(
            regulations=["gdpr", "hipaa"],
            default_retention_days=30
        )

        result = await compliance_rag.execute(
            query="Patient symptoms analysis",
            user_consent={
                "purpose": "medical_diagnosis",
                "retention_allowed": True,
                "sharing_allowed": False
            },
            jurisdiction="EU"
        )

    Parameters:
        regulations: List of regulations to comply with
        default_retention_days: Default data retention period
        require_explicit_consent: Whether explicit consent is required

    Returns:
        results: Compliant query results
        compliance_report: Regulatory compliance details
        retention_policy: Data retention information
        user_rights: Available user rights (deletion, access, etc.)
    """

    def __init__(
        self,
        name: str = "compliance_rag",
        regulations: Optional[List[str]] = None,
        default_retention_days: int = 30,
        require_explicit_consent: bool = True,
    ):
        resolved_regulations = regulations or ["gdpr", "ccpa"]
        super().__init__(
            name=name,
            regulations=resolved_regulations,
            default_retention_days=default_retention_days,
            require_explicit_consent=require_explicit_consent,
        )
        self.regulations = resolved_regulations
        self.default_retention_days = default_retention_days
        self.require_explicit_consent = require_explicit_consent

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="compliance_rag",
                description="Node instance name",
            ),
            "regulations": NodeParameter(
                name="regulations",
                type=list,
                required=False,
                default=None,
                description="Compliance regulations to enforce (gdpr, ccpa, ...)",
            ),
            "default_retention_days": NodeParameter(
                name="default_retention_days",
                type=int,
                required=False,
                default=30,
                description="Default data retention period in days",
            ),
            "require_explicit_consent": NodeParameter(
                name="require_explicit_consent",
                type=bool,
                required=False,
                default=True,
                description="Require explicit user consent before processing",
            ),
            "query": NodeParameter(
                name="query", type=str, required=True, description="Query to process"
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to search",
            ),
            "user_consent": NodeParameter(
                name="user_consent",
                type=dict,
                required=True,
                description="User consent information",
            ),
            "jurisdiction": NodeParameter(
                name="jurisdiction",
                type=str,
                required=False,
                description="User's jurisdiction",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute compliance-aware RAG"""
        query = kwargs.get("query", "")
        documents = kwargs.get("documents", [])
        user_consent = kwargs.get("user_consent", {})
        jurisdiction = kwargs.get("jurisdiction", "US")

        # Check consent
        consent_valid = self._validate_consent(user_consent, jurisdiction)
        if not consent_valid["valid"]:
            return {
                "error": "Insufficient consent",
                "required_consent": consent_valid["required"],
                "user_rights": self._get_user_rights(jurisdiction),
            }

        # Apply compliance filters
        compliant_docs = self._filter_compliant_documents(documents, jurisdiction)

        # Process query with compliance
        results = self._compliant_retrieval(query, compliant_docs)

        # Generate compliance report
        compliance_report = self._generate_compliance_report(
            query, results, user_consent, jurisdiction
        )

        return {
            "results": results,
            "compliance_report": compliance_report,
            "retention_policy": {
                "retention_days": user_consent.get(
                    "retention_days", self.default_retention_days
                ),
                "deletion_date": (
                    datetime.now().timestamp() + self.default_retention_days * 86400
                ),
            },
            "user_rights": self._get_user_rights(jurisdiction),
        }

    def _validate_consent(self, consent: Dict, jurisdiction: str) -> Dict[str, Any]:
        """Validate user consent against regulations"""
        required_fields = {
            "gdpr": [
                "purpose",
                "retention_allowed",
                "sharing_allowed",
                "explicit_consent",
            ],
            "ccpa": ["purpose", "opt_out_option", "data_categories"],
            "hipaa": ["purpose", "minimum_necessary", "authorization"],
        }

        valid = True
        missing = []

        for regulation in self.regulations:
            if regulation in required_fields:
                for field in required_fields[regulation]:
                    if field not in consent:
                        valid = False
                        missing.append(field)

        return {
            "valid": valid
            and (
                not self.require_explicit_consent
                or consent.get("explicit_consent", False)
            ),
            "required": missing,
            "regulations_checked": self.regulations,
        }

    def _filter_compliant_documents(
        self, documents: List[Dict], jurisdiction: str
    ) -> List[Dict]:
        """Filter documents based on compliance requirements"""
        compliant_docs = []

        for doc in documents:
            # Check document compliance metadata
            doc_jurisdiction = doc.get("metadata", {}).get("jurisdiction", "US")
            doc_restrictions = doc.get("metadata", {}).get("restrictions", [])

            # Check if document can be used in user's jurisdiction
            if jurisdiction == "EU" and "no_eu_transfer" in doc_restrictions:
                continue

            # Check data classification
            classification = doc.get("metadata", {}).get("classification", "public")
            if (
                classification in ["restricted", "confidential"]
                and jurisdiction != doc_jurisdiction
            ):
                continue

            compliant_docs.append(doc)

        return compliant_docs

    def _compliant_retrieval(self, query: str, documents: List[Dict]) -> List[Dict]:
        """Perform retrieval with compliance considerations"""
        # Simple retrieval with compliance
        results = []

        for doc in documents[:10]:
            # Redact based on classification
            classification = doc.get("metadata", {}).get("classification", "public")

            if classification == "public":
                content = doc.get("content", "")
            elif classification == "internal":
                content = (
                    doc.get("content", "")[:200] + "... [Truncated for compliance]"
                )
            else:
                content = "[Content restricted due to classification]"

            results.append(
                {
                    "content": content,
                    "classification": classification,
                    "compliance_filtered": classification != "public",
                }
            )

        return results

    def _generate_compliance_report(
        self, query: str, results: List[Dict], consent: Dict, jurisdiction: str
    ) -> Dict[str, Any]:
        """Generate a compliance report derived from the checks that ran."""
        fields_redacted = sum(1 for r in results if r.get("compliance_filtered", False))
        # data_minimization is "applied" only when classification filtering
        # actually redacted/truncated at least one result — never an
        # unconditional True.
        minimization_applied = fields_redacted > 0

        # Derive a score from REAL signals, not a magic constant. Each factual
        # check that passed contributes equally; the score is the fraction of
        # checks that held for this request.
        signals = [
            bool(consent.get("explicit_consent")),  # explicit consent captured
            self._determine_lawful_basis(consent, jurisdiction)
            != "legitimate_interests",  # a stronger lawful basis than the fallback
            minimization_applied,  # minimization actually reduced exposure
            len(self.regulations) > 0,  # at least one regulation enforced
        ]
        compliance_score = round(sum(1 for s in signals if s) / len(signals), 2)

        return {
            "regulations_applied": self.regulations,
            "jurisdiction": jurisdiction,
            "consent_status": {
                "explicit_consent": consent.get("explicit_consent", False),
                "purpose": consent.get("purpose", "not_specified"),
                "lawful_basis": self._determine_lawful_basis(consent, jurisdiction),
            },
            "data_minimization": {
                "applied": minimization_applied,
                "documents_filtered": len(results),
                "fields_redacted": fields_redacted,
            },
            "audit_trail": {
                "timestamp": datetime.now().isoformat(),
                "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
                "retention_commitment": consent.get(
                    "retention_days", self.default_retention_days
                ),
            },
            # Fraction of the factual compliance checks above that held for
            # this request — derived, not a hardcoded "high compliance" number.
            "compliance_score": compliance_score,
        }

    def _determine_lawful_basis(self, consent: Dict, jurisdiction: str) -> str:
        """Determine lawful basis for processing"""
        if consent.get("explicit_consent"):
            return "consent"
        elif consent.get("purpose") == "medical_diagnosis":
            return "vital_interests"
        elif consent.get("purpose") == "legal_requirement":
            return "legal_obligation"
        else:
            return "legitimate_interests"

    def _get_user_rights(self, jurisdiction: str) -> Dict[str, bool]:
        """Get user rights based on jurisdiction"""
        rights = {
            "gdpr": {
                "access": True,
                "rectification": True,
                "erasure": True,
                "portability": True,
                "restriction": True,
                "objection": True,
            },
            "ccpa": {
                "access": True,
                "deletion": True,
                "opt_out": True,
                "non_discrimination": True,
            },
        }

        user_rights = {}
        for regulation in self.regulations:
            if regulation in rights:
                user_rights.update(rights[regulation])

        return user_rights


# Export all privacy nodes
__all__ = ["PrivacyPreservingRAGNode", "SecureMultiPartyRAGNode", "ComplianceRAGNode"]
