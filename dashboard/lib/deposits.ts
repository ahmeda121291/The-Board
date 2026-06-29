// Original deposits per venue (CAD). These are your funding baseline — the
// "start balance" the system grows from. Override via env if you add more later;
// defaults reflect the $100 Kraken (crypto) + $100 Interactive Brokers (equities) launch.
export function deposits() {
  const kraken = Number(process.env.KRAKEN_DEPOSIT_CAD ?? "100");
  // IBKR_DEPOSIT_CAD is canonical; WEALTHSIMPLE_DEPOSIT_CAD kept as a fallback so
  // an older env var still resolves.
  const ibkr = Number(
    process.env.IBKR_DEPOSIT_CAD ?? process.env.WEALTHSIMPLE_DEPOSIT_CAD ?? "100",
  );
  return {
    kraken: Number.isFinite(kraken) ? kraken : 100,
    ibkr: Number.isFinite(ibkr) ? ibkr : 100,
    get total() {
      return this.kraken + this.ibkr;
    },
  };
}
