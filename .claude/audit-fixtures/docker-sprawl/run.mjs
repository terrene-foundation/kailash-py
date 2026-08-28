#!/usr/bin/env node
/**
 * Audit-fixture runner for the docker-sprawl detector — `.claude/hooks/lib/docker-sprawl.js`
 * plus the real `.claude/hooks/docker-sprawl-guard.js` stdin boundary
 * (`docker-no-sprawl.md`), shipped WITH the detector per `cc-artifacts.md` Rule 9.
 *
 * Coverage shape is ONE CASE PER SCOPE-RESTRICTION PREDICATE — the predicates a
 * wrong edit would silently widen or narrow. Every predicate is BIPOLAR: a case
 * that MUST fire and a case that MUST stay quiet, so a detector edited into
 * always-firing or always-quiet fails here rather than in review.
 *
 *   1  compose files are recognised by filename, non-compose YAML is not
 *   2  the group mandate binds a non-example compose file
 *   3  ... and is CARVED OUT for a shipped example (pinning our group would
 *      hijack a user's own project name)
 *   4  a WRONG group name is a finding, the canonical one is not
 *   5  a stateful service with no named volume is a finding
 *   6  a named volume is quiet; a BIND mount is quiet (it cannot strand)
 *   7  sidecars whose image NAME contains a stateful token are NOT stateful —
 *      the over-match that produced 5 false positives before it was fixed
 *   8  a bare stateful `docker run` is a finding
 *   9  ... but `--rm` and a named `-v` are each quiet, and `docker compose run`
 *      is never flagged
 *  10  the hook FAILS OPEN on malformed stdin, on a missing lib, and on a
 *      non-compose path — a hygiene guard must never wedge the session
 */

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..", "..");
const LIB = path.join(ROOT, ".claude", "hooks", "lib", "docker-sprawl.js");
const HOOK = path.join(ROOT, ".claude", "hooks", "docker-sprawl-guard.js");
const lib = require(LIB);

let pass = 0;
const failures = [];
function check(name, actual, expected) {
  if (actual === expected) pass++;
  else failures.push(`${name}: expected ${expected}, got ${actual}`);
}

const compose = (body) => body;
const S = "services:\n  db:\n    image: postgres:16\n";
const S_NAMED = "services:\n  db:\n    image: postgres:16\n    volumes:\n      - pgdata:/v\nvolumes:\n  pgdata:\n";

// 1 — filename recognition, both poles
check("1a compose recognised", lib.isComposeFile("a/docker-compose.yml"), true);
check("1b compose.yaml recognised", lib.isComposeFile("tests/compose.yaml"), true);
check("1c variant recognised", lib.isComposeFile("x/docker-compose.test.yml"), true);
check("1d non-compose yaml ignored", lib.isComposeFile(".github/workflows/ci.yml"), false);

// 2/3 — group mandate scope, both poles
const g = (p, t) => lib.inspectCompose(p, t).filter((f) => f.check.startsWith("group")).length;
check("2a non-example unpinned fires", g("tests/x/docker-compose.yml", compose(S)) > 0, true);
check("3a example unpinned quiet", g("pkg/examples/d/docker-compose.yml", compose(S)), 0);
check("3b nested example quiet", g("examples/x/docker-compose.yml", compose(S)), 0);

// 4 — wrong vs canonical group
check("4a wrong group fires", g("tests/x/docker-compose.yml", `name: other\n${S}`) > 0, true);
check("4b canonical group quiet", g("tests/x/docker-compose.yml", `name: ${lib.CANONICAL_GROUP}\n${S}`), 0);

// 5/6 — anonymous volume, both poles
const a = (t) => lib.inspectCompose("tests/x/docker-compose.yml", t).filter((f) => f.check === "anonymous-volume").length;
check("5a stateful w/o named vol fires", a(`name: ${lib.CANONICAL_GROUP}\n${S}`) > 0, true);
check("6a named volume quiet", a(`name: ${lib.CANONICAL_GROUP}\n${S_NAMED}`), 0);
check(
  "6b bind mount quiet",
  a(`name: ${lib.CANONICAL_GROUP}\nservices:\n  db:\n    image: postgres:16\n    volumes:\n      - ./data:/v\n`),
  0,
);

// 7 — sidecar over-match, the measured false-positive class
check("7a mongo-express not stateful", lib.isStatefulImage("mongo-express:latest"), false);
check("7b mysqld-exporter not stateful", lib.isStatefulImage("prom/mysqld-exporter"), false);
check("7c kafka-ui not stateful", lib.isStatefulImage("provectuslabs/kafka-ui"), false);
check("7d postgres IS stateful", lib.isStatefulImage("postgres:16"), true);
check("7e unknown image not stateful", lib.isStatefulImage("my/app:1.0"), false);

// 8/9 — docker run, both poles
const r = (c) => lib.inspectDockerRun(c).length;
check("8a bare stateful run fires", r("docker run -d --name pg postgres:16") > 0, true);
check("9a --rm quiet", r("docker run --rm postgres:16 psql --version"), 0);
check("9b named -v quiet", r("docker run -d -v pgdata:/var/lib/postgresql/data postgres:16"), 0);
check("9c docker compose run quiet", r("docker compose run --rm db psql"), 0);
check("9d unrelated command quiet", r("ls -la && git status"), 0);
check("9e non-stateful run quiet", r("docker run -d my/app:1.0"), 0);

// 10 — hook boundary: fires, stays quiet, and FAILS OPEN
function drive(payload) {
  const res = spawnSync(process.execPath, [HOOK], { input: payload, encoding: "utf8" });
  let json = null;
  try { json = JSON.parse(res.stdout); } catch { /* leave null */ }
  return { json, code: res.status };
}
const fired = (o) => !!(o.json && (o.json.systemMessage || o.json.hookSpecificOutput));

check(
  "10a hook fires on violating compose",
  fired(drive(JSON.stringify({ hook_event_name: "PostToolUse", tool_input: { file_path: "tests/x/docker-compose.yml", content: S } }))),
  true,
);
check(
  "10b hook quiet on clean compose",
  fired(drive(JSON.stringify({ hook_event_name: "PostToolUse", tool_input: { file_path: "tests/x/docker-compose.yml", content: `name: ${lib.CANONICAL_GROUP}\n${S_NAMED}` } }))),
  false,
);
check(
  "10c hook quiet on non-compose path",
  fired(drive(JSON.stringify({ hook_event_name: "PostToolUse", tool_input: { file_path: "src/x.py", content: S } }))),
  false,
);
check(
  "10d hook fires on bare docker run",
  fired(drive(JSON.stringify({ hook_event_name: "PreToolUse", tool_input: { command: "docker run -d --name pg postgres:16" } }))),
  true,
);
const bad = drive("{not json");
check("10e malformed stdin fails OPEN (continue)", bad.json && bad.json.continue === true, true);
check("10f malformed stdin exits 0", bad.code, 0);
const empty = drive("");
check("10g empty stdin fails OPEN", empty.json && empty.json.continue === true, true);

for (const f of failures) console.error(`FAIL ${f}`);
console.log(`docker-sprawl fixtures: ${pass} passed, ${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
