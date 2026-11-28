import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const webRoot = path.resolve(import.meta.dirname, "..");
const appDir = path.join(webRoot, "app");
const testsDir = path.join(webRoot, "tests");

function collectPageRoutes(dir, prefix = "") {
  const routes = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "api") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      routes.push(...collectPageRoutes(full, `${prefix}/${entry.name}`));
    } else if (entry.name === "page.tsx") {
      routes.push(prefix || "/");
    }
  }
  return routes;
}

function collectSpecContents(dir) {
  let combined = "";
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      combined += collectSpecContents(full);
    } else if (entry.name.endsWith(".spec.ts")) {
      combined += "\n" + fs.readFileSync(full, "utf8");
    }
  }
  return combined;
}

test("Route coverage gate: every Next.js page route is referenced by at least one .spec.ts", () => {
  const routes = collectPageRoutes(appDir).sort();
  const specsText = collectSpecContents(testsDir);
  const uncovered = routes.filter((route) => !specsText.includes(`"${route}"`) && !specsText.includes(`'${route}'`));
  assert.deepEqual(
    uncovered,
    [],
    `Uncovered Next.js routes without any Playwright .spec.ts reference: ${uncovered.join(", ")}`,
  );
});
