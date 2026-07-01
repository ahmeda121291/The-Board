import { Pill } from "@/components/ui";
import { Countdown } from "@/components/Countdown";
import type { PendingRequest, RunRow } from "@/lib/data";
import { ago, cad } from "@/lib/format";

// The precondition strip: is the machine alive, armed, and telling the truth?
// Everything here is an honest tri-state — "breakers clear" only appears when
// they were actually evaluated; a crashed run shows as a crash, not silence.

const TRIGGER_LABEL: Record<string, string> = {
  scheduled: "scheduled checkpoint",
  run_now: "Run-now click",
  wide: "wide scan",
  decide: "manual decide",
  manual: "manual run",
};

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-[130px]">
      <div className="label">{label}</div>
      <div className="mt-1 text-sm text-slate-200">{children}</div>
    </div>
  );
}

export function HealthStrip({
  tradedLive,
  armedLive,
  equity,
  equitySyncedAt,
  targetIso,
  checkpointTimes,
  lastRun,
  schedulerSeenAt,
  pollerSeenAt,
  pendingRequests,
}: {
  tradedLive: boolean;
  armedLive: boolean;
  equity: number;
  equitySyncedAt: string | null;
  targetIso: string;
  checkpointTimes: string;
  lastRun: RunRow | null;
  schedulerSeenAt: string | null;
  pollerSeenAt: string | null;
  pendingRequests: PendingRequest[];
}) {
  const pollerAlive =
    pollerSeenAt !== null && Date.now() - new Date(pollerSeenAt).getTime() < 3 * 60 * 1000;
  const schedulerRecent =
    schedulerSeenAt !== null && Date.now() - new Date(schedulerSeenAt).getTime() < 26 * 3600 * 1000;
  const stuck = pendingRequests.filter(
    (r) => Date.now() - new Date(r.created_at).getTime() > 3 * 60 * 1000,
  );

  const runTone =
    lastRun === null
      ? "default"
      : lastRun.status === "crashed"
      ? "bad"
      : lastRun.status === "running"
      ? "warn"
      : "good";

  return (
    <div className="glass hud mt-5 p-4">
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <Cell label="Mode">
          <span className="flex items-center gap-2">
            <span className={tradedLive || armedLive ? "dot dot-live" : "dot"} />
            <span className={tradedLive ? "text-rose-300" : armedLive ? "text-emerald-300" : ""}>
              {tradedLive ? "LIVE TRADING" : armedLive ? "LIVE · ARMED" : "dry-run · safe"}
            </span>
          </span>
        </Cell>

        <Cell label="Equity">
          <span className="num font-semibold text-sky-300">{cad(equity)}</span>
          <span className="ml-2 text-xs text-slate-500">
            {equitySyncedAt ? `synced ${ago(equitySyncedAt)}` : "baseline estimate"}
          </span>
        </Cell>

        <Cell label="Next checkpoint">
          <span className="num text-lg font-bold">
            <Countdown targetIso={targetIso} />
          </span>
          <span className="ml-2 text-xs text-slate-500">{checkpointTimes} UTC</span>
        </Cell>

        <Cell label="Last run">
          {lastRun ? (
            <span className="flex flex-wrap items-center gap-2">
              <Pill tone={runTone}>
                {lastRun.status === "crashed"
                  ? "⚠ CRASHED"
                  : lastRun.status === "running"
                  ? "running…"
                  : "completed"}
              </Pill>
              <span className="text-xs text-slate-400">
                {TRIGGER_LABEL[lastRun.trigger] ?? lastRun.trigger} · {ago(lastRun.started_at)}
              </span>
            </span>
          ) : (
            <span className="text-xs text-slate-500">no runs recorded yet</span>
          )}
        </Cell>

        <Cell label="Breakers">
          {lastRun?.breakers_evaluated ? (
            lastRun.breakers.length > 0 ? (
              <Pill tone="bad">⚠ TRIPPED</Pill>
            ) : (
              <Pill tone="good">evaluated · clear</Pill>
            )
          ) : (
            <Pill tone="warn">not evaluated yet</Pill>
          )}
        </Cell>

        <Cell label="Machines">
          <span className="flex flex-wrap items-center gap-2 text-xs">
            <Pill tone={schedulerRecent ? "good" : "warn"}>
              scheduler {schedulerRecent ? "on" : "silent"}
            </Pill>
            <Pill tone={pollerAlive ? "good" : "warn"}>
              poller {pollerAlive ? "alive" : pollerSeenAt ? `last ${ago(pollerSeenAt)}` : "unknown"}
            </Pill>
          </span>
        </Cell>
      </div>

      {lastRun?.status === "crashed" ? (
        <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-400/[0.06] p-3 text-xs text-rose-200">
          The last run crashed mid-checkpoint{lastRun.error ? `: ${lastRun.error}` : "."} Any fill
          it made is still recorded below; check <code>logs\poller.log</code> /{" "}
          <code>logs\scheduler.log</code> on the PC.
        </div>
      ) : null}

      {stuck.length > 0 ? (
        <div className="mt-3 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] p-3 text-xs text-amber-200">
          {stuck.length} “Run now” request{stuck.length > 1 ? "s" : ""} queued for{" "}
          {ago(stuck[stuck.length - 1].created_at).replace(" ago", "")} without being picked up — the
          poller on the PC looks down. Restart it (or reboot the PC) and the queue drains.
        </div>
      ) : null}
    </div>
  );
}
