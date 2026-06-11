#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const reportDir = path.resolve(process.argv[2] || "docs");

function existing(paths) {
  return paths.filter((file) => fs.existsSync(file));
}

function htmlFiles() {
  const fixed = [
    "index.html",
    "library.html",
    "board.html",
    "workflow.html",
    "status.html",
    "pivot.html",
    "compare.html",
    "taxonomy_map.html",
    "clusters.html",
    "roadmap.html",
    "scale.html",
    "ownership.html",
    "routing.html",
    "onboarding.html",
    "catalog.html",
    "intake.html",
    "inbox.html",
    "dedupe.html",
    "quality.html",
    "review.html",
    "freshness.html",
    "dashboard.html",
    "release.html",
    "snapshot.html",
    "actions.html",
    "collections.html",
    "balance.html",
    "coverage.html",
    "facets.html",
    "related.html",
    "taxonomy.html",
    "timeline.html",
    "matrix.html",
    "gaps.html",
    "tags.html",
    "lines/index.html",
  ].map((relative) => path.join(reportDir, relative));
  const linesDir = path.join(reportDir, "lines");
  const linePages = fs.existsSync(linesDir)
    ? fs
        .readdirSync(linesDir)
        .filter((name) => name.endsWith(".html") && name !== "index.html")
        .map((name) => path.join(linesDir, name))
    : [];
  return existing([...fixed, ...linePages]);
}

function inlineScripts(html) {
  return [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
    .map((match) => match[1])
    .filter((source) => source.trim());
}

const failures = [];
for (const file of htmlFiles()) {
  const html = fs.readFileSync(file, "utf8");
  inlineScripts(html).forEach((source, index) => {
    try {
      new Function(source);
    } catch (error) {
      failures.push(`${path.relative(process.cwd(), file)} script ${index + 1}: ${error.message}`);
    }
  });
}

if (failures.length) {
  console.error("Inline wiki script validation failed:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`Inline wiki scripts ok (${htmlFiles().length} pages)`);
