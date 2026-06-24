// Original deposits per venue (CAD). These are your funding baseline — the
// "start balance" the system grows from. Override via env if you add more later;
// defaults reflect the $100 Kraken + $100 Wealthsimple launch.
export function deposits() {
  const kraken = Number(process.env.KRAKEN_DEPOSIT_CAD ?? "100");
  const wealthsimple = Number(process.env.WEALTHSIMPLE_DEPOSIT_CAD ?? "100");
  return {
    kraken: Number.isFinite(kraken) ? kraken : 100,
    wealthsimple: Number.isFinite(wealthsimple) ? wealthsimple : 100,
    get total() {
      return this.kraken + this.wealthsimple;
    },
  };
}
