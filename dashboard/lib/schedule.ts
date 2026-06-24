// Next daily checkpoint (UTC HH:MM) as an ISO string, strictly in the future.
export function nextCheckpointIso(checkpointUtc: string, from = new Date()): string {
  const [hStr, mStr] = (checkpointUtc || "19:00").split(":");
  let h = parseInt(hStr, 10);
  let m = parseInt(mStr, 10);
  if (!Number.isFinite(h) || h < 0 || h > 23) h = 19;
  if (!Number.isFinite(m) || m < 0 || m > 59) m = 0;
  const t = new Date(
    Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate(), h, m, 0, 0),
  );
  if (t.getTime() <= from.getTime()) t.setUTCDate(t.getUTCDate() + 1);
  return t.toISOString();
}
