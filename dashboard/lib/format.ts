export const cad = (n: number | null | undefined) =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);

export const pct = (n: number | null | undefined, digits = 2) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : `${(n * 100).toFixed(digits)}%`;

export const num = (n: number | null | undefined, digits = 4) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(digits);

// A quoted instrument price ($). Sub-dollar (e.g. some crypto) gets more digits.
export const price = (n: number | null | undefined) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const digits = Math.abs(n) >= 1 ? 2 : 6;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

// A share/unit count. Whole-ish numbers shown compact; fractional kept precise.
export const qty = (n: number | null | undefined) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n >= 1
    ? n.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : n.toFixed(4);
};

// Division enum value → display label ("crypto_trend" → "crypto trend"; the
// CSS `capitalize` class then title-cases it to "Crypto Trend").
export const divLabel = (s: string | null | undefined) => (s ?? "—").replace(/_/g, " ");

export const when = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" });
};

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
};
