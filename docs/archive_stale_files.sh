#!/bin/bash
# Archive stale documentation files
# These files are outdated and no longer referenced in the new documentation structure.
# They are moved to docs/.archive/ rather than deleted, for reference.

set -e

DOCS_DIR="$(cd "$(dirname "$0")" && pwd)"
ARCHIVE_DIR="$DOCS_DIR/.archive"

mkdir -p "$ARCHIVE_DIR"
mkdir -p "$ARCHIVE_DIR/repivot"
mkdir -p "$ARCHIVE_DIR/repivot/implementation"
mkdir -p "$ARCHIVE_DIR/studio"
mkdir -p "$ARCHIVE_DIR/critiques"
mkdir -p "$ARCHIVE_DIR/requirements"
mkdir -p "$ARCHIVE_DIR/features"
mkdir -p "$ARCHIVE_DIR/enhancements"
mkdir -p "$ARCHIVE_DIR/old-runtime-refactoring"

echo "Archiving stale documentation files..."

# repivot/ -- old implementation docs
if [ -d "$DOCS_DIR/repivot" ]; then
    cp -r "$DOCS_DIR/repivot/"* "$ARCHIVE_DIR/repivot/" 2>/dev/null || true
    echo "  Archived: repivot/"
fi

# studio/ -- Kailash Studio (separate product)
if [ -d "$DOCS_DIR/studio" ]; then
    cp -r "$DOCS_DIR/studio/"* "$ARCHIVE_DIR/studio/" 2>/dev/null || true
    echo "  Archived: studio/"
fi

# critiques/ -- internal review docs
if [ -d "$DOCS_DIR/critiques" ]; then
    cp -r "$DOCS_DIR/critiques/"* "$ARCHIVE_DIR/critiques/" 2>/dev/null || true
    echo "  Archived: critiques/"
fi

# requirements/ -- old requirements
if [ -d "$DOCS_DIR/requirements" ]; then
    cp -r "$DOCS_DIR/requirements/"* "$ARCHIVE_DIR/requirements/" 2>/dev/null || true
    echo "  Archived: requirements/"
fi

# features/ -- old feature comparisons
if [ -d "$DOCS_DIR/features" ]; then
    cp -r "$DOCS_DIR/features/"* "$ARCHIVE_DIR/features/" 2>/dev/null || true
    echo "  Archived: features/"
fi

# enhancements/ -- old enhancement plans
if [ -d "$DOCS_DIR/enhancements" ]; then
    cp -r "$DOCS_DIR/enhancements/"* "$ARCHIVE_DIR/enhancements/" 2>/dev/null || true
    echo "  Archived: enhancements/"
fi

# runtime-refactoring-*.md -- completed work
for f in "$DOCS_DIR"/runtime-refactoring-*.md; do
    if [ -f "$f" ]; then
        cp "$f" "$ARCHIVE_DIR/old-runtime-refactoring/" 2>/dev/null || true
        echo "  Archived: $(basename "$f")"
    fi
done

# phase4-integration-plan.md -- old plan
if [ -f "$DOCS_DIR/phase4-integration-plan.md" ]; then
    cp "$DOCS_DIR/phase4-integration-plan.md" "$ARCHIVE_DIR/"
    echo "  Archived: phase4-integration-plan.md"
fi

# Old version-specific files
for f in "$DOCS_DIR/v0.2.0-release-summary"*; do
    if [ -f "$f" ]; then
        cp "$f" "$ARCHIVE_DIR/"
        echo "  Archived: $(basename "$f")"
    fi
done

# Old top-level files no longer in toctree
for f in data-consolidation-guide workflow_studio unimplemented_nodes_tracker glossary architecture_overview; do
    for ext in .rst .md; do
        if [ -f "$DOCS_DIR/${f}${ext}" ]; then
            cp "$DOCS_DIR/${f}${ext}" "$ARCHIVE_DIR/"
            echo "  Archived: ${f}${ext}"
        fi
    done
done

echo ""
echo "Archive complete. Stale files copied to: $ARCHIVE_DIR"
echo ""
echo "To verify, run: ls -la $ARCHIVE_DIR"
echo ""
echo "NOTE: Original files are still in place. The conf.py exclude_patterns"
echo "already excludes these directories from the Sphinx build."
echo "You can safely delete the originals after verifying the archive."
