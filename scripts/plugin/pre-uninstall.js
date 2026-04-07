#!/usr/bin/env node
/**
 * Pre-Uninstall Script for Kailash Plugin
 *
 * Runs before plugin uninstallation to:
 * - Export observations and learning digest
 * - Offer to preserve data
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

const LEARNING_DIR = path.join(os.homedir(), ".claude", "kailash-learning");
const EXPORT_DIR = path.join(os.homedir(), "kailash-learning-export");

function main() {
  console.log("\n=== Kailash COC Claude (Python) - Pre Uninstall ===\n");

  // Check if learning data exists
  if (!fs.existsSync(LEARNING_DIR)) {
    console.log("No learning data to preserve.");
    process.exit(0);
  }

  const obsFile = path.join(LEARNING_DIR, "observations.jsonl");
  const digestFile = path.join(LEARNING_DIR, "learning-digest.json");
  const codifiedFile = path.join(LEARNING_DIR, "learning-codified.json");

  let hasData = false;

  if (fs.existsSync(obsFile)) {
    const content = fs.readFileSync(obsFile, "utf8");
    const lines = content
      .trim()
      .split("\n")
      .filter((l) => l);
    if (lines.length > 0) {
      console.log(`Found ${lines.length} observations`);
      hasData = true;
    }
  }

  if (fs.existsSync(digestFile)) {
    console.log("Found learning digest");
    hasData = true;
  }

  if (!hasData) {
    console.log("No learning data to preserve.");
    process.exit(0);
  }

  // Export learning data
  console.log("\nExporting learning data...");

  if (!fs.existsSync(EXPORT_DIR)) {
    fs.mkdirSync(EXPORT_DIR, { recursive: true });
  }

  // Copy observations
  if (fs.existsSync(obsFile)) {
    fs.copyFileSync(obsFile, path.join(EXPORT_DIR, "observations.jsonl"));
    console.log("  ✓ Observations exported");
  }

  // Copy digest
  if (fs.existsSync(digestFile)) {
    fs.copyFileSync(digestFile, path.join(EXPORT_DIR, "learning-digest.json"));
    console.log("  ✓ Learning digest exported");
  }

  // Copy codification history
  if (fs.existsSync(codifiedFile)) {
    fs.copyFileSync(
      codifiedFile,
      path.join(EXPORT_DIR, "learning-codified.json"),
    );
    console.log("  ✓ Codification history exported");
  }

  // Create export manifest
  const manifest = {
    exported_at: new Date().toISOString(),
    source: "kailash-coc-claude",
    version: "2.0.0",
    contains: {
      observations: fs.existsSync(path.join(EXPORT_DIR, "observations.jsonl")),
      digest: fs.existsSync(path.join(EXPORT_DIR, "learning-digest.json")),
      codified: fs.existsSync(path.join(EXPORT_DIR, "learning-codified.json")),
    },
  };

  fs.writeFileSync(
    path.join(EXPORT_DIR, "export-manifest.json"),
    JSON.stringify(manifest, null, 2),
  );

  console.log(`\n✓ Learning data exported to: ${EXPORT_DIR}`);
  console.log("  You can re-import this data after reinstalling.\n");

  process.exit(0);
}

if (require.main === module) {
  main();
}

module.exports = { main };
