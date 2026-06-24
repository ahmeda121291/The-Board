import { cad } from "@/lib/format";

type Point = { t: string; equity: number };

const shortDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" });

export function EquityChart({
  points,
  start,
}: {
  points: Point[];
  start: number;
}): JSX.Element {
  const latest = points.length > 0 ? points[points.length - 1].equity : start;
  const up = latest >= start;
  const delta = latest - start;
  const deltaLabel = `${delta >= 0 ? "▲" : "▼"} ${cad(Math.abs(delta))}`;

  const valueClass = up
    ? "num text-3xl font-bold text-emerald-400 glow-cyan"
    : "num text-3xl font-bold text-rose-400";

  const Header = (
    <div className="flex items-end justify-between gap-4">
      <div>
        <div className="label">Equity</div>
        <div className={valueClass}>{cad(latest)}</div>
      </div>
      <div className={`text-sm ${up ? "text-emerald-400" : "text-rose-400"}`}>
        {deltaLabel}
      </div>
    </div>
  );

  if (points.length < 2) {
    return (
      <div className="glass hud p-5">
        {Header}
        <div className="mt-4 text-sm text-slate-500">
          Not enough history yet — the equity curve appears as decisions resolve.
        </div>
      </div>
    );
  }

  const n = points.length;

  // y-range includes the baseline so it stays visible; padded ~5%.
  const equities = points.map((p) => p.equity);
  let lo = Math.min(start, ...equities);
  let hi = Math.max(start, ...equities);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    lo = start;
    hi = start;
  }
  const rawRange = hi - lo;
  const pad = rawRange === 0 ? 1 : rawRange * 0.05;
  lo -= pad;
  hi += pad;
  const range = hi - lo;

  const H = 36;
  const x = (i: number): number => (i / (n - 1)) * 100;
  // Inverted: higher equity -> smaller y. Flat mid-line when range collapses.
  const y = (equity: number): number =>
    range === 0 ? H / 2 : H - ((equity - lo) / range) * H;

  const linePts = points.map((p, i) => `${x(i).toFixed(3)},${y(p.equity).toFixed(3)}`);
  const linePath = `M ${linePts.join(" L ")}`;
  const areaPath = `${linePath} L 100,${H} L 0,${H} Z`;
  const baseY = y(start);

  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const gradId = "equityFill";

  return (
    <div className="glass hud p-5">
      {Header}
      <div className="mt-4 w-full" style={{ height: 140 }}>
        <svg
          viewBox={`0 0 100 ${H}`}
          className="w-full"
          style={{ height: 140 }}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
            </linearGradient>
          </defs>

          {/* Baseline at starting balance */}
          <line
            x1={0}
            y1={baseY}
            x2={100}
            y2={baseY}
            stroke="rgb(100 116 139 / 0.4)"
            strokeDasharray="2 2"
            strokeWidth={0.3}
          />

          {/* Filled area under the curve */}
          <path d={areaPath} fill={`url(#${gradId})`} stroke="none" />

          {/* Equity line */}
          <path
            d={linePath}
            fill="none"
            stroke="#38bdf8"
            strokeWidth={0.6}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
        <span>{shortDate(points[0].t)}</span>
        <span className="num">
          {cad(minEquity)} – {cad(maxEquity)}
        </span>
        <span>{shortDate(points[n - 1].t)}</span>
      </div>
    </div>
  );
}
