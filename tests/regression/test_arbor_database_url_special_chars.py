"""Regression tests for Arbor upstream issue: DATABASE_URL special characters.

The Arbor HR Advisory Platform reported that the Kailash SDK's database
URL handling rejected passwords with special characters (``@``, ``#``,
``%``, ``:``) common in auto-generated database passwords. Passwords had
to be URL-encoded manually, which was not documented.

This test locks in the fix:

1. ``DatabaseConfigBuilder.postgresql/mysql`` URL-encode credentials.
2. ``AsyncDatabaseConfigBuilder.postgresql`` URL-encodes credentials.
3. ``get_masked_connection_string()`` masks passwords that contain
   percent-encoded ``@`` characters.
4. MySQL URL parsing in ``ConnectionManager`` URL-decodes credentials
   so the password is round-tripped to the driver correctly.
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

import pytest
from kailash.config.database_config import (
    AsyncDatabaseConfigBuilder,
    DatabaseConfigBuilder,
)


@pytest.mark.regression
class TestArborDatabaseUrlSpecialCharsBuilders:
    """Builders MUST URL-encode credentials before building the DSN."""

    @pytest.mark.parametrize(
        "password",
        [
            "p@ss",
            "p@ss#word",
            "p%ass",
            "p:ass",
            "p&ass?word",
            "p/ass=word",
            "plain",  # baseline — no special chars
            "",  # empty password
        ],
    )
    def test_postgresql_builder_encodes_password(self, password):
        cfg = DatabaseConfigBuilder.postgresql(
            host="localhost",
            port=5432,
            database="mydb",
            username="user",
            password=password,
        )
        # urlparse must succeed and round-trip the password
        parsed = urlparse(cfg.connection_string)
        assert parsed.scheme == "postgresql"
        assert parsed.hostname == "localhost"
        assert parsed.port == 5432
        assert parsed.username == "user"
        assert unquote(parsed.password or "") == password

    @pytest.mark.parametrize("password", ["p@ss#word", "p%3A:ss", "plain"])
    def test_mysql_builder_encodes_password(self, password):
        cfg = DatabaseConfigBuilder.mysql(
            host="db.internal",
            port=3306,
            database="mydb",
            username="admin",
            password=password,
        )
        parsed = urlparse(cfg.connection_string)
        assert parsed.scheme == "mysql"
        assert parsed.hostname == "db.internal"
        assert parsed.port == 3306
        assert parsed.username == "admin"
        assert unquote(parsed.password or "") == password

    @pytest.mark.parametrize("password", ["p@ss#word", "p:ass&word", "plain"])
    def test_async_postgresql_builder_encodes_password(self, password):
        cfg = AsyncDatabaseConfigBuilder.postgresql(
            host="localhost",
            port=5432,
            database="mydb",
            username="user",
            password=password,
        )
        parsed = urlparse(cfg.connection_string)
        assert parsed.scheme == "postgresql"
        assert parsed.username == "user"
        assert unquote(parsed.password or "") == password

    @pytest.mark.parametrize("password", ["p@ss#word", "plain", ""])
    def test_async_mysql_builder_encodes_password(self, password):
        """AsyncDatabaseConfigBuilder.mysql MUST exist and encode credentials."""
        cfg = AsyncDatabaseConfigBuilder.mysql(
            host="db.internal",
            port=3306,
            database="mydb",
            username="admin",
            password=password,
        )
        parsed = urlparse(cfg.connection_string)
        assert parsed.scheme == "mysql"
        assert parsed.hostname == "db.internal"
        assert parsed.username == "admin"
        assert unquote(parsed.password or "") == password

    def test_username_with_at_sign_is_encoded(self):
        """Usernames with special chars must also encode cleanly."""
        cfg = DatabaseConfigBuilder.postgresql(
            host="localhost",
            database="mydb",
            username="user@corp",
            password="secret",
        )
        parsed = urlparse(cfg.connection_string)
        assert unquote(parsed.username or "") == "user@corp"
        assert parsed.hostname == "localhost"


@pytest.mark.regression
class TestArborDatabaseUrlMasking:
    """get_masked_connection_string MUST mask passwords containing `@`.

    The previous regex locked onto the first `@` character, producing
    incorrect masking when the password contained an encoded `@` (%40)
    followed by the real host separator.
    """

    def test_masked_connection_string_plain_password(self):
        cfg = DatabaseConfigBuilder.postgresql(
            host="localhost",
            port=5432,
            database="mydb",
            username="user",
            password="secret",
        )
        masked = cfg.get_masked_connection_string()
        assert "secret" not in masked
        assert "***" in masked
        assert "localhost" in masked
        assert "5432" in masked

    def test_masked_connection_string_password_with_at(self):
        cfg = DatabaseConfigBuilder.postgresql(
            host="db.prod",
            port=5432,
            database="mydb",
            username="user",
            password="p@ss#word",
        )
        masked = cfg.get_masked_connection_string()
        # The literal password segment must not appear
        assert "p@ss" not in masked
        assert "p%40ss" not in masked
        # Host is preserved for diagnostics
        assert "db.prod" in masked
        assert "5432" in masked
        assert "mydb" in masked

    def test_masked_connection_string_query_string_credentials(self):
        """Query-string passwords MUST also be masked.

        PostgreSQL and MySQL both accept credentials via URL query
        string (``?password=...``). A masker that only redacts userinfo
        leaves these visible in logs.
        """
        from kailash.config.database_config import DatabaseConfig

        raw = (
            "postgresql://user:secret@host:5432/mydb"
            "?sslmode=require&password=shouldnot&sslpassword=alsonot"
            "&sslkey=/tmp/key.pem"
        )
        cfg = DatabaseConfig(
            connection_string=raw,
            database_type="postgresql",
            host="host",
            port=5432,
            database="mydb",
            username="user",
            password="secret",
        )
        masked = cfg.get_masked_connection_string()
        assert "secret" not in masked
        assert "shouldnot" not in masked
        assert "alsonot" not in masked
        assert "/tmp/key.pem" not in masked
        # Non-sensitive query keys are preserved
        assert "sslmode=require" in masked

    def test_masked_connection_string_sqlite_untouched(self):
        from kailash.config.database_config import DatabaseConfig

        cfg = DatabaseConfig(
            connection_string="sqlite:///tmp/app.db",
            database_type="sqlite",
            database="/tmp/app.db",
        )
        assert cfg.get_masked_connection_string() == "sqlite:///tmp/app.db"

    @pytest.mark.parametrize(
        "key", ["password", "sslpassword", "sslkey", "authtoken", "token", "apikey"]
    )
    def test_masked_connection_string_masks_all_sensitive_query_keys(self, key):
        """All masker sites MUST redact the same set of sensitive query keys.

        Round-4 finding: ``get_masked_connection_string`` was missing
        ``authtoken``/``token``/``apikey`` from its sensitive set while
        the shared ``mask_url`` helper had them. A ``?authtoken=leak``
        PostgreSQL URL would therefore leak through core config but be
        caught by the dataflow masker — the two sites must agree.
        """
        from kailash.config.database_config import DatabaseConfig

        raw = f"postgresql://host:5432/db?{key}=leaked&sslmode=require"
        cfg = DatabaseConfig(
            connection_string=raw,
            database_type="postgresql",
            host="host",
            port=5432,
            database="db",
        )
        masked = cfg.get_masked_connection_string()
        assert "leaked" not in masked, f"{key} query value leaked through masker"
        assert "sslmode=require" in masked


@pytest.mark.regression
class TestArborMysqlUrlDecoding:
    """ConnectionManager._init_mysql MUST URL-decode parsed credentials.

    We don't instantiate an aiomysql pool (requires a live MySQL server);
    instead we assert the decoding contract on urlparse+unquote directly,
    mirroring the code path. The production code lives in
    src/kailash/db/connection.py::_init_mysql.
    """

    def test_mysql_url_credentials_decoded(self):
        # Build via the fixed builder, then parse as the runtime does.
        cfg = DatabaseConfigBuilder.mysql(
            host="db.prod",
            port=3306,
            database="app",
            username="admin",
            password="p@ss#word",
        )
        parsed = urlparse(cfg.connection_string)
        decoded_user = unquote(parsed.username or "") if parsed.username else "root"
        decoded_password = unquote(parsed.password or "") if parsed.password else ""
        assert decoded_user == "admin"
        assert decoded_password == "p@ss#word"

    def test_mysql_connection_py_uses_shared_decoder(self):
        """db/connection.py MUST route MySQL credentials through the shared helper.

        Red-team R1 flagged that the session's initial fix inlined
        ``unquote`` + null-byte defense at two sites and missed three
        others. The consolidation replaces inline decode with
        ``decode_userinfo_or_raise`` from ``kailash.utils.url_credentials``
        at every MySQL credential site so the drift is structurally
        impossible.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "kailash"
            / "db"
            / "connection.py"
        ).read_text()

        # Accept both single-line and multi-line import forms
        assert "from kailash.utils.url_credentials import" in source
        assert "decode_userinfo_or_raise" in source
        assert "decode_userinfo_or_raise(parsed" in source

    def test_trust_esa_database_uses_shared_decoder(self):
        """trust/esa/database.py MUST delegate to the shared decoder.

        Red-team flagged C1: the ESA database adapter had a hand-rolled
        MySQL regex parser. The fix routes through
        ``decode_userinfo_or_raise`` so the null-byte defense and
        percent-decoding live in exactly one place.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "kailash"
            / "trust"
            / "esa"
            / "database.py"
        ).read_text()

        # Accept both single-line and multi-line import forms
        assert "from kailash.utils.url_credentials import" in source
        assert "decode_userinfo_or_raise" in source
        assert "decode_userinfo_or_raise(parsed" in source
        # The old regex parser must be gone
        assert (
            r"mysql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)" not in source
        ), "hand-rolled MySQL regex parser must be removed"

    def test_shared_url_decoder_rejects_null_bytes(self):
        """``decode_userinfo_or_raise`` MUST reject null bytes after decode.

        MySQL C client truncates at null byte — this creates an
        auth-bypass primitive if a crafted ``%00``-containing password
        is decoded. The consolidated helper is the single enforcement
        point, so this test exercises it directly rather than grepping
        for inline ``\\x00`` literals at each call site.

        Red-team R1: before the fix, null-byte defense existed only at
        ``src/kailash/db/connection.py`` and ``src/kailash/trust/esa/
        database.py``. Three other decode sites
        (``src/kailash/nodes/data/async_sql.py``,
        ``packages/kailash-dataflow/src/dataflow/core/pool_utils.py``,
        ``packages/kaizen-agents/src/kaizen_agents/patterns/
        state_manager.py``) called ``unquote(parsed.password)`` without
        the check. The shared helper eliminates the drift.
        """
        from urllib.parse import urlparse

        from kailash.utils.url_credentials import decode_userinfo_or_raise

        # Roundtrip through percent-encoding works
        parsed = urlparse("mysql://u:p%23ss@host:3306/db")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "u"
        assert password == "p#ss"

        # Null byte in password must raise
        parsed = urlparse("mysql://u:%00bypass@host/db")
        with pytest.raises(ValueError, match="null byte"):
            decode_userinfo_or_raise(parsed)

        # Null byte in username must raise
        parsed = urlparse("mysql://user%00admin:pass@host/db")
        with pytest.raises(ValueError, match="null byte"):
            decode_userinfo_or_raise(parsed)

        # Default user fallback is applied when userinfo absent
        parsed = urlparse("mysql:///dbonly")
        user, password = decode_userinfo_or_raise(parsed, default_user="root")
        assert user == "root"
        assert password == ""

    def test_shared_preencoder_handles_raw_special_chars(self):
        """``preencode_password_special_chars`` MUST encode raw ``#$@?`` in password.

        Red-team R2 finding E.1: the pre-encoding step existed only in
        ``ConnectionParser._encode_password_special_chars`` and was not
        applied at the five direct-dialect parse sites, so a raw
        ``mysql://user:p#ass@host/db`` URL worked through one code path
        and broke on ``urlparse``'s fragment-splitting in the others.

        This test locks in the contract so R3 cannot re-introduce the
        asymmetry.
        """
        from urllib.parse import unquote, urlparse

        from kailash.utils.url_credentials import preencode_password_special_chars

        # Raw # in password roundtrips cleanly via pre-encoder + urlparse + unquote
        raw = "mysql://user:p#ass@host:3306/db"
        safe = preencode_password_special_chars(raw)
        parsed = urlparse(safe)
        assert parsed.hostname == "host"
        assert parsed.port == 3306
        assert unquote(parsed.password or "") == "p#ass"

        # Already-encoded passwords pass through untouched
        encoded = "mysql://user:p%23ass@host/db"
        assert preencode_password_special_chars(encoded) == encoded

        # @ in password (last @ wins)
        r = preencode_password_special_chars("postgresql://u:p@ss@host/db")
        assert r == "postgresql://u:p%40ss@host/db"

        # None input → empty string (matches legacy contract)
        assert preencode_password_special_chars(None) == ""

        # No credentials → unchanged
        assert preencode_password_special_chars("mysql://host/db") == "mysql://host/db"

        # IPv6 host preserved
        r = preencode_password_special_chars("postgresql://u:p#ass@[::1]:5432/db")
        assert r == "postgresql://u:p%23ass@[::1]:5432/db"

    def test_all_mysql_parse_sites_apply_preencoder(self):
        """Every direct-dialect MySQL parse site MUST call ``preencode_password_special_chars``.

        Red-team R2 E.1: the original session fix left the pre-encoder
        wired only through ``ConnectionParser`` (migration paths). The
        five direct-dialect parsers hit ``urlparse`` with raw user
        input, so a raw ``#$@?`` in password silently broke auth in
        one path and worked in another.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        sites = [
            root / "src" / "kailash" / "db" / "connection.py",
            root / "src" / "kailash" / "trust" / "esa" / "database.py",
            root / "src" / "kailash" / "nodes" / "data" / "async_sql.py",
            root
            / "packages"
            / "kailash-dataflow"
            / "src"
            / "dataflow"
            / "core"
            / "pool_utils.py",
            root
            / "packages"
            / "kaizen-agents"
            / "src"
            / "kaizen_agents"
            / "patterns"
            / "state_manager.py",
        ]
        for site in sites:
            source = site.read_text()
            assert "preencode_password_special_chars" in source, (
                f"{site} missing preencode_password_special_chars call — "
                "every MySQL parse site must pre-encode raw special chars"
            )

    def test_connection_parser_delegates_to_shared_preencoder(self):
        """``ConnectionParser._encode_password_special_chars`` MUST delegate.

        Red-team R2 E.1: the legacy inline implementation in this file
        was the only pre-encoder for months. To prevent drift, it now
        delegates to ``kailash.utils.url_credentials`` so there is
        exactly one source of truth.
        """
        from dataflow.adapters.connection_parser import ConnectionParser

        # Behavioral check: delegation must preserve the legacy contract
        assert (
            ConnectionParser._encode_password_special_chars("mysql://u:p#ss@host/db")
            == "mysql://u:p%23ss@host/db"
        )
        assert (
            ConnectionParser._encode_password_special_chars("mysql://host/db")
            == "mysql://host/db"
        )
        # None roundtrips to "" per legacy contract
        assert ConnectionParser._encode_password_special_chars(None) == ""

    def test_async_sql_node_uses_shared_decoder(self):
        """async_sql.py MySQL init path MUST use the shared decoder.

        Red-team R1 HIGH finding: this site called
        ``unquote(parsed.password)`` without null-byte defense.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "kailash"
            / "nodes"
            / "data"
            / "async_sql.py"
        ).read_text()
        # Accept both single-line and multi-line import forms
        assert "from kailash.utils.url_credentials import" in source
        assert "decode_userinfo_or_raise" in source
        assert "decode_userinfo_or_raise(parsed" in source

    def test_dataflow_pool_utils_uses_shared_decoder(self):
        """dataflow/core/pool_utils.py MySQL probe MUST use the shared decoder.

        Red-team R1 HIGH finding: the pymysql probe inlined ``unquote``
        without null-byte defense, providing a second decode site where
        a crafted URL could bypass auth.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "packages"
            / "kailash-dataflow"
            / "src"
            / "dataflow"
            / "core"
            / "pool_utils.py"
        ).read_text()
        # Accept both single-line and multi-line import forms
        assert "from kailash.utils.url_credentials import" in source
        assert "decode_userinfo_or_raise" in source
        assert "decode_userinfo_or_raise(parsed" in source

    def test_kaizen_state_manager_uses_shared_decoder(self):
        """kaizen_agents state_manager MUST use the shared decoder for both dialects.

        Red-team R1 HIGH finding: both the PostgreSQL and MySQL
        validation paths in ``StateManager`` inlined ``unquote``
        without null-byte defense.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "packages"
            / "kaizen-agents"
            / "src"
            / "kaizen_agents"
            / "patterns"
            / "state_manager.py"
        ).read_text()
        # Accept both single-line and multi-line import forms (formatter-agnostic)
        assert "from kailash.utils.url_credentials import" in source
        assert "decode_userinfo_or_raise" in source
        # Both dialects (PostgreSQL + MySQL) must call the helper
        assert source.count("decode_userinfo_or_raise(parsed") >= 2

    def test_connection_parser_rejects_null_byte_credentials(self):
        """``ConnectionParser.parse_connection_string`` rejects \\x00 in creds.

        Secondary defense: this is the dict-returning entry point used
        by migration code paths. The null-byte check is inlined at this
        site rather than delegated to the shared helper because the
        return shape differs.
        """
        from dataflow.adapters.connection_parser import ConnectionParser
        from dataflow.adapters.exceptions import AdapterError

        with pytest.raises(AdapterError, match="null byte"):
            ConnectionParser.parse_connection_string("postgresql://u:%00bypass@host/db")
        with pytest.raises(AdapterError, match="null byte"):
            ConnectionParser.parse_connection_string(
                "postgresql://user%00admin:pass@host/db"
            )


@pytest.mark.regression
class TestArborSharedMaskUrl:
    """``dataflow.utils.masking.mask_url`` is the canonical URL masker.

    Nexus, DataFlow fabric, Redis backends, and the MongoDB adapter
    all delegate to it. It MUST:

    1. Mask ``user:password@`` userinfo (existing contract).
    2. Mask ``?password=``/``?sslpassword=``/``?sslkey=`` query fields
       (round-2 alignment with ``DatabaseConfig.get_masked_connection_string``).
    3. Preserve MongoDB replica-set URLs (comma-separated netloc)
       without degrading to ``<unparseable>``.
    4. Return input verbatim for URLs with no credentials at all.
    """

    def test_mask_url_userinfo_only(self):
        from dataflow.utils.masking import mask_url

        assert (
            mask_url("redis://alice:wonderland@localhost:6379/0")
            == "redis://***@localhost:6379/0"
        )

    def test_mask_url_masks_query_string_password(self):
        from dataflow.utils.masking import mask_url

        masked = mask_url("postgresql://host:5432/db?password=leak&sslmode=require")
        assert "leak" not in masked
        assert "sslmode=require" in masked

    def test_mask_url_mongodb_replica_set(self):
        """Replica-set URLs (comma netloc) must not degrade to <unparseable>."""
        from dataflow.utils.masking import mask_url

        raw = (
            "mongodb://user:secret@host1:27017,host2:27017,host3:27017"
            "/mydb?replicaSet=rs0&authSource=admin"
        )
        masked = mask_url(raw)
        assert masked != "<unparseable>"
        assert "secret" not in masked
        assert "host1:27017,host2:27017,host3:27017" in masked
        assert "replicaSet=rs0" in masked

    def test_mask_url_mongodb_replica_set_with_query_password(self):
        from dataflow.utils.masking import mask_url

        raw = "mongodb://h1,h2/db?password=leak&replicaSet=rs0"
        masked = mask_url(raw)
        assert "leak" not in masked
        assert "replicaSet=rs0" in masked

    def test_mask_url_no_credentials_returns_verbatim(self):
        from dataflow.utils.masking import mask_url

        assert (
            mask_url("postgresql://localhost:5432/db")
            == "postgresql://localhost:5432/db"
        )
        assert mask_url("sqlite:///tmp/app.db") == "sqlite:///tmp/app.db"

    def test_mask_url_none_and_empty(self):
        from dataflow.utils.masking import mask_url

        assert mask_url(None) == ""
        assert mask_url("") == ""

    def test_mask_url_multi_host_with_query_no_path(self):
        """Replica-set URL with query but NO path — query must still mask.

        Round-3 H3: the multi-host parser used to partition on '/'
        BEFORE peeling the query, so ``mongodb://u:p@h1,h2?password=leak``
        baked ``?password=leak`` into the authority and the query
        masker never ran. The query must be peeled first.
        """
        from dataflow.utils.masking import mask_url

        raw = "mongodb://u:p@h1,h2?password=leak&replicaSet=rs0"
        masked = mask_url(raw)
        assert "leak" not in masked
        assert "replicaSet=rs0" in masked
        assert "h1,h2" in masked

    def test_mask_url_multi_host_with_fragment(self):
        """Replica-set URL with fragment — fragment must not be eaten."""
        from dataflow.utils.masking import mask_url

        raw = "mongodb://u:p@h1,h2/db#section"
        masked = mask_url(raw)
        assert "#section" in masked
        # Userinfo still masked
        assert ":p@" not in masked

    def test_mask_url_multi_host_no_userinfo_no_query(self):
        """Replica-set URL with nothing to mask — return verbatim."""
        from dataflow.utils.masking import mask_url

        raw = "mongodb://host1,host2/db?replicaSet=rs0"
        assert mask_url(raw) == raw


@pytest.mark.regression
class TestArborRateLimitRedisMasker:
    """``_sanitize_url`` in both Redis rate-limit backends MUST mask both
    userinfo and the full set of sensitive query-string keys, including
    sslpassword/sslkey (aligned with the shared ``mask_url`` key set).
    """

    @pytest.mark.parametrize(
        "module_path",
        [
            "kailash.trust.rate_limit.backends.redis",
            "nexus.auth.rate_limit.backends.redis",
        ],
    )
    def test_redis_sanitize_url_masks_query_string_sslpassword(self, module_path):
        import importlib

        mod = importlib.import_module(module_path)
        # Locate the backend class in the module — both expose a class
        # whose _sanitize_url staticmethod is the canonical masker for
        # that package.
        backend_cls = None
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "_sanitize_url")
                and attr.__module__ == module_path
            ):
                backend_cls = attr
                break
        assert (
            backend_cls is not None
        ), f"no backend class with _sanitize_url in {module_path}"

        raw = "redis://user:pw@host:6379/0?sslpassword=ssslong&sslkey=/tmp/k.pem"
        masked = backend_cls._sanitize_url(raw)
        assert "pw" not in masked
        assert "ssslong" not in masked
        assert "/tmp/k.pem" not in masked

    @pytest.mark.parametrize(
        "module_path",
        [
            "kailash.trust.rate_limit.backends.redis",
            "nexus.auth.rate_limit.backends.redis",
        ],
    )
    def test_redis_sanitize_url_uses_distinct_sentinel_on_parse_error(
        self, module_path
    ):
        """The exception fallback MUST return ``"<unparseable redis url>"``.

        Red-team R1 flagged that returning ``"redis://***"`` on parse
        failure was indistinguishable from a successfully-masked URL,
        so an operator could not tell whether credentials were
        stripped or the URL was malformed. R2 LOW follow-up: lock in
        the sentinel with a direct test. The malformed IPv6 URL
        ``redis://[::1`` causes ``urllib.parse.urlparse`` to raise
        ``ValueError: Invalid IPv6 URL`` which trips the except branch.
        """
        import importlib

        mod = importlib.import_module(module_path)
        backend_cls = None
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "_sanitize_url")
                and attr.__module__ == module_path
            ):
                backend_cls = attr
                break
        assert backend_cls is not None

        # Malformed IPv6 literal — urlparse raises ValueError on this
        result = backend_cls._sanitize_url("redis://[::1")
        assert result == "<unparseable redis url>", (
            f"expected distinct sentinel for parse failure, got {result!r} "
            "— 'redis://***' is BLOCKED because it collides with the "
            "successful-mask form"
        )

    @pytest.mark.parametrize(
        "module_path",
        [
            "kailash.trust.rate_limit.backends.redis",
            "nexus.auth.rate_limit.backends.redis",
        ],
    )
    def test_redis_sanitize_url_userinfo_form_matches_shared_helpers(self, module_path):
        """The userinfo mask MUST use ``***@host`` form.

        Red-team R1 B.2 finding: the Redis backends stripped userinfo
        entirely (``host:port`` with no ``@``) while the other three
        masking helpers (``database_config.get_masked_connection_string``,
        ``dataflow.utils.masking.mask_url``) produced ``***@host``. The
        drift meant an operator grepping for ``***@`` to audit masked
        URLs would miss Redis logs. R1 fixed both Redis backends to use
        ``***@host`` — this test locks in the alignment.
        """
        import importlib

        mod = importlib.import_module(module_path)
        backend_cls = None
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "_sanitize_url")
                and attr.__module__ == module_path
            ):
                backend_cls = attr
                break
        assert backend_cls is not None

        masked = backend_cls._sanitize_url("redis://:secret@host:6379/0")
        assert masked == "redis://***@host:6379/0", (
            f"Redis backend must use ***@host form (was {masked!r}) — "
            "drift from the other 3 masking helpers makes grep-based "
            "audits miss Redis logs"
        )


@pytest.mark.regression
class TestArborRegistryMetadataCopy:
    """The registry stores a shallow COPY of caller metadata so
    post-registration mutations don't leak into the registry view.
    """

    def test_registry_not_aliased_to_caller_dict(self):
        from nexus.registry import HandlerRegistry

        reg = HandlerRegistry()
        metadata = {"version": "1.0", "author": "alice"}
        reg.register_workflow("wf", object(), metadata=metadata)

        # Caller mutates their dict after register() returns.
        metadata["version"] = "HIJACKED"
        metadata["injected"] = "by_caller"

        stored = reg.get_workflow_metadata("wf")
        assert stored["version"] == "1.0"
        assert "injected" not in stored


@pytest.mark.regression
class TestArborNexusMetadataRegisterOrdering:
    """Fix-3 ordering: validation runs BEFORE workflow.metadata mutation.

    If caller supplies invalid metadata (oversize, non-JSON-serializable),
    the ValueError must surface AND the workflow object must remain
    untouched. A retry with corrected metadata must not carry garbage
    from the failed attempt.
    """

    def _bare_nexus(self):
        from nexus.core import Nexus
        from nexus.registry import HandlerRegistry

        app = Nexus.__new__(Nexus)
        app._registry = HandlerRegistry()
        app._http_transport = type("T", (), {"gateway": None})()
        app._performance_metrics = {"workflow_registration_time": []}
        app._api_port = 8000
        return app

    def _fake_workflow(self, metadata=None):
        class _FakeWorkflow:
            pass

        wf = _FakeWorkflow()
        wf.metadata = dict(metadata) if metadata else {}
        return wf

    def test_register_fails_before_mutating_workflow_on_oversize_metadata(self):
        app = self._bare_nexus()
        wf = self._fake_workflow(metadata={"preexisting": "yes"})

        with pytest.raises(ValueError, match="exceeds"):
            app.register("wf", wf, metadata={"blob": "x" * (100 * 1024)})

        # The workflow's metadata must be exactly what it was before
        # the failed call — no partial writes, no trace of the oversize
        # payload.
        assert wf.metadata == {"preexisting": "yes"}
        assert "blob" not in wf.metadata

    def test_register_does_not_share_metadata_across_same_workflow(self):
        """Registering the same workflow under two names with different
        metadata must NOT alias — mutating one registration's metadata
        must not affect the other.
        """
        app = self._bare_nexus()
        wf = self._fake_workflow()

        app.register("a", wf, metadata={"source": "a"})
        # At this point wf.metadata == {"source": "a"}
        # Registering under a second name with different metadata must
        # produce a fresh merged dict, not mutate the same reference.
        original_ref = wf.metadata
        app.register("b", wf, metadata={"source": "b"})
        # The second registration replaces wf.metadata with a new dict
        # containing the merged view — the previous dict reference is
        # NOT mutated, so anyone who captured it still sees the old
        # value.
        assert original_ref.get("source") == "a"
        assert wf.metadata["source"] == "b"


@pytest.mark.regression
class TestArborJwtDelegateDefense:
    """JWT delegate methods MUST fail cleanly when ``_validator`` is missing.

    Red-team R1 C.2: the delegation shims at
    ``packages/kailash-nexus/src/nexus/auth/jwt.py:282-316`` raised
    an opaque ``AttributeError: 'NoneType' object has no attribute ...``
    when a caller bypassed ``__init__`` via ``__new__`` and forgot to
    assign ``mw._validator``. The R3 fix adds a typed ``RuntimeError``
    at each delegate that names the root cause unambiguously.
    """

    def _bare_middleware(self):
        """Construct a JWTMiddleware via ``__new__`` without _validator."""
        from nexus.auth.jwt import JWTMiddleware

        mw = JWTMiddleware.__new__(JWTMiddleware)
        # Deliberately do NOT assign _validator — this reproduces the
        # failure mode the test suite hit before the fix.
        return mw

    def test_create_access_token_raises_typed_error_when_validator_missing(self):
        mw = self._bare_middleware()
        with pytest.raises(RuntimeError, match="_validator is not set"):
            mw.create_access_token(user_id="u1")

    def test_create_refresh_token_raises_typed_error_when_validator_missing(self):
        mw = self._bare_middleware()
        with pytest.raises(RuntimeError, match="_validator is not set"):
            mw.create_refresh_token(user_id="u1")

    def test_verify_token_raises_typed_error_when_validator_missing(self):
        mw = self._bare_middleware()
        with pytest.raises(RuntimeError, match="_validator is not set"):
            mw._verify_token("some.jwt.token")

    def test_create_user_from_payload_raises_typed_error_when_validator_missing(
        self,
    ):
        mw = self._bare_middleware()
        with pytest.raises(RuntimeError, match="_validator is not set"):
            mw._create_user_from_payload({"sub": "u1"})

    def test_is_path_exempt_raises_typed_error_when_validator_missing(self):
        mw = self._bare_middleware()
        with pytest.raises(RuntimeError, match="_validator is not set"):
            mw._is_path_exempt("/health")
