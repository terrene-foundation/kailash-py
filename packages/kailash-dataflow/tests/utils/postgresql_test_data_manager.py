"""
PostgreSQL Test Data Manager - Phase 1B Component 2 Utilities

Comprehensive test data lifecycle management for PostgreSQL integration testing.

Features:
- Test data setup and teardown
- Fixture data management
- Performance data generation
- Concurrent access test data
- Schema validation test data
"""

import asyncio
import json
import logging
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import asyncpg

    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

logger = logging.getLogger(__name__)


class TestDataType(Enum):
    """Types of test data."""

    MINIMAL = "minimal"
    COMPREHENSIVE = "comprehensive"
    PERFORMANCE = "performance"
    STRESS = "stress"
    CONCURRENT = "concurrent"


@dataclass
class TestDataConfig:
    """Configuration for test data generation."""

    data_type: TestDataType
    record_count: int
    batch_size: int = 100
    include_relationships: bool = True
    include_indexes: bool = True
    generate_realistic_data: bool = True
    concurrent_users: int = 1
    performance_metrics: Dict[str, Any] = field(default_factory=dict)


class PostgreSQLTestDataManager:
    """
    Comprehensive test data management for PostgreSQL testing.

    Manages test data lifecycle, fixtures, and performance data generation
    for integration and E2E testing scenarios.
    """

    def __init__(self, database_url: str):
        """
        Initialize test data manager.

        Args:
            database_url: PostgreSQL database connection URL
        """
        if not ASYNCPG_AVAILABLE:
            raise ImportError("asyncpg required for PostgreSQL test data management")

        self.database_url = database_url
        self._connection_pool: Optional[asyncpg.Pool] = None
        self._test_tables: List[str] = []
        self._test_data_cache: Dict[str, Any] = {}

        # Realistic test data generators
        self._sample_names = [
            "Alice Johnson",
            "Bob Smith",
            "Carol Williams",
            "David Brown",
            "Emma Davis",
            "Frank Miller",
            "Grace Wilson",
            "Henry Moore",
            "Ivy Taylor",
            "Jack Anderson",
            "Kate Thomas",
            "Liam Jackson",
        ]

        self._sample_emails = [
            "user1@example.com",
            "user2@test.org",
            "user3@demo.net",
            "test.user@company.com",
            "developer@startup.io",
            "admin@enterprise.com",
        ]

        self._sample_categories = [
            "Technology",
            "Science",
            "Health",
            "Education",
            "Business",
            "Entertainment",
            "Sports",
            "Travel",
            "Food",
            "Art",
        ]

        self._sample_content = [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco.",
            "Duis aute irure dolor in reprehenderit in voluptate velit esse.",
            "Excepteur sint occaecat cupidatat non proident sunt in culpa.",
        ]

    async def initialize(self) -> None:
        """Initialize connection pool and prepare for data management."""
        logger.info("Initializing PostgreSQL test data manager")

        try:
            self._connection_pool = await asyncpg.create_pool(
                self.database_url, min_size=2, max_size=10, command_timeout=60
            )
            logger.info("Connection pool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    async def cleanup(self) -> None:
        """Clean up connection pool and resources."""
        if self._connection_pool:
            await self._connection_pool.close()
            logger.info("Connection pool closed")

    async def setup_test_schema(self, schema_name: str = "public") -> None:
        """
        Set up comprehensive test schema for testing.

        Args:
            schema_name: Database schema name
        """
        logger.info(f"Setting up test schema: {schema_name}")

        async with self._connection_pool.acquire() as conn:
            # Create comprehensive test tables
            await self._create_users_table(conn)
            await self._create_categories_table(conn)
            await self._create_posts_table(conn)
            await self._create_comments_table(conn)
            await self._create_tags_table(conn)
            await self._create_audit_log_table(conn)

            # Create performance test tables
            await self._create_performance_tables(conn)

            # Create indexes for performance
            await self._create_test_indexes(conn)

            logger.info("Test schema setup completed")

    async def _create_users_table(self, conn) -> None:
        """Create users table for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                bio TEXT,
                avatar_url VARCHAR(500),
                is_active BOOLEAN DEFAULT TRUE,
                email_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """
        )
        self._test_tables.append("test_users")

    async def _create_categories_table(self, conn) -> None:
        """Create categories table for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                parent_id INTEGER REFERENCES test_categories(id),
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self._test_tables.append("test_categories")

    async def _create_posts_table(self, conn) -> None:
        """Create posts table for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                slug VARCHAR(200) UNIQUE NOT NULL,
                content TEXT,
                excerpt TEXT,
                author_id INTEGER REFERENCES test_users(id) NOT NULL,
                category_id INTEGER REFERENCES test_categories(id),
                status VARCHAR(20) DEFAULT 'draft',
                view_count INTEGER DEFAULT 0,
                like_count INTEGER DEFAULT 0,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self._test_tables.append("test_posts")

    async def _create_comments_table(self, conn) -> None:
        """Create comments table for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_comments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER REFERENCES test_posts(id) NOT NULL,
                author_id INTEGER REFERENCES test_users(id) NOT NULL,
                parent_id INTEGER REFERENCES test_comments(id),
                content TEXT NOT NULL,
                is_approved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self._test_tables.append("test_comments")

    async def _create_tags_table(self, conn) -> None:
        """Create tags and post_tags tables for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_tags (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                color VARCHAR(7) DEFAULT '#000000',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_post_tags (
                post_id INTEGER REFERENCES test_posts(id),
                tag_id INTEGER REFERENCES test_tags(id),
                PRIMARY KEY (post_id, tag_id)
            )
        """
        )
        self._test_tables.extend(["test_tags", "test_post_tags"])

    async def _create_audit_log_table(self, conn) -> None:
        """Create audit log table for testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_audit_log (
                id SERIAL PRIMARY KEY,
                table_name VARCHAR(100) NOT NULL,
                record_id INTEGER NOT NULL,
                action VARCHAR(20) NOT NULL,
                old_data JSONB,
                new_data JSONB,
                user_id INTEGER REFERENCES test_users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self._test_tables.append("test_audit_log")

    async def _create_performance_tables(self, conn) -> None:
        """Create tables specifically for performance testing."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_performance_large (
                id SERIAL PRIMARY KEY,
                data_field_1 VARCHAR(500),
                data_field_2 TEXT,
                numeric_field_1 INTEGER,
                numeric_field_2 DECIMAL(10,2),
                boolean_field BOOLEAN DEFAULT FALSE,
                timestamp_field TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_field JSONB
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_performance_small (
                id SERIAL PRIMARY KEY,
                code VARCHAR(10) UNIQUE,
                name VARCHAR(100),
                value INTEGER
            )
        """
        )
        self._test_tables.extend(["test_performance_large", "test_performance_small"])

    async def _create_test_indexes(self, conn) -> None:
        """Create indexes for performance testing."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON test_users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON test_users(email)",
            "CREATE INDEX IF NOT EXISTS idx_posts_author ON test_posts(author_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON test_posts(category_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_status ON test_posts(status)",
            "CREATE INDEX IF NOT EXISTS idx_posts_created ON test_posts(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_comments_post ON test_comments(post_id)",
            "CREATE INDEX IF NOT EXISTS idx_performance_large_timestamp ON test_performance_large(timestamp_field)",
            "CREATE INDEX IF NOT EXISTS idx_performance_small_code ON test_performance_small(code)",
        ]

        for index_sql in indexes:
            await conn.execute(index_sql)

    async def generate_test_data(self, config: TestDataConfig) -> Dict[str, int]:
        """
        Generate test data based on configuration.

        Args:
            config: Test data configuration

        Returns:
            Dictionary with record counts per table
        """
        logger.info(f"Generating {config.data_type.value} test data")
        start_time = time.perf_counter()

        record_counts = {}

        try:
            async with self._connection_pool.acquire() as conn:
                # Generate data based on type
                if config.data_type == TestDataType.MINIMAL:
                    record_counts = await self._generate_minimal_data(conn, config)
                elif config.data_type == TestDataType.COMPREHENSIVE:
                    record_counts = await self._generate_comprehensive_data(
                        conn, config
                    )
                elif config.data_type == TestDataType.PERFORMANCE:
                    record_counts = await self._generate_performance_data(conn, config)
                elif config.data_type == TestDataType.STRESS:
                    record_counts = await self._generate_stress_data(conn, config)
                elif config.data_type == TestDataType.CONCURRENT:
                    record_counts = await self._generate_concurrent_data(conn, config)

                generation_time = time.perf_counter() - start_time
                config.performance_metrics["generation_time"] = generation_time
                config.performance_metrics["records_per_second"] = (
                    sum(record_counts.values()) / generation_time
                )

                logger.info(
                    f"Generated {sum(record_counts.values())} records in {generation_time:.3f}s "
                    f"({config.performance_metrics['records_per_second']:.1f} records/sec)"
                )

                return record_counts

        except Exception as e:
            logger.error(f"Failed to generate test data: {e}")
            raise

    async def _generate_minimal_data(
        self, conn, config: TestDataConfig
    ) -> Dict[str, int]:
        """Generate minimal test data for basic testing."""
        record_counts = {}

        # Create 5 users
        user_ids = []
        for i in range(5):
            user_id = await conn.fetchval(
                """
                INSERT INTO test_users (username, email, password_hash, first_name, last_name)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """,
                f"user_{i}",
                f"user{i}@test.com",
                "hashed_password",
                self._sample_names[i % len(self._sample_names)].split()[0],
                self._sample_names[i % len(self._sample_names)].split()[1],
            )
            user_ids.append(user_id)
        record_counts["test_users"] = 5

        # Create 3 categories
        category_ids = []
        for i in range(3):
            category_id = await conn.fetchval(
                """
                INSERT INTO test_categories (name, slug, description)
                VALUES ($1, $2, $3)
                RETURNING id
            """,
                self._sample_categories[i],
                f"category-{i}",
                f"Description for {self._sample_categories[i]}",
            )
            category_ids.append(category_id)
        record_counts["test_categories"] = 3

        # Create 10 posts
        for i in range(10):
            await conn.execute(
                """
                INSERT INTO test_posts (title, slug, content, author_id, category_id, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                f"Test Post {i}",
                f"test-post-{i}",
                f"Content for test post {i}",
                random.choice(user_ids),
                random.choice(category_ids),
                random.choice(["draft", "published"]),
            )
        record_counts["test_posts"] = 10

        return record_counts

    async def _generate_comprehensive_data(
        self, conn, config: TestDataConfig
    ) -> Dict[str, int]:
        """Generate comprehensive test data for thorough testing."""
        record_counts = {}

        # Generate users
        user_count = min(config.record_count // 10, 100)  # 10% of records, max 100
        user_ids = await self._generate_users_batch(conn, user_count)
        record_counts["test_users"] = user_count

        # Generate categories
        category_count = min(user_count // 5, 20)  # Fewer categories than users
        category_ids = await self._generate_categories_batch(conn, category_count)
        record_counts["test_categories"] = category_count

        # Generate tags
        tag_count = min(user_count // 2, 50)
        tag_ids = await self._generate_tags_batch(conn, tag_count)
        record_counts["test_tags"] = tag_count

        # Generate posts
        post_count = min(config.record_count // 2, 1000)
        post_ids = await self._generate_posts_batch(
            conn, post_count, user_ids, category_ids
        )
        record_counts["test_posts"] = post_count

        # Generate post-tag relationships
        if config.include_relationships:
            post_tag_count = await self._generate_post_tags_batch(
                conn, post_ids, tag_ids
            )
            record_counts["test_post_tags"] = post_tag_count

        # Generate comments
        comment_count = min(config.record_count, 2000)
        comments_created = await self._generate_comments_batch(
            conn, comment_count, post_ids, user_ids
        )
        record_counts["test_comments"] = comments_created

        return record_counts

    async def _generate_performance_data(
        self, conn, config: TestDataConfig
    ) -> Dict[str, int]:
        """Generate performance test data for load testing."""
        record_counts = {}

        # Generate large dataset for performance testing
        large_records = await self._generate_performance_large_batch(
            conn, config.record_count
        )
        record_counts["test_performance_large"] = large_records

        # Generate smaller lookup table
        small_records = await self._generate_performance_small_batch(
            conn, config.record_count // 100
        )
        record_counts["test_performance_small"] = small_records

        return record_counts

    async def _generate_stress_data(
        self, conn, config: TestDataConfig
    ) -> Dict[str, int]:
        """Generate stress test data for high-load scenarios."""
        # Use performance data generation with higher volume
        stress_config = TestDataConfig(
            data_type=TestDataType.PERFORMANCE,
            record_count=config.record_count * 5,  # 5x more data for stress testing
            batch_size=config.batch_size * 2,
        )

        return await self._generate_performance_data(conn, stress_config)

    async def _generate_concurrent_data(
        self, conn, config: TestDataConfig
    ) -> Dict[str, int]:
        """Generate data for concurrent access testing."""
        record_counts = {}

        # Create data that will be accessed concurrently
        concurrent_tasks = []

        for user_batch in range(config.concurrent_users):

            async def generate_user_batch(batch_id):
                batch_conn = await asyncpg.connect(self.database_url)
                try:
                    batch_records = config.record_count // config.concurrent_users

                    # Generate users for this batch
                    user_ids = []
                    for i in range(batch_records // 10):
                        user_id = await batch_conn.fetchval(
                            """
                            INSERT INTO test_users (username, email, password_hash)
                            VALUES ($1, $2, $3)
                            RETURNING id
                        """,
                            f"concurrent_user_{batch_id}_{i}",
                            f"concurrent{batch_id}_{i}@test.com",
                            "password",
                        )
                        user_ids.append(user_id)

                    return len(user_ids)
                finally:
                    await batch_conn.close()

            concurrent_tasks.append(generate_user_batch(user_batch))

        # Execute concurrent data generation
        batch_results = await asyncio.gather(*concurrent_tasks)
        record_counts["test_users"] = sum(batch_results)

        return record_counts

    async def _generate_users_batch(self, conn, count: int) -> List[int]:
        """Generate batch of users."""
        user_ids = []

        for i in range(count):
            name_parts = random.choice(self._sample_names).split()
            user_id = await conn.fetchval(
                """
                INSERT INTO test_users (
                    username, email, password_hash, first_name, last_name, bio, is_active
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """,
                f"user_{i}_{random.randint(1000, 9999)}",
                f"user{i}@{random.choice(['test.com', 'example.org', 'demo.net'])}",
                "hashed_password",
                name_parts[0],
                name_parts[1],
                random.choice(self._sample_content),
                random.choice([True, False]),
            )
            user_ids.append(user_id)

        return user_ids

    async def _generate_categories_batch(self, conn, count: int) -> List[int]:
        """Generate batch of categories."""
        category_ids = []

        for i in range(count):
            category = self._sample_categories[i % len(self._sample_categories)]
            category_id = await conn.fetchval(
                """
                INSERT INTO test_categories (name, slug, description, sort_order)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                f"{category} {i}",
                f"{category.lower().replace(' ', '-')}-{i}",
                f"Test description for {category}",
                i,
            )
            category_ids.append(category_id)

        return category_ids

    async def _generate_tags_batch(self, conn, count: int) -> List[int]:
        """Generate batch of tags."""
        tag_ids = []

        tag_names = [
            "python",
            "postgresql",
            "testing",
            "docker",
            "api",
            "web",
            "backend",
            "database",
            "performance",
            "scalability",
            "security",
            "devops",
        ]

        for i in range(count):
            tag_name = f"{random.choice(tag_names)}-{i}"
            tag_id = await conn.fetchval(
                """
                INSERT INTO test_tags (name, color)
                VALUES ($1, $2)
                RETURNING id
            """,
                tag_name,
                f"#{random.randint(100000, 999999):06x}",
            )
            tag_ids.append(tag_id)

        return tag_ids

    async def _generate_posts_batch(
        self, conn, count: int, user_ids: List[int], category_ids: List[int]
    ) -> List[int]:
        """Generate batch of posts."""
        post_ids = []

        for i in range(count):
            post_id = await conn.fetchval(
                """
                INSERT INTO test_posts (
                    title, slug, content, excerpt, author_id, category_id,
                    status, view_count, like_count
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """,
                f"Test Post {i}: Advanced Testing",
                f"test-post-{i}-{random.randint(1000, 9999)}",
                f"Comprehensive content for test post {i}. {random.choice(self._sample_content)}",
                f"Excerpt for test post {i}",
                random.choice(user_ids),
                random.choice(category_ids) if category_ids else None,
                random.choice(["draft", "published", "archived"]),
                random.randint(0, 1000),
                random.randint(0, 100),
            )
            post_ids.append(post_id)

        return post_ids

    async def _generate_post_tags_batch(
        self, conn, post_ids: List[int], tag_ids: List[int]
    ) -> int:
        """Generate post-tag relationships."""
        relationships_created = 0

        for post_id in post_ids:
            # Each post gets 1-5 random tags
            post_tag_count = random.randint(1, min(5, len(tag_ids)))
            selected_tags = random.sample(tag_ids, post_tag_count)

            for tag_id in selected_tags:
                try:
                    await conn.execute(
                        """
                        INSERT INTO test_post_tags (post_id, tag_id)
                        VALUES ($1, $2)
                    """,
                        post_id,
                        tag_id,
                    )
                    relationships_created += 1
                except:
                    # Ignore duplicate key errors
                    pass

        return relationships_created

    async def _generate_comments_batch(
        self, conn, count: int, post_ids: List[int], user_ids: List[int]
    ) -> int:
        """Generate batch of comments."""
        comments_created = 0

        for i in range(count):
            if not post_ids or not user_ids:
                break

            try:
                await conn.execute(
                    """
                    INSERT INTO test_comments (post_id, author_id, content, is_approved)
                    VALUES ($1, $2, $3, $4)
                """,
                    random.choice(post_ids),
                    random.choice(user_ids),
                    f"Test comment {i}: {random.choice(self._sample_content)}",
                    random.choice([True, False]),
                )
                comments_created += 1
            except Exception as e:
                logger.warning(f"Failed to create comment {i}: {e}")

        return comments_created

    async def _generate_performance_large_batch(self, conn, count: int) -> int:
        """Generate large performance test records."""
        records_created = 0

        for i in range(count):
            try:
                await conn.execute(
                    """
                    INSERT INTO test_performance_large (
                        data_field_1, data_field_2, numeric_field_1, numeric_field_2,
                        boolean_field, json_field
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    f"Performance data {i} {'x' * random.randint(10, 100)}",
                    f"Large text content for performance testing: {random.choice(self._sample_content) * 5}",
                    random.randint(1, 1000000),
                    random.uniform(1.0, 1000.0),
                    random.choice([True, False]),
                    json.dumps(
                        {"test_data": i, "random_value": random.randint(1, 100)}
                    ),
                )
                records_created += 1
            except Exception as e:
                logger.warning(f"Failed to create performance record {i}: {e}")

        return records_created

    async def _generate_performance_small_batch(self, conn, count: int) -> int:
        """Generate small lookup table records."""
        records_created = 0

        for i in range(count):
            try:
                await conn.execute(
                    """
                    INSERT INTO test_performance_small (code, name, value)
                    VALUES ($1, $2, $3)
                """,
                    f"CODE{i:04d}",
                    f"Performance Item {i}",
                    random.randint(1, 1000),
                )
                records_created += 1
            except Exception as e:
                logger.warning(f"Failed to create small performance record {i}: {e}")

        return records_created

    async def cleanup_test_data(self) -> None:
        """Clean up all test data."""
        logger.info("Cleaning up test data")

        async with self._connection_pool.acquire() as conn:
            # Drop tables in reverse dependency order
            tables_to_drop = [
                "test_post_tags",
                "test_comments",
                "test_posts",
                "test_tags",
                "test_categories",
                "test_users",
                "test_audit_log",
                "test_performance_large",
                "test_performance_small",
            ]

            for table in tables_to_drop:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                except Exception as e:
                    logger.warning(f"Failed to drop table {table}: {e}")

            self._test_tables.clear()
            self._test_data_cache.clear()

        logger.info("Test data cleanup completed")

    async def verify_data_integrity(self) -> Dict[str, Any]:
        """Verify test data integrity and relationships."""
        logger.info("Verifying test data integrity")

        integrity_report = {
            "tables_checked": 0,
            "integrity_issues": [],
            "record_counts": {},
            "relationship_checks": {},
        }

        async with self._connection_pool.acquire() as conn:
            # Check record counts
            for table in self._test_tables:
                try:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    integrity_report["record_counts"][table] = count
                    integrity_report["tables_checked"] += 1
                except Exception as e:
                    integrity_report["integrity_issues"].append(
                        f"Failed to count {table}: {e}"
                    )

            # Check referential integrity
            integrity_checks = [
                ("test_posts", "author_id", "test_users", "id"),
                ("test_posts", "category_id", "test_categories", "id"),
                ("test_comments", "post_id", "test_posts", "id"),
                ("test_comments", "author_id", "test_users", "id"),
                ("test_post_tags", "post_id", "test_posts", "id"),
                ("test_post_tags", "tag_id", "test_tags", "id"),
            ]

            for child_table, child_col, parent_table, parent_col in integrity_checks:
                try:
                    orphans = await conn.fetchval(
                        f"""
                        SELECT COUNT(*) FROM {child_table} c
                        LEFT JOIN {parent_table} p ON c.{child_col} = p.{parent_col}
                        WHERE c.{child_col} IS NOT NULL AND p.{parent_col} IS NULL
                    """
                    )

                    check_key = (
                        f"{child_table}.{child_col} -> {parent_table}.{parent_col}"
                    )
                    integrity_report["relationship_checks"][check_key] = orphans

                    if orphans > 0:
                        integrity_report["integrity_issues"].append(
                            f"Found {orphans} orphaned records in {check_key}"
                        )

                except Exception as e:
                    integrity_report["integrity_issues"].append(
                        f"Failed to check {check_key}: {e}"
                    )

        logger.info(
            f"Integrity check completed: {len(integrity_report['integrity_issues'])} issues found"
        )
        return integrity_report

    def get_sample_data_for_testing(self) -> Dict[str, Any]:
        """Get sample data structures for testing."""
        return {
            "sample_user": {
                "username": "test_user",
                "email": "test@example.com",
                "password_hash": "hashed_password",
                "first_name": "Test",
                "last_name": "User",
            },
            "sample_category": {
                "name": "Test Category",
                "slug": "test-category",
                "description": "A test category",
            },
            "sample_post": {
                "title": "Test Post",
                "slug": "test-post",
                "content": "Test post content",
                "status": "published",
            },
            "sample_comment": {"content": "Test comment content", "is_approved": True},
            "sample_tag": {"name": "test-tag", "color": "#ff0000"},
        }
