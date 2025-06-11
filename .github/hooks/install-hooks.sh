#!/bin/bash
# Install git hooks for the Claude Code workflow

HOOKS_DIR=".github/hooks"
GIT_HOOKS_DIR=".git/hooks"

echo "Installing Claude Code workflow git hooks..."

# Create git hooks directory if it doesn't exist
if [ ! -d "$GIT_HOOKS_DIR" ]; then
    mkdir -p "$GIT_HOOKS_DIR"
fi

# Install pre-commit hook
if [ -f "$HOOKS_DIR/pre-commit" ]; then
    cp "$HOOKS_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"
    chmod +x "$GIT_HOOKS_DIR/pre-commit"
    echo "✅ Installed pre-commit hook"
else
    echo "❌ pre-commit hook not found in $HOOKS_DIR"
fi

echo ""
echo "Git hooks installation complete!"
echo ""
echo "The pre-commit hook will prevent:"
echo "  • Manual editing of TODO files"
echo "  • Direct project manipulation"
echo ""
echo "To bypass in emergency (NOT recommended):"
echo "  git commit --no-verify"
