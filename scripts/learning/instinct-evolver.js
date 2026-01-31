#!/usr/bin/env node
/**
 * Instinct Evolver for Kailash Continuous Learning System
 *
 * Evolves learned instincts into skills, commands, and agents.
 * Part of Phase 4: Continuous Learning implementation.
 *
 * Usage:
 *   node instinct-evolver.js --candidates
 *   node instinct-evolver.js --evolve-skill <instinct_id>
 *   node instinct-evolver.js --evolve-command <instinct_id>
 *   node instinct-evolver.js --auto
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// Learning directory structure - supports env var override for testing
const LEARNING_DIR = process.env.KAILASH_LEARNING_DIR || path.join(os.homedir(), '.claude', 'kailash-learning');
const INSTINCTS_DIR = path.join(LEARNING_DIR, 'instincts', 'personal');
const EVOLVED_DIR = path.join(LEARNING_DIR, 'evolved');

// Evolution thresholds
const THRESHOLDS = {
  skill: { minConfidence: 0.7, minOccurrences: 5 },
  command: { minConfidence: 0.6, minOccurrences: 3 },
  agent: { minConfidence: 0.8, minOccurrences: 10 }
};

/**
 * Load all instincts
 */
function loadInstincts() {
  const instincts = [];

  if (!fs.existsSync(INSTINCTS_DIR)) {
    return instincts;
  }

  const files = fs.readdirSync(INSTINCTS_DIR);
  files.forEach(file => {
    if (file.endsWith('.json')) {
      const content = JSON.parse(fs.readFileSync(path.join(INSTINCTS_DIR, file), 'utf8'));
      content.forEach(i => {
        i.category = file.replace('.json', '');
        instincts.push(i);
      });
    }
  });

  return instincts;
}

/**
 * Get evolution candidates
 */
function getCandidates() {
  const instincts = loadInstincts();
  const candidates = {
    skill: [],
    command: [],
    agent: []
  };

  instincts.forEach(instinct => {
    const occurrences = instinct.source?.occurrences || 0;

    // Check skill threshold
    if (instinct.confidence >= THRESHOLDS.skill.minConfidence &&
        occurrences >= THRESHOLDS.skill.minOccurrences) {
      candidates.skill.push({
        id: instinct.id,
        confidence: instinct.confidence,
        occurrences,
        category: instinct.category,
        pattern_summary: JSON.stringify(instinct.pattern).substring(0, 80)
      });
    }

    // Check command threshold
    if (instinct.confidence >= THRESHOLDS.command.minConfidence &&
        occurrences >= THRESHOLDS.command.minOccurrences) {
      candidates.command.push({
        id: instinct.id,
        confidence: instinct.confidence,
        occurrences,
        category: instinct.category,
        pattern_summary: JSON.stringify(instinct.pattern).substring(0, 80)
      });
    }

    // Check agent threshold
    if (instinct.confidence >= THRESHOLDS.agent.minConfidence &&
        occurrences >= THRESHOLDS.agent.minOccurrences) {
      candidates.agent.push({
        id: instinct.id,
        confidence: instinct.confidence,
        occurrences,
        category: instinct.category,
        pattern_summary: JSON.stringify(instinct.pattern).substring(0, 80)
      });
    }
  });

  return candidates;
}

/**
 * Find instinct by ID
 */
function findInstinct(id) {
  const instincts = loadInstincts();
  return instincts.find(i => i.id === id);
}

/**
 * Evolve instinct to skill
 */
function evolveToSkill(instinctId) {
  const instinct = findInstinct(instinctId);
  if (!instinct) {
    return { success: false, error: `Instinct ${instinctId} not found` };
  }

  const skillsDir = path.join(EVOLVED_DIR, 'skills');
  if (!fs.existsSync(skillsDir)) {
    fs.mkdirSync(skillsDir, { recursive: true });
  }

  // Generate skill content based on pattern type
  let skillContent = '';
  if (instinct.category === 'workflow-patterns') {
    skillContent = generateWorkflowSkill(instinct);
  } else if (instinct.category === 'error-fixes') {
    skillContent = generateErrorFixSkill(instinct);
  } else {
    skillContent = generateGenericSkill(instinct);
  }

  const fileName = `${instinct.id}.md`;
  const filePath = path.join(skillsDir, fileName);
  fs.writeFileSync(filePath, skillContent);

  // Mark instinct as evolved
  markEvolved(instinctId, 'skill', filePath);

  return {
    success: true,
    file: filePath,
    type: 'skill',
    instinct_id: instinctId
  };
}

/**
 * Evolve instinct to command
 */
function evolveToCommand(instinctId) {
  const instinct = findInstinct(instinctId);
  if (!instinct) {
    return { success: false, error: `Instinct ${instinctId} not found` };
  }

  const commandsDir = path.join(EVOLVED_DIR, 'commands');
  if (!fs.existsSync(commandsDir)) {
    fs.mkdirSync(commandsDir, { recursive: true });
  }

  const commandContent = generateCommand(instinct);
  const fileName = `${instinct.id}.md`;
  const filePath = path.join(commandsDir, fileName);
  fs.writeFileSync(filePath, commandContent);

  markEvolved(instinctId, 'command', filePath);

  return {
    success: true,
    file: filePath,
    type: 'command',
    instinct_id: instinctId
  };
}

/**
 * Generate workflow skill content
 */
