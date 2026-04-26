import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";

const dashboardPagePath = path.resolve(process.cwd(), "src/app/dashboard/page.tsx");

function readDashboardSource() {
  return fs.readFileSync(dashboardPagePath, "utf-8");
}

test("Dashboard view contract: metadata title is stable", () => {
  const source = readDashboardSource();
  assert.match(source, /title:\s*"Overview — AI Media OS"/);
});

test("Dashboard view contract: critical sections are present", () => {
  const source = readDashboardSource();

  assert.match(source, /<PageHeader/);
  assert.match(source, /<MetricsGrid\s*\/>/);
  assert.match(source, /<OverviewChart\s*\/>/);
  assert.match(source, /<ActivityFeed\s*\/>/);
  assert.match(source, /<RecommendationPanel\s*\/>/);
});
