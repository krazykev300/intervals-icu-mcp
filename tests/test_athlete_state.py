"""Tests for athlete-state compute helpers and the composite tool."""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import Response

from intervals_icu_mcp.athlete_state_compute import (
    current_fitness,
    derive_phase_context,
    durability_from_streams,
    fitness_points,
    gaps,
    readiness_block,
    tsb_tolerance,
    weekly_fitness_series,
)
from intervals_icu_mcp.models import Event, Wellness
from intervals_icu_mcp.tools.athlete_state import _durability_cache, get_athlete_state


def _ctx(config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=config)
    return ctx


def _daily_tsb(start: date, values: list[float]) -> list[dict]:
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "ctl": 80.0, "atl": 80.0 - v, "tsb": v}
        for i, v in enumerate(values)
    ]


class TestTsbTolerance:
    def test_eight_excursions_median_three_day_recovery(self):
        """Spec case: eight sub-25 dips that recover in three days."""
        start = date(2026, 1, 1)
        values: list[float] = []
        # 16 weeks: every other week a 2-day -30 dip, recover to -8 on day 3.
        for week in range(16):
            if week % 2 == 0:
                values.extend([-30.0, -30.0, -12.0, -8.0, 2.0, 4.0, 5.0])
            else:
                values.extend([5.0] * 7)
        daily = _daily_tsb(start, values)
        result = tsb_tolerance(daily)
        assert result["min_observed"] == -30.0
        assert result["excursions_below_-25"] == 8
        assert result["median_days_to_recover"] == 3.0


class TestPhaseContext:
    def test_derived_from_future_race_a(self):
        today = date(2026, 9, 16)
        events = [
            Event.model_validate(
                {
                    "id": 1,
                    "start_date_local": "2026-10-04",
                    "name": "Diablo",
                    "category": "RACE_A",
                    "type": "Ride",
                }
            )
        ]
        ctx = derive_phase_context(events, today)
        assert ctx["source"] == "derived_from_race"
        assert ctx["current_phase"] == "peak"
        assert ctx["anchor_event_id"] == 1

    def test_atp_plan_wins(self):
        today = date(2026, 9, 16)
        events = [
            Event.model_validate(
                {
                    "id": 9,
                    "start_date_local": "2026-08-01",
                    "end_date_local": "2026-10-01",
                    "name": "Season",
                    "category": "PLAN",
                    "tags": ["Build"],
                }
            ),
            Event.model_validate(
                {
                    "id": 1,
                    "start_date_local": "2026-10-04",
                    "name": "Diablo",
                    "category": "RACE_A",
                }
            ),
        ]
        ctx = derive_phase_context(events, today)
        assert ctx["source"] == "atp"
        assert ctx["current_phase"] == "build"

    def test_unspecified_without_race_or_atp(self):
        ctx = derive_phase_context([], date(2026, 9, 16))
        assert ctx["source"] == "unspecified"
        assert ctx["current_phase"] is None


class TestFitnessSeries:
    def test_weekly_downsample_and_current(self):
        today = date(2026, 1, 14)
        records = [
            Wellness.model_validate({"id": "2026-01-05", "ctl": 80.0, "atl": 70.0, "tsb": 10.0}),
            Wellness.model_validate({"id": "2026-01-12", "ctl": 82.0, "atl": 75.0, "tsb": 7.0}),
            Wellness.model_validate({"id": "2026-01-14", "ctl": 83.0, "atl": 76.0, "tsb": 7.0}),
        ]
        daily = fitness_points(records, today)
        weekly = weekly_fitness_series(daily)
        assert len(weekly) == 2
        current = current_fitness(daily, today)
        assert current["ctl"] == 83.0


