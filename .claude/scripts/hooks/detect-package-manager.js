#!/usr/bin/env node
/**
 * Package Manager Detection Hook for Kailash Setup
 *
 * Detects which package manager is used in the current project:
 * - npm (package-lock.json)
 * - pnpm (pnpm-lock.yaml)
 * - yarn (yarn.lock)
 * - bun (bun.lockb)
 *
 * Gap Resolution: "No Package Manager Detection" from 02-kailash-setup-gaps.md
 *
 * Usage:
 *   node detect-package-manager.js [--cwd /path/to/project]
 *   echo '{"cwd": "/path"}' | node detect-package-manager.js
 */

const fs = require("fs");
const path = require("path");

// Package manager lock files and their priority
const PACKAGE_MANAGERS = [
  { name: "bun", lockFile: "bun.lockb", command: "bun" },
  { name: "pnpm", lockFile: "pnpm-lock.yaml", command: "pnpm" },
  { name: "yarn", lockFile: "yarn.lock", command: "yarn" },
  { name: "npm", lockFile: "package-lock.json", command: "npm" },
];

// Default fallback
const DEFAULT_PM = { name: "npm", lockFile: null, command: "npm" };

/**
 * Detect package manager in a directory
 */
function detectPackageManager(dir) {
  // Check for lock files in priority order
  for (const pm of PACKAGE_MANAGERS) {
    const lockPath = path.join(dir, pm.lockFile);
    if (fs.existsSync(lockPath)) {
      return {
        detected: true,
        packageManager: pm.name,
        command: pm.command,
        lockFile: pm.lockFile,
        lockPath: lockPath,
      };
    }
  }

  // Check package.json for packageManager field (Corepack)
  const packageJsonPath = path.join(dir, "package.json");
  if (fs.existsSync(packageJsonPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
      if (pkg.packageManager) {
        // Format: "pnpm@8.0.0" or "yarn@4.0.0"
        const match = pkg.packageManager.match(/^(npm|pnpm|yarn|bun)@/);
        if (match) {
          const pmName = match[1];
          return {
            detected: true,
            packageManager: pmName,
            command: pmName,
            lockFile: null,
            source: "packageManager field",
            version: pkg.packageManager,
          };
        }
      }
    } catch (e) {
      // Ignore parse errors
    }
  }

  // No package manager detected, check if package.json exists
  if (fs.existsSync(packageJsonPath)) {
    return {
      detected: false,
      packageManager: DEFAULT_PM.name,
      command: DEFAULT_PM.command,
      lockFile: null,
      fallback: true,
      reason: "No lock file found, defaulting to npm",
    };
  }

  return {
    detected: false,
    packageManager: null,
    command: null,
    lockFile: null,
    reason: "No package.json found",
  };
}

/**
 * Get install command for detected package manager
 */
function getInstallCommand(pm, packages = []) {
  const pkgStr = packages.join(" ");
  switch (pm) {
    case "bun":
      return packages.length > 0 ? `bun add ${pkgStr}` : "bun install";
    case "pnpm":
      return packages.length > 0 ? `pnpm add ${pkgStr}` : "pnpm install";
    case "yarn":
      return packages.length > 0 ? `yarn add ${pkgStr}` : "yarn install";
    case "npm":
    default:
      return packages.length > 0 ? `npm install ${pkgStr}` : "npm install";
  }
}

/**
 * Get run command for detected package manager
 */
function getRunCommand(pm, script) {
  switch (pm) {
    case "bun":
      return `bun run ${script}`;
    case "pnpm":
      return `pnpm run ${script}`;
    case "yarn":
      return `yarn ${script}`;
    case "npm":
    default:
      return `npm run ${script}`;
  }
}

/**
 * Get exec command for detected package manager
 */
function getExecCommand(pm, command) {
  switch (pm) {
    case "bun":
      return `bunx ${command}`;
    case "pnpm":
      return `pnpm exec ${command}`;
    case "yarn":
      return `yarn dlx ${command}`;
    case "npm":
    default:
      return `npx ${command}`;
  }
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);
  let cwd = process.cwd();

  // Check for --cwd argument
  const cwdIndex = args.indexOf("--cwd");
  if (cwdIndex >= 0 && args[cwdIndex + 1]) {
    cwd = args[cwdIndex + 1];
  }

  // Check for --help
  if (args.includes("--help")) {
    console.log(`
Package Manager Detection for Kailash Setup

Usage:
  node detect-package-manager.js [--cwd /path/to/project]
  echo '{"cwd": "/path"}' | node detect-package-manager.js

Output (JSON):
  {
    "detected": true|false,
    "packageManager": "npm|pnpm|yarn|bun|null",
    "command": "npm|pnpm|yarn|bun|null",
    "lockFile": "package-lock.json|pnpm-lock.yaml|yarn.lock|bun.lockb|null",
    "commands": {
      "install": "npm install",
      "run": "npm run <script>",
      "exec": "npx <command>"
    }
  }
`);
    process.exit(0);
  }

  // Check for stdin input (for hook usage)
  if (!process.stdin.isTTY) {
    let input = "";
    process.stdin.on("data", (chunk) => {
      input += chunk;
    });
    process.stdin.on("end", () => {
      try {
        const data = JSON.parse(input);
        if (data.cwd) {
          cwd = data.cwd;
        }
        outputResult(cwd);
      } catch (e) {
        outputResult(cwd);
      }
    });
  } else {
    outputResult(cwd);
  }
}

function outputResult(cwd) {
  const result = detectPackageManager(cwd);

  // Add command helpers if package manager detected
  if (result.packageManager) {
    result.commands = {
      install: getInstallCommand(result.packageManager),
      installPackage: getInstallCommand(result.packageManager, ["<package>"]),
      run: getRunCommand(result.packageManager, "<script>"),
      exec: getExecCommand(result.packageManager, "<command>"),
    };
  }

  result.cwd = cwd;
  result.timestamp = new Date().toISOString();

  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}

if (require.main === module) {
  main();
}

module.exports = {
  detectPackageManager,
  getInstallCommand,
  getRunCommand,
  getExecCommand,
  PACKAGE_MANAGERS,
};
