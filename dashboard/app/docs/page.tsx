import Link from "next/link";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { marked } from "marked";

export const dynamic = "force-dynamic";

// The docs page renders the repo's ACTUAL living docs (docs/SCOPE.md,
// docs/OPERATIONS.md, RUNBOOK.md), synced into content/ at build time by
// scripts/sync-docs.mjs. Every merge to main redeploys and re-syncs — the
// deploy pipeline is the docs-update loop, so this page can never drift from
// the code the way the old hand-written version did.

const DOCS: { file: string; title: string; blurb: string }[] = [
  {
    file: "SCOPE.md",
    title: "The living scope",
    blurb: "The canonical spec — updated in the same commit as every behavior change.",
  },
  {
    file: "OPERATIONS.md",
    title: "Operations & risk model",
    blurb: "How it scans, the checkpoint order, the hard caps and breakers.",
  },
  {
    file: "RUNBOOK.md",
    title: "Runbook",
    blurb: "Going live, credentials, the Windows scheduler and poller.",
  },
];

async function loadDoc(file: string): Promise<string | null> {
  try {
    const raw = await readFile(join(process.cwd(), "content", file), "utf-8");
    return await marked.parse(raw);
  } catch {
    return null;
  }
}

export default async function DocsPage() {
  const rendered = await Promise.all(DOCS.map(async (d) => ({ ...d, html: await loadDoc(d.file) })));

  return (
    <main className="mx-auto max-w-4xl px-5 py-8">
      <header className="flex items-center gap-4">
        <div>
          <h1 className="title-grad text-3xl font-bold tracking-tight">DOCS</h1>
          <p className="mt-1 text-xs uppercase tracking-[0.25em] text-slate-500">
            rendered from the repo — always in sync with the code
          </p>
        </div>
        <Link
          href="/"
          className="ml-auto rounded-full border border-white/15 px-3 py-1.5 text-xs text-slate-300 hover:border-white/30 hover:bg-white/5"
        >
          ← back to dashboard
        </Link>
      </header>

      <nav className="glass mt-6 flex flex-wrap gap-3 p-4 text-sm">
        {rendered.map((d) => (
          <a key={d.file} href={`#${d.file}`} className="text-sky-300 hover:underline">
            {d.title}
          </a>
        ))}
        <a
          href="https://github.com/ahmeda121291/the-board/tree/main/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-slate-400 hover:text-slate-200"
        >
          view on GitHub ↗
        </a>
      </nav>

      {rendered.map((d) => (
        <section key={d.file} id={d.file} className="mt-8">
          <div className="flex items-center gap-3">
            <span className="h-3 w-1 rounded-full bg-gradient-to-b from-sky-400 to-violet-500" />
            <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">
              {d.title}
            </h2>
          </div>
          <p className="mt-1 pl-4 text-xs text-slate-500">{d.blurb}</p>
          {d.html ? (
            <article
              className="prose-docs glass mt-3 p-6"
              dangerouslySetInnerHTML={{ __html: d.html }}
            />
          ) : (
            <div className="glass mt-3 p-4 text-sm text-slate-400">
              Not synced in this build — run <code className="text-sky-300">npm run build</code> (the
              prebuild step copies the repo docs in).
            </div>
          )}
        </section>
      ))}

      <footer className="mt-12 border-t border-white/10 pt-4 text-xs text-slate-500">
        Synced from <code className="text-sky-300">docs/</code> at build time · every merge to main
        redeploys and refreshes this page.
      </footer>
    </main>
  );
}
