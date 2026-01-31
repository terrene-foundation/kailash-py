#!/usr/bin/env node
/**
 * Plugin Builder for Kailash Vibe CC Setup
 *
 * Packages the setup as a distributable .claude-plugin for easy installation.
 *
 * Gap Resolution: "No Plugin Distribution" from 02-kailash-setup-gaps.md
 *
 * Usage:
 *   node build-plugin.js [--output /path/to/output]
 *   node build-plugin.js --version 1.0.0
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Plugin configuration
const PLUGIN_NAME = 'kailash-vibe-cc-setup';
const PLUGIN_VERSION = process.env.PLUGIN_VERSION || '1.0.0';

// Directories to include in plugin
const INCLUDE_DIRS = [
  '.claude/agents',
  '.claude/commands',
  '.claude/rules',
  '.claude/skills',
  '.claude/guides',
  'scripts/hooks',
  'scripts/learning',
  'scripts/ci',
  'mcp-configs'
];

// Files to include in plugin root
const INCLUDE_FILES = [
  '.claude/settings.json',
  'CLAUDE.md',
  'instructions/FLOW.md',
  'instructions/SOP.md'
];

// Files to exclude (patterns)
const EXCLUDE_PATTERNS = [
  /\.DS_Store$/,
  /\.git\//,
  /node_modules\//,
  /\.env$/,
  /\.backup/,
  /\.disabled$/,
  /\.test\.js$/,
  /__tests__\//
];

/**
 * Plugin manifest schema
 */
function createManifest() {
  return {
    name: PLUGIN_NAME,
    version: PLUGIN_VERSION,
    description: 'Framework-specific Claude Code setup for Kailash SDK ecosystem (DataFlow, Nexus, Kaizen, MCP)',
    author: 'Kailash Team',
    license: 'MIT',
    claude_code_version: '>=1.0.0',
    keywords: [
      'kailash',
      'sdk',
      'dataflow',
      'nexus',
      'kaizen',
      'mcp',
      'workflow',
      'database',
      'ai-agents'
    ],
    repository: {
      type: 'git',
      url: 'https://github.com/kailash/kailash-vibe-cc-setup'
    },
    components: {
      agents: 25,
      skills: 18,
      commands: 9,
      rules: 5,
      hooks: 8,
      mcp_configs: 3,
      learning_scripts: 4,
      ci_validators: 5
    },
    features: [
      'hooks-infrastructure',
      'continuous-learning',
      'ci-validation',
      'mcp-configurations',
      'security-reviewer',
      'package-manager-detection'
    ],
    dependencies: {
      runtime: 'node >= 18.0.0',
      optional: ['black', 'prettier', 'eslint']
    },
    install: {
      pre_install: 'scripts/plugin/pre-install.js',
      post_install: 'scripts/plugin/post-install.js'
    },
    uninstall: {
      pre_uninstall: 'scripts/plugin/pre-uninstall.js'
    }
  };
}

/**
 * Check if file should be excluded
 */
function shouldExclude(filePath) {
  return EXCLUDE_PATTERNS.some(pattern => pattern.test(filePath));
}

/**
 * Copy directory recursively
 */
function copyDir(src, dest, fileList = []) {
  if (!fs.existsSync(src)) {
    return fileList;
  }

  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true });
  }

  const entries = fs.readdirSync(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (shouldExclude(srcPath)) {
      continue;
    }

    if (entry.isDirectory()) {
      copyDir(srcPath, destPath, fileList);
    } else {
      fs.copyFileSync(srcPath, destPath);
      fileList.push(destPath);
    }
  }

  return fileList;
}

/**
 * Build the plugin package
 */