class TestGaps:
    def test_no_a_race_is_high_for_year_out(self):
        items = gaps(
            horizon_days=365,
            races=[],
            phase_source="unspecified",
            subjective_empty_days=None,
            has_power=None,
        )
        fields = {item["field"] for item in items}
        assert "calendar.goal_events" in fields
        assert "calendar.phase_context" in fields
        assert any(item["severity"] == "high" for item in items)

    def test_missing_atp_is_not_a_gap_when_phase_derived(self):
        items = gaps(
            horizon_days=90,
            races=[{"category": "RACE_A"}],
            phase_source="derived_from_race",
            subjective_empty_days=0,
            has_power=True,
        )
        assert items == []

    def test_unknown_readiness_is_a_gap(self):
        items = gaps(
            horizon_days=90,
            races=[{"category": "RACE_A"}],
            phase_source="derived_from_race",
            subjective_empty_days=0,
            has_power=True,
            readiness_state="unknown",
        )
        assert any(item["field"] == "readiness.signals" for item in items)


class TestReadiness:
    def test_ctl_and_rhr_only_today_is_unknown_not_green(self):
        today = date(2026, 9, 16)
        records = [
            Wellness.model_validate(
                {
                    "id": "2026-09-15",
                    "ctl": 89.0,
                    "hrv": 61.0,
                    "restingHR": 43,
                    "sleepSecs": 7 * 3600,
                }
            ),
            Wellness.model_validate(
                {
                    "id": "2026-09-16",
                    "ctl": 88.9,
                    "atl": 94.7,
                    "restingHR": 43,
                }
            ),
        ]
        block = readiness_block(records, today)
        assert block["readiness_state"] == "unknown"
        assert block["gating"] == "do_not_treat_as_green"
        assert "hrv" in block["missing_today"]
        assert "sleep" in block["missing_today"]
        assert "2026-09-16" in block["days_missing_hrv_and_sleep"]

    def test_does_not_reuse_yesterdays_complete_row(self):
        today = date(2026, 9, 17)
        records = [
            Wellness.model_validate(
                {
                    "id": "2026-09-15",
                    "ctl": 89.0,
                    "hrv": 61.0,
                    "restingHR": 43,
                    "sleepSecs": 7 * 3600,
                }
            ),
            Wellness.model_validate({"id": "2026-09-17", "ctl": 88.2, "atl": 90.3}),
        ]
        block = readiness_block(records, today)
        assert block["as_of"] == "2026-09-17"
        assert block["readiness_state"] == "unknown"
        assert "today" not in block.get("hrv", {})

    def test_today_complete_is_a_color(self):
        today = date(2026, 9, 15)
        records = [
            Wellness.model_validate(
                {
                    "id": (today - timedelta(days=i)).isoformat(),
                    "ctl": 80.0,
                    "hrv": 50.0,
                    "restingHR": 48,
                    "sleepSecs": 7 * 3600,
                }
            )
            for i in range(20)
        ]
        block = readiness_block(records, today)
        assert block["readiness_state"] in {"green", "amber", "red"}
        assert "gating" not in block


class TestDurability:
    def test_fresh_bin_from_short_trace(self):
        watts = [300.0] * 1300
        result = durability_from_streams([watts])
        assert result["bins_kj"] == [0, 1000, 2000, 3000]
        assert result["curves_by_bin"]["0"]["5m"] == 300
        assert result["curves_by_bin"]["0"]["20m"] == 300


