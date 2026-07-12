"""
Cache Key Generator

Generates deterministic cache keys from queries and parameters.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Union
from urllib.parse import urlparse

from kailash.utils.url_credentials import UNPARSEABLE_URL_SENTINEL, mask_url

if TYPE_CHECKING:
    from dataflow.classification.policy import ClassificationPolicy

# Express (Rust-pinned) cross-SDK cache keyspace version. Bumped v2 -> v3 for
# issue #1606 (the Rust SDK's #1713): the v3 keyspace inserts a database-instance
# segment immediately after the version token so two DataFlow instances at
# DIFFERENT databases sharing a process-wide cache backend (e.g. Redis) can never
# collide on the same physical key. This is DISTINCT from
# ``CacheKeyGenerator.version`` (the py-local QUERY keyspace, still ``v2``): the
# express keyspace is a byte-for-byte contract with the Rust SDK and MUST move in
# lockstep with it (canonical vectors: ``tests/fixtures/dataflow-cache-keys.json``,
# contract ``dataflow-cache-keys-v3``); the query keyspace diverges cross-SDK by
# construction (py vs rs emit different SQL) and versions independently.
EXPRESS_KEYSPACE_VERSION = "v3"


def _hash8(material: str) -> str:
    """Return the first 8 hex chars of sha256(material)."""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]


def _sanitize_component_host(host: str) -> str:
    """Strip any credential-carrying userinfo from a component-config host.

    Defense-in-depth parity (#1606): the URL identity path routes through
    ``mask_url`` (userinfo stripped to ``***``) BEFORE hashing, so no
    credential byte reaches the hash pre-image. The component-fallback path
    hashes ``host:port/dbname`` directly — so if an operator mis-sets
    ``config.database.host`` to a full DSN-with-creds (e.g.
    ``postgres://u:pw@h/db``) AND leaves ``url`` absent, those credential
    bytes would otherwise enter the pre-image. When ``host`` is DSN-shaped
    (contains ``@`` or ``://``), strip the scheme and the userinfo so only a
    credential-free host substring survives; a normal bare hostname is
    returned BYTE-IDENTICALLY (the guard triggers ONLY on the DSN-shaped
    case, so it never changes the identity of a correctly-configured host).

    NOTE: ``host`` and ``dbname`` are assumed delimiter-free for the
    ``host:port/dbname`` join; a literal ``:`` / ``/`` inside a component
    field is not disambiguated (no realistic cross-DB collision is
    constructible — the fields come from structured config, not free text).
    """
    if "@" not in host and "://" not in host:
        return host
    stripped = host
    if "://" in stripped:
        stripped = stripped.split("://", 1)[1]
    if "@" in stripped:
        # userinfo (user[:password]) precedes the last '@'; keep only the host side.
        stripped = stripped.rsplit("@", 1)[1]
    return stripped


def hash_database_identity(database_url: Optional[str]) -> Optional[str]:
    """Return a short, credential-free fingerprint of a database URL.

    Used as the DB-instance identity segment in the QUERY cache keyspace
    (issue #1606) so two DataFlow instances pointed at *different* databases
    never collide on the same query cache key. The query keyspace hashes a
    normalized SQL string + params, which is identical for the same
    model+filter regardless of which database the instance targets — so
    without this segment two instances at different DBs read each other's
    cached query rows (cross-DB cache bleed).

    The URL is FIRST routed through ``mask_url`` (credential-stripped:
    scheme + ``***`` placeholder + host+port+dbname, NEVER user/password
    bytes) BEFORE hashing, so no credential can ever enter the key. Redis
    keys are an observable surface — treat like logs (``rules/security.md``
    § "No secrets in logs").

    Returns ``None`` when the URL is falsy OR unparseable (``mask_url``
    yields ``UNPARSEABLE_URL_SENTINEL`` — e.g. a libpq keyword/value DSN
    ``"host=a dbname=x"`` with no ``://``). Hashing the sentinel is
    DELIBERATELY refused: every unparseable-DSN instance would otherwise
    share one CONSTANT identity, silently collapsing cross-DB isolation
    (``rules/zero-tolerance.md`` Rule 3, silent fallback). Callers that
    need the URL-vs-components-vs-none disposition (to warn the operator)
    use ``resolve_db_identity`` instead.

    SCOPE (issue #1606) — the identity keys on database LOCATION
    (host/port/dbname), NOT on the connecting principal: ``mask_url``
    strips userinfo to ``***``, so ``postgres://alice:pw1@h:5432/db`` and
    ``postgres://bob:pw2@h:5432/db`` produce the SAME identity. Two
    instances at the same database with different DB credentials share a
    cache namespace BY DESIGN. Deployments relying on per-principal
    DB-level row visibility (RLS / per-user GRANTs) MUST NOT share a cache
    backend across principals.

    NOTE: this segments the QUERY keyspace only. The Express keyspace
    (``generate_express_key``) carries its OWN cross-SDK db-instance
    segment from ``express_db_instance_fingerprint`` (a different algorithm
    + length); this query-side fingerprint MUST NOT be used there.
    """
    if not database_url:
        return None
    # mask_url is the single credential-masking helper; its output never
    # contains user/password bytes (only a constant ``***`` placeholder),
    # so hashing it yields a stable per-DB fingerprint with zero credential
    # exposure even if the digest were ever reversed.
    masked = mask_url(database_url)
    if masked == UNPARSEABLE_URL_SENTINEL:
        # A non-URL DSN (or garbage) masks to a CONSTANT sentinel; hashing it
        # would give every such instance the same identity — refuse.
        return None
    return _hash8(masked)


def express_db_instance_fingerprint(database_url: Optional[str]) -> Optional[str]:
    """Return the Rust-pinned ``db<16 hex>`` db-instance segment for EXPRESS v3.

    This is the EXPRESS-keyspace sibling of :func:`hash_database_identity` and is
    a DELIBERATELY DIFFERENT algorithm — it is a byte-for-byte cross-SDK contract
    with the Rust SDK (issue #1606 / the Rust SDK's #1713, contract
    ``dataflow-cache-keys-v3``), NOT the py-local query-keyspace fingerprint:

    * ``hash_database_identity`` (QUERY keyspace) hashes ``mask_url(...)``
      (``scheme://***@host:port/dbname``) and takes 8 hex chars. py-local shape.
    * THIS function (EXPRESS keyspace) hashes the NORMALIZED connection target
      ``scheme://<authority><path>`` — scheme lowercased, userinfo (credentials)
      and query string and fragment stripped BEFORE hashing — and takes the
      FIRST 16 hex chars (64 bits), prefixed with the literal ``db``. The two
      MUST NOT be interchanged; the express bytes are pinned by the vendored
      canonical vectors and any drift breaks cross-SDK cache-key parity.

    The normalized pre-image carries NO credential byte (userinfo is stripped),
    so a Redis key — an observable surface (``rules/security.md`` § "No secrets
    in logs") — can never leak a password even if the digest were reversed. Two
    instances at the SAME database with different DB credentials share a cache
    namespace by design (the identity keys on database LOCATION, not principal).

    Returns ``None`` when the URL is falsy OR unparseable (no scheme), OR when a
    ``//``-less credential-bearing DSN would otherwise leak credential bytes into
    the pre-image (see below). Callers that get ``None`` MUST emit a loud warning
    — cross-DB cache isolation is then INACTIVE on a shared backend
    (``rules/zero-tolerance.md`` Rule 3, no silent fallback).

    KNOWN LIMITATION (cross-SDK-pinned): the identity keys on the connection
    TARGET (``scheme://host:port/dbname``) — the query string is stripped, so two
    instances at the SAME host/port/dbname that select a different SCHEMA via a
    query parameter (e.g. ``?options=-csearch_path=a`` vs ``...=b``) share one
    ``db_instance``. Deployments relying on per-schema-via-query isolation MUST
    NOT share a cache backend across those instances. This normalization is the
    byte-for-byte cross-SDK contract and MUST NOT be changed unilaterally
    (``cross-sdk-inspection.md`` Rule 4b).

    Examples (canonical vectors):
        ``postgres://cache-host:5432/app_a``            -> ``dbd4e3f17d35c2bb57``
        ``sqlite:///var/data/app_b.db``                 -> ``db5c74b84689218303``
        ``postgres://svc_user:s3cr3t@cache-host:5432/app_a`` -> ``dbd4e3f17d35c2bb57``
        (credentials stripped -> identical to the credential-free form)
    """
    if not database_url:
        return None
    try:
        parsed = urlparse(database_url)
    except Exception:
        # urlparse is tolerant, but fail closed on any parse error rather than
        # hashing a garbage constant that would collapse cross-DB isolation.
        return None
    if not parsed.scheme:
        return None
    netloc = parsed.netloc
    # Fail closed on a ``//``-less credential-bearing DSN. ``urlparse`` only
    # populates ``netloc`` for a ``scheme://authority`` URL; a
    # ``scheme:user:pass@host/db`` form (no ``//``) leaves ``netloc`` empty and
    # the userinfo in ``path``, so the ``@``-strip below would never fire and
    # credential bytes would enter the hash pre-image. Refuse rather than hash a
    # credential (defense-in-depth; the caller warns and isolation is INACTIVE).
    # A ``//``-authority URL (``postgres://...``) always has a non-empty netloc;
    # a sqlite file URL (``sqlite:///path``) has empty netloc but no ``@`` in the
    # path — so this guard never fires for any valid/canonical target.
    if not netloc and "@" in parsed.path:
        return None
    # Strip userinfo (user[:password]@) from the authority — only host[:port]
    # survives, so no credential byte enters the hash pre-image.
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    # query + fragment live in parsed.query / parsed.fragment and are excluded
    # from the pre-image by construction (only scheme://netloc/path is joined).
    normalized = f"{parsed.scheme.lower()}://{netloc}{parsed.path}"
    return "db" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class DbIdentityResolution(NamedTuple):
    """Outcome of :func:`resolve_db_identity`.

    Attributes:
        identity: The credential-free DB-identity segment, or ``None`` when
            no usable identity could be derived (the query keyspace then
            falls back to the pre-#1606 shape and cross-DB isolation is
            INACTIVE — the caller MUST warn).
        source: ``"url"`` (derived from the connection URL), ``"components"``
            (derived from host/port/dbname structured config after the URL
            was absent or unparseable), or ``"none"`` (no usable identity).
        url_unparseable: ``True`` when a URL string was supplied but
            ``mask_url`` could not parse it (a keyword/value DSN or garbage).
            The caller warns on this even when the component fallback
            succeeds, because the supplied URL could not be used.
    """

    identity: Optional[str]
    source: str
    url_unparseable: bool


def resolve_db_identity(
    url: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[Union[int, str]] = None,
    dbname: Optional[str] = None,
) -> DbIdentityResolution:
    """Resolve a credential-free DB-instance identity (issue #1606).

    Tries the connection URL first; when the URL is absent OR unparseable,
    falls back to the structured component config (``host``/``port``/
    ``dbname``) so cross-DB isolation still HOLDS for URL-less DataFlow
    instances (component/params config, or a lazily-populated URL). The
    component identity is a hash of a normalized ``host:port/dbname``
    string — host+port+dbname ONLY, NEVER any user/password field — so the
    same credential-free contract as the URL path holds.

    Returns a :class:`DbIdentityResolution`; when ``identity is None`` the
    caller MUST emit a loud warning (cross-DB cache isolation is INACTIVE
    on a shared cache backend). See ``rules/zero-tolerance.md`` Rule 3 —
    silent-unprotected is the failure mode this resolution + the caller's
    warning close.

    The identity is captured ONCE at cache-integration construction; a URL
    set on the config AFTER construction does not retroactively change it
    (acceptable — DataFlow database URLs are set at init).
    """
    # 1. URL path.
    if url:
        masked = mask_url(url)
        if masked != UNPARSEABLE_URL_SENTINEL:
            return DbIdentityResolution(_hash8(masked), "url", False)
        url_unparseable = True
    else:
        url_unparseable = False

    # 2. Component fallback — credential-free host:port/dbname. Never hash
    #    the unparseable sentinel (that constant would collapse isolation);
    #    derive from structured fields instead so URL-less configs stay
    #    isolated. host + dbname are the minimum; port is optional.
    if host and dbname:
        # Defense-in-depth (#1606): strip any credential-carrying userinfo if
        # host was mis-set to a DSN, so no credential byte enters the hash
        # pre-image (parity with the URL path's mask_url step). A bare
        # hostname is unchanged, so a correctly-configured host's identity is
        # byte-identical to the pre-sanitize behavior.
        safe_host = _sanitize_component_host(host)
        normalized = f"{safe_host}:{port if port is not None else ''}/{dbname}"
        return DbIdentityResolution(_hash8(normalized), "components", url_unparseable)

    # 3. No usable identity — segmentation is DISABLED; the caller warns.
    return DbIdentityResolution(None, "none", url_unparseable)


class CacheKeyGenerator:
    """Generates cache keys for queries."""

    def __init__(
        self,
        prefix: str = "dataflow",
        namespace: Optional[str] = None,
        version: str = "v2",
        classification_policy: Optional["ClassificationPolicy"] = None,
        db_identity: Optional[str] = None,
        express_db_instance: Optional[str] = None,
    ):
        """
        Initialize key generator.

        Args:
            prefix: Global prefix for all keys
            namespace: Optional namespace (e.g., tenant ID)
            version: QUERY-keyspace version (``generate_key``). Default ``"v2"``
                (py-local; diverges cross-SDK by construction — py vs rs emit
                different SQL). This is NOT the express keyspace version; the
                express keyspace is Rust-pinned at ``EXPRESS_KEYSPACE_VERSION``
                (``v3``, issue #1606) and is not affected by this argument.
            classification_policy: Optional policy used to hash classified
                PK values before they enter the key-material hash. When
                provided, PKs whose model+field pair is classified are
                routed through ``format_record_id_for_event`` before
                serialization so the raw value never appears in the JSON
                that feeds the MD5/SHA-256 digest. See issue #520.
            db_identity: Optional credential-free fingerprint of the
                database this generator serves, produced by
                ``hash_database_identity``. When set, it is inserted into
                the QUERY keyspace (``generate_key``) — directly after the
                model name — so two DataFlow instances at *different*
                databases never collide on the same query cache key
                (issue #1606: cross-DB cache bleed). It is DELIBERATELY
                absent from ``generate_express_key`` — the express keyspace
                carries its OWN ``express_db_instance`` segment (below), a
                different byte-for-byte cross-SDK fingerprint; the two MUST
                NOT be interchanged.
            express_db_instance: Optional Rust-pinned ``db<16 hex>``
                database-instance segment for the EXPRESS keyspace
                (``generate_express_key``), produced by
                ``express_db_instance_fingerprint``. When set, it is inserted
                directly AFTER the version token (``dataflow:v3:<db_instance>:
                ...``) so two DataFlow instances at *different* databases
                never collide on the same express cache key (issue #1606 /
                the Rust SDK's #1713, the v2->v3 lockstep). DISTINCT from
                ``db_identity`` (query keyspace, different algorithm + length);
                the two are never interchanged.
        """
        self.prefix = prefix
        self.namespace = namespace
        self.version = version
        self._classification_policy = classification_policy
        self.db_identity = db_identity
        self.express_db_instance = express_db_instance

    def _safe_params(self, model_name: str, params: Any) -> Any:
        """Return a copy of ``params`` with classified PK values hashed.

        Routes ``params["id"]`` (and any ``{"id": ...}`` nested in a
        filter dict) through ``format_record_id_for_event`` when the
        classification policy marks the model's PK as classified.
        Non-dict inputs and dicts without an ``id`` key pass through
        unchanged. Mirrors the filtering contract of
        ``kailash-rs`` BP-049.
        """
        if self._classification_policy is None or not isinstance(params, dict):
            return params
        # Lazy import avoids a cycle with features/express.py.
        from dataflow.classification.event_payload import format_record_id_for_event

        def _hash_id(mapping: Dict[str, Any]) -> Dict[str, Any]:
            if "id" not in mapping:
                return mapping
            safe = dict(mapping)
            safe["id"] = format_record_id_for_event(
                self._classification_policy, model_name, mapping["id"]
            )
            return safe

        safe_params = _hash_id(params)
        # Filter-style params ({"filter": {"id": ...}}) — hash the nested id.
        if isinstance(safe_params.get("filter"), dict):
            safe_params = dict(safe_params)
            safe_params["filter"] = _hash_id(safe_params["filter"])
        return safe_params

    def generate_key(
        self, model_name: str, sql: str, params: List[Any], ttl: Optional[int] = None
    ) -> str:
        """
        Generate cache key from query components.

        Args:
            model_name: Name of the model
            sql: SQL query string
            params: Query parameters
            ttl: TTL (not included in key)

        Returns:
            Deterministic cache key

        Raises:
            ValueError: If inputs are invalid
        """
        if not model_name:
            raise ValueError("Model name is required")
        if not sql:
            raise ValueError("SQL query is required")
        if model_name is None:
            raise ValueError("Model name cannot be None")

        # Normalize SQL (remove extra whitespace)
        normalized_sql = " ".join(sql.split())

        # Create key components
        components = [self.prefix]

        if self.namespace:
            components.append(self.namespace)

        components.append(model_name)

        # Issue #1606: DB-instance identity segment. The query keyspace
        # hashes a normalized SQL string + params — identical for the same
        # model+filter across every database — so without this segment two
        # DataFlow instances at different DBs collide on one key and read
        # each other's cached rows (cross-DB cache bleed). Placed AFTER the
        # model name so the existing model-anchored invalidation sweeps
        # (``{prefix}:{model}:*`` and the ``:{model}:`` substring matcher)
        # still match BOTH old-shape (no db_identity) and new-shape keys.
        # The query keyspace is NOT the Rust-pinned express keyspace — it
        # diverges cross-SDK by construction (py vs rs emit different SQL),
        # so this segment is a py-local change, not a cross-SDK lockstep. The
        # express keyspace has its OWN Rust-pinned db-instance segment; see
        # ``generate_express_key`` / ``express_db_instance_fingerprint``.
        if self.db_identity:
            components.append(self.db_identity)

        components.extend([self.version, self._hash_query(normalized_sql, params)])

        # Join with colons
        key = ":".join(components)

        # Ensure reasonable length
        if len(key) > 250:
            # Hash the key if too long
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
            key = f"{self.prefix}:{model_name}:{key_hash}"

        return key

    def generate_key_from_builder(self, model_name: str, builder: Any) -> str:
        """
        Generate cache key from QueryBuilder.

        Args:
            model_name: Name of the model
            builder: QueryBuilder instance

        Returns:
            Cache key
        """
        # Get SQL and params from builder
        sql, params = builder.build_select()
        return self.generate_key(model_name, sql, params)

    def generate_express_key(
        self,
        model_name: str,
        operation: str,
        params: Any = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """Generate cache key for Express operations (no SQL).

        Produces keys like ``dataflow:v2:<tenant>:<model>:<op>:<hash>``
        where ``<tenant>`` is only included when a ``tenant_id`` is
        provided (or the generator was constructed with a namespace).
        The trailing segment is a short hash of the serialised *params*.
        When a ``classification_policy`` was configured and ``params``
        contains a classified PK under ``id``, the PK is routed through
        ``format_record_id_for_event`` BEFORE serialisation so the raw
        value never enters the hash input. See issue #520 (BP-049).

        Shape (``v3`` keyspace; issue #1606 / the Rust SDK's #1713 cross-SDK
        lockstep). The ``db_instance`` segment sits directly after the
        version, BEFORE the tenant, and is present in BOTH forms (it is
        absent only when the generator was constructed without an
        ``express_db_instance`` — a degraded no-DB fallback):

        * Single-tenant: ``dataflow:v3:<db_instance>:User:list:a1b2c3d4``
        * Multi-tenant:  ``dataflow:v3:<db_instance>:tenant-a:User:list:a1b2c3d4``
        * No db_instance (fallback): ``dataflow:v3:User:list:a1b2c3d4``

        The ``tenant_id`` argument takes precedence over the
        constructor ``namespace`` when both are supplied, so a
        multi-tenant DataFlow instance can share a single key generator
        across requests and bind the tenant per-call.

        Args:
            model_name: Name of the model (e.g. ``"User"``).
            operation: Express operation name (``"read"``, ``"list"``,
                etc.).
            params: Arbitrary JSON-serialisable parameters (optional).
            tenant_id: Per-call tenant identifier for multi-tenant
                cache partitioning. Callers that hit a ``multi_tenant``
                DataFlow MUST supply this; the Express wrapper enforces
                it before calling into the generator.

        Returns:
            Deterministic cache key.

        Raises:
            ValueError: If *model_name* or *operation* is empty/None.
        """
        if not model_name:
            raise ValueError("Model name is required")
        if not operation:
            raise ValueError("Operation is required")

        params_hash: Optional[str] = None
        if params is not None:
            safe = self._safe_params(model_name, params)
            param_str = json.dumps(safe, sort_keys=True, default=str)
            params_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]

        return self._assemble_express_key(model_name, operation, params_hash, tenant_id)

    def _assemble_express_key(
        self,
        model_name: str,
        operation: str,
        params_hash: Optional[str],
        tenant_id: Optional[str],
    ) -> str:
        """Assemble a v3 express physical key from an already-computed hash.

        This is the byte-for-byte cross-SDK assembly seam (the equivalent of
        the Rust SDK's ``BackendKey::to_physical``): it concatenates the
        keyspace segments in the canonical v3 order and is exercised directly
        by the conformance test against the vendored canonical vectors
        (``tests/fixtures/dataflow-cache-keys.json``). ``generate_express_key``
        computes ``params_hash`` (MD5 of the serialised params) then delegates
        here; the conformance test injects the vectors' pre-computed
        ``params_hash`` instead.

        ``params_hash`` semantics:

        * ``None`` — no params were supplied; the trailing segment is OMITTED
          (``dataflow:v3:<db_instance>:User:list``). Backward-compatible with
          the pre-#1606 no-params shape.
        * ``""`` (empty string) — a PRESENT-but-empty hash; the segment IS
          appended, so the key ends in a bare ``:`` (canonical vector V4:
          ``dataflow:v3:<db_instance>:Product:list:``). ``generate_express_key``
          never emits this (MD5 is always 8 chars); it is a conformance-only
          shape the assembly must reproduce to match the Rust SDK byte-for-byte.
        """
        parts: list[str] = [self.prefix, EXPRESS_KEYSPACE_VERSION]
        # #1606 db-instance segment: directly after the version, before tenant.
        # Present in every production key (a DataFlow always has a connection
        # target); absent only in the degraded no-URL fallback, where the
        # express wrapper has already logged that cross-DB isolation is INACTIVE.
        if self.express_db_instance:
            parts.append(self.express_db_instance)
        if tenant_id is not None:
            parts.append(str(tenant_id))
        elif self.namespace:
            parts.append(self.namespace)
        parts.append(model_name)
        parts.append(operation)
        if params_hash is not None:
            parts.append(params_hash)

        return ":".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hash_query(self, sql: str, params: List[Any]) -> str:
        """
        Create hash from query and parameters.

        Args:
            sql: Normalized SQL query
            params: Query parameters

        Returns:
            Hash string
        """
        # Create deterministic string representation
        query_data = {"sql": sql, "params": self._serialize_params(params)}

        # Create hash
        query_string = json.dumps(query_data, sort_keys=True, default=str)
        return hashlib.sha256(query_string.encode()).hexdigest()[:16]

    def _serialize_params(self, params: List[Any]) -> List[Any]:
        """
        Serialize parameters for consistent hashing.

        Args:
            params: Query parameters

        Returns:
            Serializable parameter list
        """
        serialized = []
        for param in params:
            if param is None:
                serialized.append("__null__")
            elif isinstance(param, (str, int, float, bool)):
                serialized.append(param)
            elif isinstance(param, (list, tuple)):
                serialized.append(list(param))
            elif isinstance(param, dict):
                serialized.append(dict(sorted(param.items())))
            else:
                # Convert to string for other types
                serialized.append(str(param))

        return serialized
