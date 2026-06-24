"use client";

import { useEffect, useState } from "react";

// Live HH:MM:SS countdown to an ISO target. Mounted-guarded to avoid hydration
// mismatch (server time != client time).
export function Countdown({ targetIso }: { targetIso: string }) {
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState(0);

  useEffect(() => {
    setMounted(true);
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!mounted) return <span className="num tabular-nums">--:--:--</span>;

  let diff = new Date(targetIso).getTime() - now;
  if (diff < 0) diff = 0;
  const hrs = Math.floor(diff / 3.6e6);
  const mins = Math.floor((diff % 3.6e6) / 6e4);
  const secs = Math.floor((diff % 6e4) / 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const imminent = diff < 5 * 60 * 1000;

  return (
    <span className={`num tabular-nums ${imminent ? "text-amber-300" : "text-sky-300 glow-cyan"}`}>
      {pad(hrs)}:{pad(mins)}:{pad(secs)}
    </span>
  );
}