class TestGetAthleteStateTool:
    @patch("intervals_icu_mcp.tools.athlete_state.date")
    async def test_composite_success(self, mock_date, mock_config, respx_mock):
        today = date(2026, 9, 16)
        mock_date.today.return_value = today
        wellness = []
        for i in range(40):
            day = today - timedelta(days=39 - i)
            wellness.append(
                {
                    "id": day.isoformat(),
                    "ctl": 80.0 + i * 0.1,
                    "atl": 82.0,
                    "tsb": -2.0,
                    "rampRate": 0.5,
                    "hrv": 50.0,
                    "restingHR": 48,
                    "sleepSecs": 7 * 3600,
                    "mood": 4,
                }
            )
        respx_mock.get("/athlete/i123456/wellness").mock(return_value=Response(200, json=wellness))
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 10,
                        "start_date_local": "2026-10-04",
                        "name": "Diablo Challenge",
                        "category": "RACE_A",
                        "type": "Ride",
                        "moving_time": 4200,
                    },
                    {
                        "id": 11,
                        "start_date_local": "2026-09-17",
                        "name": "Endurance",
                        "category": "WORKOUT",
                        "type": "Ride",
                        "icu_training_load": 80,
                        "icu_intensity": 0.70,
                    },
                ],
            )
        )
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "start_date_local": "2026-09-10T08:00:00",
                        "name": "Ride",
                        "type": "Ride",
                        "moving_time": 7200,
                        "icu_training_load": 90,
                        "icu_intensity": 0.72,
                    }
                ],
            )
        )
        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "days": 42,
                            "secs": [5, 60, 300, 1200, 3600],
                            "values": [1000, 500, 360, 330, 260],
                        },
                        {
                            "days": 90,
                            "secs": [5, 60, 300, 1200, 3600],
                            "values": [1010, 510, 365, 332, 262],
                        },
                        {
                            "days": 365,
                            "secs": [5, 60, 300, 1200, 3600],
                            "values": [1022, 550, 370, 338, 268],
                        },
                    ]
                },
            )
        )
        respx_mock.get("/athlete/i123456/sport-settings").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "types": ["Ride"], "ftp": 321, "lthr": 165}],
            )
        )

        result = await get_athlete_state(ctx=_ctx(mock_config), horizon_days=90)
        response = json.loads(result)
        data = response["data"]
        assert data["athlete_id"] == "i123456"
        assert "tsb_tolerance" in data["fitness_form"]
        assert data["power_profile"]["estimated_ftp"] == 321
        assert data["power_profile"]["ftp_source"] == "sport_settings"
        assert data["power_profile"]["curves"]["d365"]["60m"] == 268
        assert data["calendar"]["goal_events"][0]["category"] == "RACE_A"
        assert data["phase_context"]["source"] == "derived_from_race"
        assert data["readiness"]["readiness_state"] in {"green", "amber", "red"}
        assert "unknown" != data["readiness"]["readiness_state"]
        assert "compliance" in data
        flags = response["analysis"]["derived_flags"]
        assert any("60m_to_ftp_gap" in flag for flag in flags)
        assert not any(
            item["field"] == "calendar.goal_events" for item in response["analysis"]["gaps"]
        )

    async def test_validation_unknown_include(self, mock_config):
        result = await get_athlete_state(include=["bananas"], ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"

    async def test_year_out_gaps_without_a_race(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/wellness").mock(return_value=Response(200, json=[]))
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=[]))
        respx_mock.get("/athlete/i123456/activities").mock(return_value=Response(200, json=[]))
        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(200, json={"list": []})
        )
        respx_mock.get("/athlete/i123456/sport-settings").mock(return_value=Response(200, json=[]))

        result = await get_athlete_state(horizon_days=365, ctx=_ctx(mock_config))
        response = json.loads(result)
        fields = {item["field"] for item in response["analysis"]["gaps"]}
        assert "calendar.goal_events" in fields
        assert "calendar.phase_context" in fields

    async def test_durability_include_bins_from_streams(self, mock_config, respx_mock):
        _durability_cache.clear()
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "long1",
                        "start_date_local": "2026-09-10T08:00:00",
                        "name": "Long",
                        "type": "Ride",
                        "moving_time": 10800,
                        "icu_training_load": 200,
                    }
                ],
            )
        )
        respx_mock.get("/activity/long1/streams.json").mock(
            return_value=Response(
                200,
                json=[{"type": "watts", "data": [250] * 1300}],
            )
        )

        result = await get_athlete_state(include=["durability"], ctx=_ctx(mock_config))
        response = json.loads(result)
        durability = response["data"]["power_profile"]["durability"]
        assert durability["curves_by_bin"]["0"]["5m"] == 250
