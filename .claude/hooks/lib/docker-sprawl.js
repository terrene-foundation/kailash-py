"use strict";
/**
 * docker-sprawl.js — detection logic for `docker-no-sprawl.md`.
 *
 * Pure functions over text. No docker calls, no filesystem, no network: the
 * daemon is not queried at tool-call time because a hook that shells out to
 * `docker` pays a multi-second cost on every edit and fails differently when
 * the daemon is down. Everything here is decidable from the compose source or
 * the pending shell command.
 *
 * MEASURED CAUSE (this repo, 2026-08-28) — the two shapes below are not
 * hypothetical, they are what produced the sprawl that prompted the rule:
 *
 *   1. 14 of 18 compose files pinned no top-level `name:`, so each project name
 *      defaulted to the parent DIRECTORY. That both fragments (13 distinct
 *      groups) and COLLIDES: `docker` x3, `utils` x2, `test-environment` x2 and
 *      `monitoring` x2 are distinct stacks that silently share one group.
 *   2. 18 of 21 containers carried NO compose project label at all — raw
 *      `docker run`. Against images that declare an anonymous VOLUME (postgres,
 *      mysql, mongo, ...) every such run strands a ~50-80MB volume when the
 *      container is removed. 456 orphans, 25.8GB, were reclaimed on the day
 *      this rule landed.
 */

// The one persistent group every non-example stack in this repo joins.
const CANONICAL_GROUP = "kailash_sdk";

// Images that persist state, so an unnamed volume silently strands data.
// Substring match on the image ref; deliberately a positive ALLOWLIST of known
// stateful images rather than a denylist, so an unknown image is NOT flagged.
const STATEFUL_IMAGES = [
  "postgres", "pgvector", "mysql", "mariadb", "mongo", "redis",
  "elasticsearch", "opensearch", "qdrant", "milvus", "weaviate",
  "minio", "cassandra", "clickhouse", "neo4j", "ollama", "kafka", "zookeeper",
];

const COMPOSE_RE = /(^|\/)(docker-)?compose([.-][\w.-]+)?\.ya?ml$/i;
// Shipped examples users COPY. Pinning our internal group into one would hijack
// the user's own project name, so they are carved out of the group mandate --
// but NOT out of the anonymous-volume check, which is good practice anywhere.
const EXAMPLE_RE = /(^|\/)examples?\//;

function isComposeFile(p) {
  return typeof p === "string" && COMPOSE_RE.test(p);
}
function isExampleCompose(p) {
  return typeof p === "string" && EXAMPLE_RE.test(p);
}
// Sidecars whose image NAME contains a stateful token but which store nothing:
// exporters, admin UIs, CLIs. Measured: a substring-only match flagged
// `mongo-express`, `kafka-ui` and three `*-exporter` services on this repo --
// five false positives out of twelve hits, which is what reading the hits
// rather than the tally revealed (`instrument-discipline.md` MUST-3(b)).
const NON_STATEFUL_MARKERS = [
  "-exporter", "_exporter", "-ui", "express", "-cli", "adminer",
  "commander", "-proxy", "exporter:",
];

function isStatefulImage(ref) {
  if (!ref) return false;
  const r = String(ref).toLowerCase();
  if (NON_STATEFUL_MARKERS.some((s) => r.includes(s))) return false;
  return STATEFUL_IMAGES.some((s) => r.includes(s));
}

/** Top-level `name:` of a compose file, or null. Textual on purpose: a YAML
 *  loader turns the `on`-style bare keys into surprises, and we only need one
 *  top-level scalar that must sit at column 0. */