function buildPlugin(outputDir) {
  const projectRoot = path.resolve(__dirname, '../..');
  const buildDir = path.join(outputDir, PLUGIN_NAME);
  const copiedFiles = [];

  console.log(`Building plugin: ${PLUGIN_NAME} v${PLUGIN_VERSION}`);
  console.log(`Output directory: ${outputDir}`);

  // Clean existing build
  if (fs.existsSync(buildDir)) {
    fs.rmSync(buildDir, { recursive: true });
  }
  fs.mkdirSync(buildDir, { recursive: true });

  // Copy directories
  console.log('\nCopying directories...');
  for (const dir of INCLUDE_DIRS) {
    const srcDir = path.join(projectRoot, dir);
    const destDir = path.join(buildDir, dir);

    if (fs.existsSync(srcDir)) {
      const files = copyDir(srcDir, destDir);
      copiedFiles.push(...files);
      console.log(`  ✓ ${dir} (${files.length} files)`);
    } else {
      console.log(`  ⚠ ${dir} (not found, skipping)`);
    }
  }

  // Copy individual files
  console.log('\nCopying files...');
  for (const file of INCLUDE_FILES) {
    const srcFile = path.join(projectRoot, file);
    const destFile = path.join(buildDir, file);

    if (fs.existsSync(srcFile)) {
      const destDir = path.dirname(destFile);
      if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
      }
      fs.copyFileSync(srcFile, destFile);
      copiedFiles.push(destFile);
      console.log(`  ✓ ${file}`);
    } else {
      console.log(`  ⚠ ${file} (not found, skipping)`);
    }
  }

  // Create manifest
  console.log('\nCreating manifest...');
  const manifest = createManifest();
  manifest.files_count = copiedFiles.length;
  manifest.built_at = new Date().toISOString();

  fs.writeFileSync(
    path.join(buildDir, 'plugin.json'),
    JSON.stringify(manifest, null, 2)
  );
  console.log('  ✓ plugin.json');

  // Create README for plugin
  const readme = `# ${PLUGIN_NAME}

Framework-specific Claude Code setup for Kailash SDK ecosystem.

## Version

${PLUGIN_VERSION}

## Components

- **Agents**: ${manifest.components.agents} specialized agents
- **Skills**: ${manifest.components.skills} skill categories
- **Commands**: ${manifest.components.commands} slash commands
- **Hooks**: ${manifest.components.hooks} automation hooks
- **MCP Configs**: ${manifest.components.mcp_configs} context configurations

## Installation

\`\`\`bash
# Via Claude Code plugin manager (when available)
claude plugin install ${PLUGIN_NAME}

# Manual installation
cp -r ${PLUGIN_NAME}/.claude/* ~/.claude/
cp -r ${PLUGIN_NAME}/scripts/* ~/scripts/
\`\`\`

## Features

${manifest.features.map(f => `- ${f}`).join('\n')}

## Documentation

See CLAUDE.md for complete documentation.

Built: ${manifest.built_at}
`;

  fs.writeFileSync(path.join(buildDir, 'README.md'), readme);
  console.log('  ✓ README.md');

  // Create archive (if tar available)
  console.log('\nCreating archive...');
  const archiveName = `${PLUGIN_NAME}-${PLUGIN_VERSION}.tar.gz`;
  const archivePath = path.join(outputDir, archiveName);

  try {
    execSync(`tar -czf "${archivePath}" -C "${outputDir}" "${PLUGIN_NAME}"`, {
      stdio: 'pipe'
    });
    console.log(`  ✓ ${archiveName}`);
  } catch (e) {
    console.log(`  ⚠ Archive creation failed (tar not available)`);
  }

  // Summary
  console.log('\n=== Build Summary ===');
  console.log(`Plugin: ${PLUGIN_NAME}`);
  console.log(`Version: ${PLUGIN_VERSION}`);
  console.log(`Files: ${copiedFiles.length}`);
  console.log(`Output: ${buildDir}`);

  if (fs.existsSync(archivePath)) {
    const stats = fs.statSync(archivePath);
    console.log(`Archive: ${archiveName} (${(stats.size / 1024).toFixed(1)} KB)`);
  }

  return {
    success: true,
    plugin_name: PLUGIN_NAME,
    version: PLUGIN_VERSION,
    build_dir: buildDir,
    files_count: copiedFiles.length,
    manifest: manifest
  };
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);

  // Check for --help
  if (args.includes('--help')) {
    console.log(`
Plugin Builder for Kailash Vibe CC Setup

Usage:
  node build-plugin.js [options]

Options:
  --output <dir>    Output directory (default: ./dist)
  --version <ver>   Plugin version (default: 1.0.0)
  --help            Show this help

Example:
  node build-plugin.js --output ./dist --version 1.0.0
`);
    process.exit(0);
  }

  // Parse arguments
  let outputDir = path.join(process.cwd(), 'dist');

  const outputIndex = args.indexOf('--output');
  if (outputIndex >= 0 && args[outputIndex + 1]) {
    outputDir = path.resolve(args[outputIndex + 1]);
  }

  const versionIndex = args.indexOf('--version');
  if (versionIndex >= 0 && args[versionIndex + 1]) {
    process.env.PLUGIN_VERSION = args[versionIndex + 1];
  }

  // Build
  try {
    const result = buildPlugin(outputDir);
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  } catch (error) {
    console.error(`Build failed: ${error.message}`);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { buildPlugin, createManifest };
