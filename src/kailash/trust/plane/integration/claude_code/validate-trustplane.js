// Copyright 2026 Terrene Foundation
// SPDX-License-Identifier: Apache-2.0

// TrustPlane Pre-Tool-Use Validation Hook (Tier 2)
//
// Install in .claude/settings.json:
// {
//   "hooks": {
//     "PreToolUse": [{
//       "matcher": "Edit|Write|Bash",
//       "hooks": ["node scripts/hooks/validate-trustplane.js"]
//     }]
//   }
// }

const fs = require("fs");
const path = require("path");

const input = JSON.parse(fs.readFileSync("/dev/stdin", "utf8"));
const toolName = input.tool_name;
const toolInput = input.tool_input || {};

// Find trust-plane directory
const trustDir = path.join(process.cwd(), "trust-plane");

// Check 1: Prevent direct modification of trust infrastructure
if (toolName === "Edit" || toolName === "Write") {
  const filePath = toolInput.file_path || "";
  if (filePath.includes("trust-plane/")) {
    console.error(
      JSON.stringify({
        decision: "block",
        reason:
          "Direct modification of trust-plane/ directory is not allowed. Use TrustPlane MCP tools instead.",
      }),
    );
    process.exit(0);
  }
}

// Check 2: Warn if no active session when modifying governance files
if (toolName === "Edit" || toolName === "Write") {
  const filePath = toolInput.file_path || "";
  const governancePaths = [
    "docs/06-operations/",
    "docs/02-standards/",
    "docs/01-strategy/",
  ];

  const isGovernance = governancePaths.some((p) => filePath.includes(p));
  if (isGovernance && fs.existsSync(trustDir)) {
    const sessionPath = path.join(trustDir, "session.json");
    if (!fs.existsSync(sessionPath)) {
      // Warning only — don't block
      console.error(
        JSON.stringify({
          decision: "warn",
          reason:
            "Modifying governance file without active TrustPlane session. Consider starting a session with trust_status.",
        }),
      );
    }
  }
}

// Default: allow
process.exit(0);
