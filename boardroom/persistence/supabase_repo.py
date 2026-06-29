"""Supabase-backed repository (Postgres schema ``boardroom``).

Uses the service key — full read/write to the metrics DB, NO trading power. The
schema is created by ``supabase/migrations`` and exposed to PostgREST there.
"""

from __future__ import annotations

import json

from datetime import datetime

from boardroom.config import get_settings
from boardroom.persistence.repository import DivisionState, OpenPosition, Repository
from boardroom.schemas import Decision, Division, Pitch, ProcessLuckTag, ResolvedOutcome

_SCHEMA = "boardroom"


def _jsonable(obj) -> dict:
    return json.loads(obj.model_dump_json()) if hasattr(obj, "model_dump_json") else obj


class SupabaseRepository(Repository):
    def __init__(self) -> None:
        from supabase import create_client

        s = get_settings()
        self._client = create_client(s.supabase_url, s.supabase_service_key.get_secret_value())

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    # ---- writes --------------------------------------------------------------
    def save_pitch(self, pitch: Pitch) -> None:
        p = _jsonable(pitch)
        self._t("pitches").upsert(
            {
                "pitch_id": pitch.pitch_id,
                "division": pitch.division.value,
                "venue": pitch.venue.value,
                "symbol": pitch.symbol,
                "created_at": pitch.created_at.isoformat(),
                "capital_required": pitch.capital_required,
                "expected_return": pitch.expected_return,
                "confidence": pitch.confidence,
                "time_horizon_days": pitch.time_horizon_days,
                "max_loss": pitch.max_loss,
                "expected_cost": pitch.expected_cost,
                "opportunity": pitch.opportunity,
                "why_now": pitch.why_now,
                "snapshot": p["snapshot"],
                "signals": p["signals"],
            }
        ).execute()

    def save_decision(self, decision: Decision, ranking: list[dict]) -> None:
        self._t("decisions").upsert(
            {
                "decision_id": decision.decision_id,
                "created_at": decision.created_at.isoformat(),
                "kind": decision.kind.value,
                "division": decision.division.value if decision.division else None,
                "pitch_id": decision.pitch_id,
                "size_cad": decision.size_cad,
                "hurdle_rate": decision.hurdle_rate,
                "rationale": decision.rationale,
                "ranked": ranking,
                "live": decision.live,
            }
        ).execute()

    def save_outcome(self, outcome: ResolvedOutcome) -> None:
        self._t("outcomes").insert(
            {
                "decision_id": outcome.decision_id,
                "division": outcome.division.value,
                "resolved_at": outcome.resolved_at.isoformat(),
                "predicted_return": outcome.predicted_return,
                "realized_return": outcome.realized_return,
                "predicted_confidence": outcome.predicted_confidence,
                "win": outcome.win,
                "pnl_cad": outcome.pnl_cad,
                "cost_cad": outcome.cost_cad,
                "inside_band": outcome.inside_band,
                "process_luck": outcome.process_luck.value if outcome.process_luck else None,
                "postmortem": outcome.postmortem,
            }
        ).execute()

    def upsert_division_state(self, state: DivisionState) -> None:
        self._t("division_state").upsert(
            {
                "division": state.division,
                "alpha": state.alpha,
                "beta": state.beta,
                "leash": state.leash,
                "retired": state.retired,
                "shadow": state.shadow,
                "n_resolved": state.n_resolved,
                "net_vs_floor_cad": state.net_vs_floor_cad,
            }
        ).execute()

    def save_performance(self, snapshot: dict) -> None:
        self._t("performance_snapshots").insert({"payload": snapshot}).execute()

    def save_weekly_report(self, report: str, payload: dict) -> None:
        self._t("weekly_reports").insert({"report": report, "payload": payload}).execute()

    def audit(self, event: str, payload: dict) -> None:
        self._t("audit_log").insert({"event": event, "payload": payload}).execute()

    def get_system_state(self) -> dict:
        res = self._t("system_state").select("*").eq("id", 1).limit(1).execute()
        if res.data:
            row = res.data[0]
            return {
                "reserve_cad": row["reserve_cad"],
                "hwm_cad": row["hwm_cad"],
                "live_armed": bool(row.get("live_armed", False)),
            }
        return {"reserve_cad": 0.0, "hwm_cad": 0.0, "live_armed": False}

    def set_system_state(self, reserve_cad: float, hwm_cad: float) -> None:
        self._t("system_state").upsert(
            {"id": 1, "reserve_cad": reserve_cad, "hwm_cad": hwm_cad}
        ).execute()

    def set_live_armed(self, armed: bool) -> None:
        self._t("system_state").upsert({"id": 1, "live_armed": bool(armed)}).execute()

    def claim_next_run_request(self) -> dict | None:
        from datetime import datetime, timezone

        res = (
            self._t("run_requests")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        # Conditional claim: only succeeds if it's still pending (guards against
        # two pollers grabbing the same row).
        upd = (
            self._t("run_requests")
            .update({"status": "running", "claimed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", row["id"])
            .eq("status", "pending")
            .execute()
        )
        return upd.data[0] if upd.data else None

    def complete_run_request(
        self, request_id: int, status: str, result: dict, decision_id: str | None = None
    ) -> None:
        from datetime import datetime, timezone

        self._t("run_requests").update(
            {
                "status": status,
                "result": result,
                "decision_id": decision_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", request_id).execute()

    def save_strategy_review(
        self, headline: str, narrative: str, recommendations: list, standing: dict
    ) -> None:
        self._t("strategist_reviews").insert(
            {
                "headline": headline,
                "narrative": narrative,
                "recommendations": recommendations,
                "standing": standing,
            }
        ).execute()

    def recent_strategy_reviews(self, limit: int = 10) -> list[dict]:
        res = (
            self._t("strategist_reviews")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    # ---- open positions ------------------------------------------------------
    def save_open_position(self, position: OpenPosition) -> None:
        self._t("open_positions").upsert(
            {
                "decision_id": position.decision_id,
                "division": position.division,
                "venue": position.venue,
                "symbol": position.symbol,
                "size_cad": position.size_cad,
                "predicted_return": position.predicted_return,
                "predicted_confidence": position.predicted_confidence,
                "cost_cad": position.cost_cad,
                "stop_fraction": position.stop_fraction,
                "band_low": position.band_low,
                "band_high": position.band_high,
                "horizon_days": position.horizon_days,
                "opened_at": position.opened_at.isoformat(),
                "live": position.live,
            }
        ).execute()

    def open_positions(self) -> list[OpenPosition]:
        res = self._t("open_positions").select("*").execute()
        out: list[OpenPosition] = []
        for row in res.data or []:
            out.append(
                OpenPosition(
                    decision_id=row["decision_id"],
                    division=row["division"],
                    venue=row["venue"],
                    symbol=row["symbol"],
                    size_cad=row["size_cad"],
                    predicted_return=row["predicted_return"],
                    predicted_confidence=row["predicted_confidence"],
                    cost_cad=row["cost_cad"],
                    stop_fraction=row["stop_fraction"],
                    band_low=row["band_low"],
                    band_high=row["band_high"],
                    horizon_days=row["horizon_days"],
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    live=bool(row.get("live", False)),
                )
            )
        return out

    def close_position(self, decision_id: str) -> None:
        self._t("open_positions").delete().eq("decision_id", decision_id).execute()

    # ---- model params --------------------------------------------------------
    def get_model_params(self, division: str) -> dict | None:
        res = self._t("model_params").select("*").eq("division", division).limit(1).execute()
        if res.data:
            return res.data[0].get("params")
        return None

    def save_model_params(self, division: str, params: dict) -> None:
        self._t("model_params").upsert({"division": division, "params": params}).execute()

    # ---- reads ---------------------------------------------------------------
    def get_division_state(self, division: str) -> DivisionState:
        res = self._t("division_state").select("*").eq("division", division).limit(1).execute()
        if res.data:
            row = res.data[0]
            return DivisionState(
                division=row["division"],
                alpha=row["alpha"],
                beta=row["beta"],
                leash=row["leash"],
                retired=row["retired"],
                shadow=row["shadow"],
                n_resolved=row["n_resolved"],
                net_vs_floor_cad=row["net_vs_floor_cad"],
            )
        state = DivisionState(division=division)
        self.upsert_division_state(state)
        return state

    def recent_outcomes(self, division: str | None = None, limit: int = 200) -> list[ResolvedOutcome]:
        q = self._t("outcomes").select("*").order("resolved_at", desc=True).limit(limit)
        if division:
            q = q.eq("division", division)
        res = q.execute()
        out: list[ResolvedOutcome] = []
        for row in res.data:
            out.append(
                ResolvedOutcome(
                    decision_id=row["decision_id"],
                    division=Division(row["division"]),
                    predicted_return=row["predicted_return"],
                    realized_return=row["realized_return"],
                    predicted_confidence=row["predicted_confidence"],
                    win=row["win"],
                    pnl_cad=row["pnl_cad"],
                    cost_cad=row["cost_cad"],
                    inside_band=row["inside_band"],
                    process_luck=ProcessLuckTag(row["process_luck"]) if row["process_luck"] else None,
                    postmortem=row.get("postmortem", ""),
                )
            )
        return out
