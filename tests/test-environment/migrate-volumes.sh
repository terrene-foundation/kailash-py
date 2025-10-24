#!/bin/bash
# Migrate test-environment volumes to kailash_sdk volumes
# Preserves all existing data

set -e

echo "🔄 Migrating Docker volumes from test-environment to kailash_sdk..."
echo ""

# Volume pairs: old_name:new_name
VOLUME_PAIRS=(
    "test-environment_postgres_test_data:kailash_sdk_postgres_test_data"
    "test-environment_mysql_test_data:kailash_sdk_mysql_test_data"
    "test-environment_mongodb_test_data:kailash_sdk_mongodb_test_data"
    "test-environment_ollama_models:kailash_sdk_ollama_models"
    "test-environment_qdrant_test_data:kailash_sdk_qdrant_test_data"
    "test-environment_minio_test_data:kailash_sdk_minio_test_data"
    "test-environment_elasticsearch_data:kailash_sdk_elasticsearch_data"
    "test-environment_kubernetes_data:kailash_sdk_kubernetes_data"
    "test-environment_kubernetes_config:kailash_sdk_kubernetes_config"
)

# Check which volumes exist
echo "Checking for existing volumes..."
EXISTING_PAIRS=()
for pair in "${VOLUME_PAIRS[@]}"; do
    old_vol="${pair%%:*}"
    new_vol="${pair##*:}"

    if docker volume inspect "$old_vol" >/dev/null 2>&1; then
        echo "  ✅ Found: $old_vol"
        EXISTING_PAIRS+=("$pair")
    else
        echo "  ⚠️  Not found: $old_vol (will skip)"
    fi
done

echo ""
echo "📦 Will migrate ${#EXISTING_PAIRS[@]} volumes"
echo ""

# Migrate each volume
for pair in "${EXISTING_PAIRS[@]}"; do
    old_vol="${pair%%:*}"
    new_vol="${pair##*:}"

    echo "Migrating: $old_vol → $new_vol"

    # Create new volume
    docker volume create "$new_vol" >/dev/null

    # Copy data using a temporary container
    echo "  📋 Copying data..."
    docker run --rm \
        -v "$old_vol":/from \
        -v "$new_vol":/to \
        alpine sh -c "cd /from && cp -av . /to" 2>&1 | tail -5

    echo "  ✅ Migrated successfully"
    echo ""
done

echo "✅ All volumes migrated!"
echo ""
echo "Next steps:"
echo "  1. Stop old containers: cd tests/test-environment && docker-compose down"
echo "  2. Start with new name: docker-compose up -d"
echo "  3. Verify data intact"
echo "  4. Delete old volumes: docker volume rm test-environment_*"
echo ""
