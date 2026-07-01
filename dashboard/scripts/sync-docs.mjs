// Copy the repo's living docs into the dashboard so /docs renders THE actual
// markdown, not a hand-written snapshot. Runs automatically before every build
// (npm prebuild) — Vercel rebuilds on every merge to main, so the deploy
// pipeline itself keeps the dashboard docs in sync with the code. No agent,
// no cron: merging IS the update.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const outDir = join(here, "..", "content");

const SOURCES = [
  ["docs/SCOPE.md", "SCOPE.md"],
  ["docs/OPERATIONS.md", "OPERATIONS.md"],
  ["RUNBOOK.md", "RUNBOOK.md"],
];

mkdirSync(outDir, { recursive: true });
let copied = 0;
for (const [src, dst] of SOURCES) {
  const from = join(repoRoot, src);
  if (!existsSync(from)) {
    console.warn(`sync-docs: missing ${src} (skipped)`);
    continue;
  }
  copyFileSync(from, join(outDir, dst));
  copied++;
}
console.log(`sync-docs: copied ${copied}/${SOURCES.length} docs into dashboard/content/`);
