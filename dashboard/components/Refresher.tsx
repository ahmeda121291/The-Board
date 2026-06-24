"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// Periodically re-fetches the server component data so the hub stays live
// without a manual reload. Shows a subtle "updating…" tick.
export function Refresher({ intervalMs = 45000 }: { intervalMs?: number }) {
  const router = useRouter();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      router.refresh();
      setTick((t) => t + 1);
    }, intervalMs);
    return () => clearInterval(id);
  }, [router, intervalMs]);

  return (
    <span className="text-xs text-muted">
      auto-refresh {Math.round(intervalMs / 1000)}s{tick > 0 ? " · live" : ""}
    </span>
  );
}
