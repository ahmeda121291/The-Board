import { Pill } from "@/components/ui";
import { when, cad } from "@/lib/format";
import type { Decision, Session } from "@/lib/data";

type DivTone = "cyan" | "good" | "default" | "warn";

const dotColor: Record<DivTone, string> = {
  cyan: "bg-sky-400",
  good: "bg-emerald-400",
  warn: "bg-amber-400",
  default: "bg-slate-500",
};

function divisionTone(status: string): DivTone {
  if (status.startsWith("pitched")) return "cyan";
  if (status.startsWith("floor")) return "good";
  if (status.startsWith("disabled")) return "default";
  return "warn";
}

function kindTone(kind: string): "good" | "warn" | "default" {
  if (kind === "fund") return "good";
  if (kind === "hold") return "warn";
  return "default";
}

function asSession(ranked: Decision["ranked"]): Session | null {
  if (ranked && typeof ranked === "object" && !Array.isArray(ranked)) {
    return ranked as Session;
  }
  return null;
}

export function SessionHistory({ decisions }: { decisions: Decision[] }): JSX.Element {
  return (
    <div className="space-y-3">
      {decisions.slice(0, 6).map((d) => {
        const session = asSession(d.ranked);
        const pitches = session?.pitches ?? [];
        const vetoed = pitches.filter((p) => p.status === "vetoed").length;
        const funded = pitches.find((p) => p.status === "funded");
        const summary =
          pitches.length > 0
            ? `${pitches.length} pitched · ${vetoed} vetoed · ${
                funded ? "funded " + funded.division : "held the floor"
              }`
            : null;

        return (
          <div key={d.decision_id} className="glass p-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">{when(d.created_at)}</span>
              <Pill tone={kindTone(d.kind)}>{d.kind.toUpperCase()}</Pill>
              {d.kind === "fund" && d.division ? (
                <span className="text-sm">
                  {d.division} {cad(d.size_cad)}
                </span>
              ) : null}
              <span className="ml-auto">
                <Pill tone={d.live ? "bad" : "default"}>{d.live ? "live" : "dry"}</Pill>
              </span>
            </div>

            {session && session.divisions && session.divisions.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                {session.divisions.map((div) => {
                  const tone = divisionTone(div.status);
                  return (
                    <span
                      key={div.division}
                      className="inline-flex items-center gap-1 text-[11px] text-slate-400"
                    >
                      <span
                        className={"inline-block h-1.5 w-1.5 rounded-full " + dotColor[tone]}
                      />
                      {div.division}
                    </span>
                  );
                })}
              </div>
            ) : null}

            {session ? (
              summary ? (
                <div className="mt-2 text-xs text-slate-400">{summary}</div>
              ) : null
            ) : (
              <div className="mt-2 truncate text-xs text-slate-400">{d.rationale || "—"}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