function generateWorkflowSkill(instinct) {
  const pattern = instinct.pattern;
  return `# Learned Workflow Pattern

## Source
- Instinct ID: ${instinct.id}
- Confidence: ${(instinct.confidence * 100).toFixed(0)}%
- Occurrences: ${instinct.source?.occurrences || 0}
- Learned: ${instinct.created_at}

## Pattern

\`\`\`python
# Workflow pattern learned from usage
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
${JSON.stringify(pattern, null, 2)}

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
\`\`\`

## When to Use

This pattern was observed ${instinct.source?.occurrences || 0} times with high success rate.

## Integration

To add to skills:
1. Review the pattern above
2. Copy relevant sections to appropriate skill file
3. Update skill SKILL.md entry
`;
}

/**
 * Generate error-fix skill content
 */
function generateErrorFixSkill(instinct) {
  const pattern = instinct.pattern;
  return `# Learned Error-Fix Pattern

## Source
- Instinct ID: ${instinct.id}
- Confidence: ${(instinct.confidence * 100).toFixed(0)}%
- Occurrences: ${instinct.source?.occurrences || 0}
- Learned: ${instinct.created_at}

## Error Pattern

\`\`\`
${JSON.stringify(pattern.error || pattern, null, 2)}
\`\`\`

## Fix Pattern

\`\`\`
${JSON.stringify(pattern.fix || {}, null, 2)}
\`\`\`

## When to Apply

Apply this fix when encountering the error pattern above.
Success rate: ${(instinct.confidence * 100).toFixed(0)}%

## Integration

To add to troubleshooting guide:
1. Add to \`15-error-troubleshooting/\`
2. Document in error catalog
`;
}

/**
 * Generate generic skill content
 */
function generateGenericSkill(instinct) {
  return `# Learned Pattern

## Source
- Instinct ID: ${instinct.id}
- Category: ${instinct.category}
- Confidence: ${(instinct.confidence * 100).toFixed(0)}%
- Occurrences: ${instinct.source?.occurrences || 0}
- Learned: ${instinct.created_at}

## Pattern

\`\`\`json
${JSON.stringify(instinct.pattern, null, 2)}
\`\`\`

## Usage Notes

This pattern was learned from ${instinct.source?.occurrences || 0} observations.
Review and integrate into appropriate skill documentation.
`;
}

/**
 * Generate command content
 */
function generateCommand(instinct) {
  const commandName = instinct.id.replace('instinct_', '').substring(0, 20);
  return `# /${commandName} - Learned Command

## Purpose

Auto-generated command from learned instinct.

## Source
- Instinct ID: ${instinct.id}
- Category: ${instinct.category}
- Confidence: ${(instinct.confidence * 100).toFixed(0)}%

## Pattern

\`\`\`json
${JSON.stringify(instinct.pattern, null, 2)}
\`\`\`

## Usage

Review this command and:
1. Rename to meaningful name
2. Move to \`.claude/commands/\`
3. Update command registry
`;
}

/**
 * Mark instinct as evolved
 */
function markEvolved(instinctId, type, outputPath) {
  const evolutionLog = path.join(EVOLVED_DIR, 'evolution-log.jsonl');
  const entry = {
    timestamp: new Date().toISOString(),
    instinct_id: instinctId,
    evolution_type: type,
    output_path: outputPath
  };
  fs.appendFileSync(evolutionLog, JSON.stringify(entry) + '\n');
}

/**
 * Auto-evolve high-confidence instincts
 */
function autoEvolve() {
  const results = {
    evolved: [],
    skipped: []
  };

  const instincts = loadInstincts();

  instincts.forEach(instinct => {
    const occurrences = instinct.source?.occurrences || 0;

    // Only auto-evolve very high confidence instincts
    if (instinct.confidence >= 0.8 && occurrences >= 5) {
      let result;

      if (instinct.category === 'workflow-patterns') {
        result = evolveToSkill(instinct.id);
      } else if (instinct.category === 'error-fixes') {
        result = evolveToCommand(instinct.id);
      } else {
        result = evolveToSkill(instinct.id);
      }

      if (result.success) {
        results.evolved.push(result);
      }
    } else {
      results.skipped.push({
        id: instinct.id,
        reason: instinct.confidence < 0.8 ? 'low_confidence' : 'insufficient_occurrences'
      });
    }
  });

  return results;
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);
  const command = args[0] || '--help';

  // Ensure evolved directory exists
  if (!fs.existsSync(EVOLVED_DIR)) {
    fs.mkdirSync(EVOLVED_DIR, { recursive: true });
  }

  switch (command) {
    case '--candidates':
      const candidates = getCandidates();
      console.log(JSON.stringify(candidates, null, 2));
      break;

    case '--evolve-skill':
      const skillId = args[1];
      if (!skillId) {
        console.error('Error: instinct_id required');
        process.exit(1);
      }
      const skillResult = evolveToSkill(skillId);
      console.log(JSON.stringify(skillResult, null, 2));
      break;

    case '--evolve-command':
      const cmdId = args[1];
      if (!cmdId) {
        console.error('Error: instinct_id required');
        process.exit(1);
      }
      const cmdResult = evolveToCommand(cmdId);
      console.log(JSON.stringify(cmdResult, null, 2));
      break;

    case '--auto':
      const autoResult = autoEvolve();
      console.log(JSON.stringify(autoResult, null, 2));
      break;

    case '--help':
    default:
      console.log(`
Instinct Evolver for Kailash Continuous Learning

Usage:
  node instinct-evolver.js --candidates          List evolution candidates
  node instinct-evolver.js --evolve-skill <id>   Evolve to skill
  node instinct-evolver.js --evolve-command <id> Evolve to command
  node instinct-evolver.js --auto                Auto-evolve high-confidence
  node instinct-evolver.js --help                Show this help
`);
      break;
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  loadInstincts,
  getCandidates,
  evolveToSkill,
  evolveToCommand,
  autoEvolve
};