function composeProjectName(text) {
  const m = /^name:[ \t]*(["']?)([A-Za-z0-9][A-Za-z0-9_.-]*)\1[ \t]*$/m.exec(text || "");
  return m ? m[2] : null;
}

/** Services whose image is stateful but which mount no NAMED volume.
 *  A bind mount (`./x:/y`) is fine -- it is on the host and cannot strand.
 *  An anonymous mount (`/var/lib/postgresql/data` with no source) is the
 *  orphan-maker. */
function anonymousStatefulServices(text) {
  const out = [];
  const src = text || "";
  const svcBlock = /^services:[ \t]*$/m.exec(src);
  if (!svcBlock) return out;
  const body = src.slice(svcBlock.index + svcBlock[0].length);
  // split on 2-space-indented service keys, stop at the next top-level key
  const end = /^[A-Za-z]/m.exec(body);
  const scoped = end ? body.slice(0, end.index) : body;
  const parts = scoped.split(/^ {2}([A-Za-z0-9._-]+):[ \t]*$/m);
  for (let i = 1; i < parts.length; i += 2) {
    const name = parts[i];
    const chunk = parts[i + 1] || "";
    const img = /^\s*image:[ \t]*["']?([^"'\s]+)/m.exec(chunk);
    if (!img || !isStatefulImage(img[1])) continue;
    const volLines = [];
    const vm = /^\s*volumes:[ \t]*$/m.exec(chunk);
    if (vm) {
      const after = chunk.slice(vm.index + vm[0].length);
      for (const line of after.split("\n")) {
        if (/^\s*-\s/.test(line)) volLines.push(line.trim());
        else if (/^\s*[A-Za-z_]/.test(line)) break;
      }
    }
    // The question is whether the data can be STRANDED, not whether the mount is
    // a named volume. Three shapes:
    //   `- name:/path`   NAMED volume  -> durable, findable again
    //   `- ./x:/path`    BIND mount    -> lives on the host, cannot strand
    //   `- /path`        ANONYMOUS     -> stranded the moment the container goes
    // Only the third is the orphan-maker, so a bind counts as durable. Treating
    // a bind as "not named" and flagging it was a real defect the fixtures caught.
    const hasDurableMount = volLines.some((l) => {
      const v = l.replace(/^-\s*/, "").replace(/^["']|["']$/g, "");
      const [source, target] = v.split(":");
      if (!target || !source) return false; // `- /path` -> anonymous
      return true; // named volume OR bind mount -- both durable
    });
    if (!hasDurableMount) out.push({ service: name, image: img[1] });
  }
  return out;
}

/** Findings for a compose file. `path` decides whether the group mandate applies. */
function inspectCompose(path, text) {
  const findings = [];
  const example = isExampleCompose(path);
  if (!example) {
    const name = composeProjectName(text);
    if (!name) {
      findings.push({
        check: "group-unpinned",
        detail:
          "no top-level `name:` — the compose project defaults to the parent " +
          `directory, which both fragments the forest and COLLIDES when two ` +
          `stacks share a directory name. Pin \`name: ${CANONICAL_GROUP}\`.`,
      });
    } else if (name !== CANONICAL_GROUP) {
      findings.push({
        check: "group-wrong",
        detail: `project name is \`${name}\`, not the canonical group \`${CANONICAL_GROUP}\`.`,
      });
    }
  }
  for (const s of anonymousStatefulServices(text)) {
    findings.push({
      check: "anonymous-volume",
      detail:
        `service \`${s.service}\` (image \`${s.image}\`) mounts no NAMED volume, ` +
        `so its data lands in an anonymous volume that is stranded the moment ` +
        `the container is removed.`,
    });
  }
  return findings;
}

/** Findings for a pending shell command. Lexical by nature, so this can only
 *  ever be advisory/halt-and-report -- never `block`. */
function inspectDockerRun(command) {
  const cmd = String(command || "");
  // `docker run` / `docker container run`, not `docker compose run`.
  if (!/\bdocker\s+(container\s+)?run\b/.test(cmd)) return [];
  if (/\bdocker\s+compose\b/.test(cmd)) return [];
  const img = /\b(?:docker\s+(?:container\s+)?run\b[^|;&]*?)\s((?!-)[A-Za-z0-9][\w./-]*(?::[\w.-]+)?)\s*(?:$|[|;&])/.exec(cmd);
  const imageRef = img ? img[1] : (cmd.match(/\s([a-z0-9]+\/[\w.-]+:[\w.-]+)/) || [])[1];
  if (!isStatefulImage(imageRef) && !STATEFUL_IMAGES.some((s) => cmd.toLowerCase().includes(s))) return [];
  const findings = [];
  const hasNamedVol = /-v\s+[A-Za-z][\w.-]*:/.test(cmd) || /--mount[^|;&]*source=[A-Za-z]/.test(cmd);
  const hasRm = /\s--rm\b/.test(cmd);
  if (!hasNamedVol && !hasRm) {
    findings.push({
      check: "ungrouped-run",
      detail:
        "a stateful `docker run` with neither a NAMED volume nor `--rm`: it joins " +
        "no compose group and strands an anonymous volume when removed. Prefer a " +
        `compose service in the \`${CANONICAL_GROUP}\` group; if it must be a bare ` +
        "run, add `--rm` (throwaway) or `-v <name>:/path` (persistent).",
    });
  }
  return findings;
}

module.exports = {
  CANONICAL_GROUP,
  STATEFUL_IMAGES,
  isComposeFile,
  isExampleCompose,
  isStatefulImage,
  composeProjectName,
  anonymousStatefulServices,
  inspectCompose,
  inspectDockerRun,
};
